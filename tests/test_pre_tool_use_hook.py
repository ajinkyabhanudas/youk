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
