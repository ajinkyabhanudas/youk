"""Tests for the pre_tool_use.py PreToolUse hook entrypoint itself — stdin in,
stdout out, via a real subprocess (not just the underlying function), since the
hook's actual contract with Claude Code is the JSON on stdout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).parent.parent
_HOOK = _REPO / "plugin" / "scripts" / "pre_tool_use.py"


def _run_hook(payload: dict, env: dict | None = None) -> dict:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        env=full_env,
    )
    return json.loads(result.stdout)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False,
    )


class TestNonBashToolsPassThrough:
    def test_read_tool_is_ignored(self, tmp_path):
        out = _run_hook({"tool_name": "Read", "tool_input": {"file_path": "x"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}

    def test_edit_tool_allowed_when_no_gate_state_exists(self, tmp_path):
        """No route_task-ran flag, no kill_criterion flag → nothing to gate on, allow."""
        youk_root = tmp_path / "youk_root"
        (youk_root / "state").mkdir(parents=True)
        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {}, "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(youk_root)},
        )
        assert out["continue"] is True
        assert "hookSpecificOutput" not in out


class TestSafeBashCommandsPassThroughSilently:
    def test_git_status_produces_no_message(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}
        assert "systemMessage" not in out

    def test_ls_produces_no_message(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": str(tmp_path)})
        assert out == {"continue": True}


class TestDestructiveBashCommandsGetCheckpointed:
    def test_never_blocks_the_command(self, tmp_path):
        """The whole design point: this is a safety net, not a permission gate —
        continue must always be True regardless of what the command is."""
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git reset --hard HEAD~1"},
            "cwd": str(r),
        })
        assert out["continue"] is True

    def test_checkpoint_noted_when_there_is_something_to_protect(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        _git(["config", "user.email", "t@t.com"], r)
        _git(["config", "user.name", "t"], r)
        (r / "f.txt").write_text("v1\n")
        _git(["add", "f.txt"], r)
        _git(["commit", "-q", "-m", "init"], r)
        (r / "f.txt").write_text("uncommitted change\n")

        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git checkout ."},
            "cwd": str(r),
        })
        assert "systemMessage" in out
        assert "checkpoint" in out["systemMessage"].lower()
        assert "revert_checkpoint.py" in out["systemMessage"]

    def test_no_checkpoint_noted_when_tree_is_clean(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(["init", "-q"], r)
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git checkout ."},
            "cwd": str(r),
        })
        assert out == {"continue": True}

    def test_non_git_directory_does_not_crash_the_hook(self, tmp_path):
        out = _run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf ./build"},
            "cwd": str(tmp_path),
        })
        assert out == {"continue": True}


class TestDeployFreshnessGate:
    """CIR-153: the PreToolUse boundary gating mcp__youk-core__* /
    mcp__youk-code__* tool calls until the running container is confirmed not
    to predate the latest runtime-sensitive commit. Real subprocess hook,
    real git repo, fake `docker`/`launchctl` executables on PATH so the suite
    never touches an actual container."""

    def _repo(self, tmp_path: Path) -> Path:
        d = tmp_path / "youk_root"
        d.mkdir()
        self._git(d, "init", "-q")
        self._git(d, "config", "user.email", "t@t.t")
        self._git(d, "config", "user.name", "t")
        (d / "README.md").write_text("x")
        self._git(d, "add", "-A")
        self._git(d, "commit", "-qm", "init")
        return d

    @staticmethod
    def _git(d: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True, text=True)

    def _touch_runtime_file(self, d: Path) -> str:
        """Commit a servers/-prefixed change; return that commit's ISO timestamp."""
        p = d / "servers" / "core" / "src" / "session.py"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("changed")
        self._git(d, "add", "-A")
        self._git(d, "commit", "-qm", "touch runtime file")
        r = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%cI"],
                            capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def _fake_bin(self, tmp_path: Path, *, docker_fail: bool = False,
                   launchctl_fail: bool = False, started_at: str = "") -> tuple[Path, Path]:
        """Write fake `docker` and `launchctl` executables to tmp_path/bin.

        `docker inspect ... --format {{.State.StartedAt}}` reads its answer
        from a state file so a fake `launchctl kickstart` can simulate an
        actual restart by rewriting it — mirrors the real world, where a
        restart is confirmed by the container reporting a new boot time, not
        by the kickstart command merely returning 0.
        """
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        state_file = tmp_path / "started_at.txt"
        state_file.write_text(started_at)

        docker_sh = bindir / "docker"
        if docker_fail:
            docker_sh.write_text("#!/bin/sh\nexit 1\n")
        else:
            docker_sh.write_text(
                "#!/bin/sh\n"
                f'cat "{state_file}"\n'
            )
        docker_sh.chmod(0o755)

        launchctl_sh = bindir / "launchctl"
        if launchctl_fail:
            launchctl_sh.write_text("#!/bin/sh\nexit 1\n")
        else:
            launchctl_sh.write_text(
                "#!/bin/sh\n"
                f'printf %s "2099-01-01T00:00:00Z" > "{state_file}"\n'
                "exit 0\n"
            )
        launchctl_sh.chmod(0o755)
        return bindir, state_file

    def _env_with_fake_bin(self, bindir: Path, root: Path) -> dict:
        return {
            "YOUK_ROOT": str(root),
            "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        }

    def test_fresh_container_allows_silently(self, tmp_path):
        root = self._repo(tmp_path)
        commit_time = self._touch_runtime_file(root)
        bindir, _ = self._fake_bin(tmp_path, started_at="2099-01-01T00:00:00Z")
        assert commit_time  # container boots AFTER the commit -> fresh

        out = _run_hook(
            {"tool_name": "mcp__youk-core__session_start", "tool_input": {}, "cwd": str(root)},
            env=self._env_with_fake_bin(bindir, root),
        )
        assert out == {"continue": True}

    def test_stale_container_auto_restarts_and_allows(self, tmp_path):
        root = self._repo(tmp_path)
        self._touch_runtime_file(root)
        # container booted long before the commit above -> stale
        bindir, state_file = self._fake_bin(tmp_path, started_at="2020-01-01T00:00:00Z")

        out = _run_hook(
            {"tool_name": "mcp__youk-core__next_task", "tool_input": {}, "cwd": str(root)},
            env=self._env_with_fake_bin(bindir, root),
        )
        assert out["continue"] is True
        assert "hookSpecificOutput" not in out
        assert "auto-restarted" in out["systemMessage"].lower()
        # the fake launchctl really did rewrite the boot-time state
        assert state_file.read_text() == "2099-01-01T00:00:00Z"

    def test_stale_container_failed_restart_denies(self, tmp_path):
        root = self._repo(tmp_path)
        self._touch_runtime_file(root)
        bindir, _ = self._fake_bin(tmp_path, started_at="2020-01-01T00:00:00Z", launchctl_fail=True)

        out = _run_hook(
            {"tool_name": "mcp__youk-core__route_task", "tool_input": {}, "cwd": str(root)},
            env=self._env_with_fake_bin(bindir, root),
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "launchctl kickstart" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_docker_unreachable_fails_closed(self, tmp_path):
        root = self._repo(tmp_path)
        self._touch_runtime_file(root)
        bindir, _ = self._fake_bin(tmp_path, docker_fail=True)

        out = _run_hook(
            {"tool_name": "mcp__youk-code__implement", "tool_input": {}, "cwd": str(root)},
            env=self._env_with_fake_bin(bindir, root),
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "could not be determined" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_non_youk_mcp_tool_passes_through_untouched(self, tmp_path):
        root = self._repo(tmp_path)
        bindir, _ = self._fake_bin(tmp_path, docker_fail=True)  # would deny if it were checked

        out = _run_hook(
            {"tool_name": "mcp__some-other-server__do_thing", "tool_input": {}, "cwd": str(root)},
            env=self._env_with_fake_bin(bindir, root),
        )
        assert out == {"continue": True}

    def test_docker_and_launchctl_never_invoked_for_edit(self, tmp_path):
        """The gate only intercepts youk MCP tool calls — Edit/Write keep
        going through check_m_plus_write_gate exactly as before, with zero
        dependency on docker being present at all."""
        root = self._repo(tmp_path)
        (root / "state").mkdir()
        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {}, "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root), "PATH": "/nonexistent"},
        )
        assert out["continue"] is True


class TestMissingFieldsDegradeGracefully:
    def test_empty_payload(self):
        out = _run_hook({})
        assert out == {"continue": True}

    def test_missing_command(self, tmp_path):
        out = _run_hook({"tool_name": "Bash", "tool_input": {}, "cwd": str(tmp_path)})
        assert out == {"continue": True}


class TestMPlusWriteGate:
    """CIR-150 item 4 / CIR-151: real subprocess-level proof that an M+ session
    with no capability skill logged gets its Edit/Write denied, and that the
    same session state after a skill is logged allows it through — the exact
    minimum real test CIR-151 specifies."""

    def _project(self, tmp_path, slug="myproject"):
        project = tmp_path / slug
        project.mkdir()
        return project

    def _youk_root(self, tmp_path):
        root = tmp_path / "youk_root"
        (root / "state").mkdir(parents=True)
        return root

    def _open_session(self, root, slug):
        slug_dir = root / "state" / "sessions" / slug
        slug_dir.mkdir(parents=True)
        (slug_dir / "open.json").write_text(json.dumps({"slug": slug}))
        return slug_dir

    def test_m_size_session_with_no_skill_logged_is_denied(self, tmp_path):
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        slug_dir = self._open_session(root, "myproject")
        (slug_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "add auth", "size": "M"},
        ]))

        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "route_task" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_same_session_after_skill_logged_is_allowed(self, tmp_path):
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        slug_dir = self._open_session(root, "myproject")
        (slug_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "add auth", "size": "M"},
        ]))
        # Same session — write the skill invocation log entry after session open.
        (slug_dir / "skills-invoked.jsonl").write_text(
            json.dumps({"skill": "dev-loop", "ts": time.time()}) + "\n"
        )

        out = _run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out == {"continue": True}

    def test_apply_patch_is_gated_identically_to_edit_write_cir_155(self, tmp_path):
        """CIR-155: Codex's canonical file-edit tool name is "apply_patch", not
        Edit/Write. Real proof the fix actually blocks something, not just that
        the structural scanner found a code line — same M-size-no-skill setup as
        test_m_size_session_with_no_skill_logged_is_denied, tool_name swapped."""
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        slug_dir = self._open_session(root, "myproject")
        (slug_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "add auth", "size": "M"},
        ]))

        out = _run_hook(
            {"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "route_task" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_xs_size_session_is_never_gated(self, tmp_path):
        """Sub-M sizes were never in scope for this gate — only M/L/XL."""
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        slug_dir = self._open_session(root, "myproject")
        (slug_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "fix typo", "size": "XS"},
        ]))

        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out == {"continue": True}

    def test_route_task_never_called_this_session_is_not_gated_by_size_alone(self, tmp_path):
        """No route_task call at all this session -> no recorded size -> the
        size-based condition has nothing to gate on (kill_criterion is the
        separate, additional condition covering this case once it fires)."""
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        self._open_session(root, "myproject")

        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out == {"continue": True}

    def test_kill_criterion_triggered_denies_write_with_no_routing_at_all(self, tmp_path):
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        self._open_session(root, "myproject")
        (root / "state" / "kill-criterion-triggered.json").write_text(
            json.dumps({"triggered": True})
        )

        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "kill_criterion" in out["hookSpecificOutput"]["permissionDecisionReason"]

    def test_kill_criterion_triggered_but_routed_this_session_is_allowed(self, tmp_path):
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        slug_dir = self._open_session(root, "myproject")
        (slug_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "fix typo", "size": "XS"},
        ]))
        (root / "state" / "kill-criterion-triggered.json").write_text(
            json.dumps({"triggered": True})
        )

        out = _run_hook(
            {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out == {"continue": True}

    def test_bash_tool_is_unaffected_by_the_write_gate(self, tmp_path):
        """The gate only applies to Edit/Write — Bash keeps its existing
        checkpoint-only behavior even under a triggered kill_criterion."""
        root = self._youk_root(tmp_path)
        project = self._project(tmp_path)
        self._open_session(root, "myproject")
        (root / "state" / "kill-criterion-triggered.json").write_text(
            json.dumps({"triggered": True})
        )

        out = _run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(project)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out == {"continue": True}


class TestVerificationClaimGate:
    """CIR-154 item 4: a claim on record with an unresolved sub_claim must
    block mcp__youk-core__session_end(close_cluster=True) at the same
    PreToolUse boundary CIR-150 item 4 already uses for the M+ write gate --
    real subprocess hook, real claim files on disk, no mocking."""

    def _youk_root(self, tmp_path) -> Path:
        root = tmp_path / "youk_root"
        (root / "state").mkdir(parents=True)
        return root

    def _write_claim(self, root: Path, name: str, sub_claims: list[dict]) -> None:
        claims_dir = root / "state" / "verification-contracts" / "claims"
        claims_dir.mkdir(parents=True, exist_ok=True)
        (claims_dir / f"{name}.json").write_text(json.dumps({
            "statement": name,
            "dimension": "host",
            "sub_claims": sub_claims,
            "all_verified": all(sc["status"] == "verified" for sc in sub_claims),
        }))

    def _fake_fresh_docker_bin(self, tmp_path: Path) -> Path:
        """Minimal fake docker/launchctl reporting an always-fresh container,
        so tests that fall through the claim gate (nothing to block) don't
        also need to exercise CIR-153's separate deploy-freshness gate."""
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        (bindir / "docker").write_text('#!/bin/sh\nprintf %s "2099-01-01T00:00:00Z"\n')
        (bindir / "docker").chmod(0o755)
        return bindir

    def test_session_end_with_unresolved_sub_claim_is_denied(self, tmp_path):
        root = self._youk_root(tmp_path)
        self._write_claim(root, "youk-is-agent-agnostic", [
            {"id": "pre_tool_guard:claude-code", "mechanism": "pre_tool_guard",
             "host": "claude-code", "status": "verified", "evidence": "plugin/hooks/hooks.json:26"},
            {"id": "pre_tool_guard:codex", "mechanism": "pre_tool_guard",
             "host": "codex", "status": "failed", "evidence": None},
        ])

        out = _run_hook(
            {"tool_name": "mcp__youk-core__session_end",
             "tool_input": {"summary": "done", "close_cluster": True},
             "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root)},
        )
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "pre_tool_guard:codex" in reason
        assert "failed" in reason

    def test_session_end_with_every_sub_claim_verified_is_allowed(self, tmp_path):
        root = self._youk_root(tmp_path)
        self._write_claim(root, "compaction-works-everywhere", [
            {"id": "compaction_context:claude-code", "mechanism": "compaction_context",
             "host": "claude-code", "status": "verified", "evidence": "plugin/hooks/hooks.json:4"},
        ])
        bindir = self._fake_fresh_docker_bin(tmp_path)

        out = _run_hook(
            {"tool_name": "mcp__youk-core__session_end",
             "tool_input": {"summary": "done", "close_cluster": True},
             "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
        )
        assert "hookSpecificOutput" not in out or out["hookSpecificOutput"].get("permissionDecision") != "deny"

    def test_session_end_without_close_cluster_is_not_gated_on_claims(self, tmp_path):
        """A mid-session session_end (close_cluster not set) isn't the "report
        this done" boundary -- only the close_cluster=True call is."""
        root = self._youk_root(tmp_path)
        self._write_claim(root, "youk-is-agent-agnostic", [
            {"id": "pre_tool_guard:codex", "mechanism": "pre_tool_guard",
             "host": "codex", "status": "failed", "evidence": None},
        ])
        bindir = self._fake_fresh_docker_bin(tmp_path)

        out = _run_hook(
            {"tool_name": "mcp__youk-core__session_end",
             "tool_input": {"summary": "partial"},
             "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
        )
        assert "hookSpecificOutput" not in out or out["hookSpecificOutput"].get("permissionDecision") != "deny"

    def test_other_mcp_tool_calls_are_not_gated_on_claims(self, tmp_path):
        root = self._youk_root(tmp_path)
        self._write_claim(root, "youk-is-agent-agnostic", [
            {"id": "pre_tool_guard:codex", "mechanism": "pre_tool_guard",
             "host": "codex", "status": "failed", "evidence": None},
        ])
        bindir = self._fake_fresh_docker_bin(tmp_path)

        out = _run_hook(
            {"tool_name": "mcp__youk-core__route_task", "tool_input": {}, "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
        )
        assert "hookSpecificOutput" not in out or out["hookSpecificOutput"].get("permissionDecision") != "deny"

    def test_no_claims_directory_at_all_falls_through_to_allow(self, tmp_path):
        root = self._youk_root(tmp_path)
        bindir = self._fake_fresh_docker_bin(tmp_path)

        out = _run_hook(
            {"tool_name": "mcp__youk-core__session_end",
             "tool_input": {"summary": "done", "close_cluster": True},
             "cwd": str(tmp_path)},
            env={"YOUK_ROOT": str(root), "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
        )
        assert "hookSpecificOutput" not in out or out["hookSpecificOutput"].get("permissionDecision") != "deny"
