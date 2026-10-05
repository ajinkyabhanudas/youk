"""Usage tap and the hook wiring around it.

These run the real scripts as subprocesses with fixture stdin, the way the host calls them,
and read back what landed in the ledger. The properties: the right events appear, no prompt
or command text ever does, and nothing can fail or print.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import events

REPO = Path(__file__).parent.parent
TAP = REPO / "plugin" / "scripts" / "usage_tap.py"
PROMPT_HOOK = REPO / "plugin" / "scripts" / "user_prompt_submit.py"
START_HOOK = REPO / "plugin" / "scripts" / "session_start.py"
HOOKS_JSON = REPO / "plugin" / "hooks" / "hooks.json"


def _run(script: Path, payload, root: Path, arm: str = "") -> subprocess.CompletedProcess:
    env = {**os.environ, "YOUK_ROOT": str(root), "YOUK_ARM": arm,
           "YOUK_CORE_URL": "http://127.0.0.1:1"}
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    # The tap runs under -S (no site-packages) in hooks.json to save ~6 ms; prove it works so.
    flags = ["-S"] if script == TAP else []
    return subprocess.run([sys.executable, *flags, str(script)], input=stdin, capture_output=True,
                          text=True, env=env, timeout=30)


def _ledger(root: Path, slug: str = "proj") -> list[dict]:
    return list(events.read_events(root, slug))


def _post(tool, tool_input=None, response=None, event="PostToolUse", **extra):
    payload = {"hook_event_name": event, "tool_name": tool, "tool_input": tool_input or {},
               "cwd": "/work/proj", "session_id": "sess-1", "tool_use_id": "toolu_1", **extra}
    if response is not None:
        payload["tool_response"] = response
    return payload


class TestToolEvents:
    def test_a_tool_call_becomes_a_tool_event_with_its_duration(self, tmp_path):
        r = _run(TAP, _post("Edit", duration=42), tmp_path)
        assert r.returncode == 0 and r.stdout == ""
        tool = [e for e in _ledger(tmp_path) if e["kind"] == "tool"]
        assert len(tool) == 1
        assert tool[0]["name"] == "Edit" and tool[0]["ms"] == 42 and tool[0]["status"] == "ok"
        assert tool[0]["src"] == "hook"

    def test_a_failure_event_is_recorded_as_fail(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "ls"}, event="PostToolUseFailure",
                        error={"type": "x", "message": "Exit code 2\nboom"}), tmp_path)
        (tool,) = [e for e in _ledger(tmp_path) if e["kind"] == "tool"]
        assert tool["status"] == "fail"

    def test_mcp_tool_names_survive(self, tmp_path):
        _run(TAP, _post("mcp__youk-core__route_task"), tmp_path)
        assert [e["name"] for e in _ledger(tmp_path) if e["kind"] == "tool"] == [
            "mcp__youk-core__route_task"
        ]

    def test_arm_comes_from_the_environment(self, tmp_path):
        _run(TAP, _post("Edit"), tmp_path, arm="lean")
        assert {e.get("arm") for e in _ledger(tmp_path)} == {"lean"}


class TestSkillEvents:
    def test_skill_name_is_recorded_under_either_field_name(self, tmp_path):
        _run(TAP, _post("Skill", {"skill": "code-review"}), tmp_path)
        _run(TAP, _post("Skill", {"skill_name": "/adr"}, tool_use_id="toolu_2"), tmp_path)
        names = sorted(e["name"] for e in _ledger(tmp_path) if e["kind"] == "skill")
        assert names == ["adr", "code-review"]


class TestTestAndCommitEvents:
    def test_pytest_exit_code_is_captured(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "uv run pytest tests/ -q"},
                        {"stdout": "...", "exit_code": 1}), tmp_path)
        (test,) = [e for e in _ledger(tmp_path) if e["kind"] == "test"]
        assert test["name"] == "pytest" and test["status"] == "fail" and test["n"] == 1

    def test_chained_runners_each_get_an_event(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "ruff check . && python -m pytest"},
                        {"exit_code": 0}), tmp_path)
        names = sorted(e["name"] for e in _ledger(tmp_path) if e["kind"] == "test")
        assert names == ["pytest", "ruff"]

    def test_a_failed_bash_delivered_as_failure_event_still_reads_the_exit_code(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "cargo test"}, event="PostToolUseFailure",
                        error={"message": "Exit code 101"}), tmp_path)
        (test,) = [e for e in _ledger(tmp_path) if e["kind"] == "test"]
        assert test["name"] == "cargo-test" and test["n"] == 101 and test["status"] == "fail"

    def test_git_commit_is_a_commit_event_but_dry_run_is_not(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "git add -A && git commit -m 'x'"},
                        {"exit_code": 0}), tmp_path)
        _run(TAP, _post("Bash", {"command": "git commit --dry-run"}, {"exit_code": 0},
                        tool_use_id="toolu_2"), tmp_path)
        assert len([e for e in _ledger(tmp_path) if e["kind"] == "commit"]) == 1

    def test_unrelated_commands_produce_only_the_tool_event(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "ls -la"}, {"exit_code": 0}), tmp_path)
        assert {e["kind"] for e in _ledger(tmp_path)} <= {"tool", "hook"}


class TestPrivacy:
    def test_command_text_and_paths_never_reach_the_ledger(self, tmp_path):
        secret = "pytest tests/test_acme_billing_migration.py --token=sk-secret-123"
        _run(TAP, _post("Bash", {"command": secret}, {"exit_code": 0}), tmp_path)
        _run(TAP, _post("Edit", {"file_path": "/Users/me/clients/acme/plan.md"}), tmp_path,)
        raw = "".join(p.read_text() for p in (tmp_path / "state" / "events").rglob("*.jsonl"))
        for leaked in ("sk-secret", "acme", "billing", "/Users/me", "plan.md", "sess-1"):
            assert leaked not in raw


class TestNeverFailsNeverPrints:
    def test_garbage_stdin(self, tmp_path):
        for junk in ("", "not json", "[]", "null", "{"):
            r = _run(TAP, junk, tmp_path)
            assert r.returncode == 0 and r.stdout == "" and r.stderr == ""

    def test_unknown_event_is_ignored(self, tmp_path):
        r = _run(TAP, {"hook_event_name": "Stop", "cwd": "/w/proj"}, tmp_path)
        assert r.returncode == 0 and _ledger(tmp_path) == []

    def test_missing_root_is_a_silent_noop(self, tmp_path):
        env = {**os.environ, "YOUK_ROOT": str(tmp_path / "nope"), "HOME": str(tmp_path / "h")}
        r = subprocess.run([sys.executable, str(TAP)], input=json.dumps(_post("Edit")),
                           capture_output=True, text=True, env=env)
        assert r.returncode == 0 and r.stdout == ""


class TestSessionAndLatencySampling:
    def test_session_end_records_the_reason_and_its_own_latency(self, tmp_path):
        _run(TAP, {"hook_event_name": "SessionEnd", "exit_reason": "clear",
                   "cwd": "/w/proj", "session_id": "s"}, tmp_path)
        got = _ledger(tmp_path)
        assert [e["name"] for e in got if e["kind"] == "session"] == ["end.clear"]
        assert [e for e in got if e["kind"] == "hook" and e["name"] == "session_end"]

    def test_hook_latency_is_sampled_not_recorded_on_every_call(self, tmp_path):
        for i in range(40):
            _run(TAP, _post("Edit", tool_use_id=f"toolu_{i}", duration=1), tmp_path)
        got = _ledger(tmp_path)
        tools = [e for e in got if e["kind"] == "tool"]
        hooks = [e for e in got if e["kind"] == "hook"]
        assert len(tools) == 40
        assert 0 < len(hooks) < 20
        assert all(h["n"] == 10 for h in hooks)  # the sampling weight, for the report


class TestCorrectionAndStartEvents:
    def test_pushback_and_rule_phrases_are_counted_without_the_text(self, tmp_path):
        prompt = "you missed the edge case, and from now on always run the linter first"
        r = _run(PROMPT_HOOK, {"prompt": prompt, "cwd": "/w/proj", "session_id": "s"}, tmp_path)
        assert r.returncode == 0
        names = sorted(e["name"] for e in _ledger(tmp_path) if e["kind"] == "correction")
        assert names == ["pushback", "rule_phrase"]
        raw = "".join(p.read_text() for p in (tmp_path / "state" / "events").rglob("*.jsonl"))
        assert "linter" not in raw and "edge case" not in raw

    def test_a_neutral_prompt_records_nothing(self, tmp_path):
        _run(PROMPT_HOOK, {"prompt": "please add a docstring to the parser module",
                           "cwd": "/w/proj", "session_id": "s"}, tmp_path)
        assert [e for e in _ledger(tmp_path) if e["kind"] == "correction"] == []

    def test_session_start_hook_records_the_source(self, tmp_path):
        _run(START_HOOK, {"cwd": "/w/proj", "session_id": "s", "source": "resume"}, tmp_path)
        assert [e["name"] for e in _ledger(tmp_path) if e["kind"] == "session"] == ["start.resume"]


class TestHooksJson:
    def test_tap_is_registered_for_every_event_it_handles(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        for event in ("PostToolUse", "PostToolUseFailure", "SessionEnd"):
            commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
            assert any("usage_tap.py" in c for c in commands), event

    def test_the_tap_runs_without_site_packages(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        command = hooks["PostToolUse"][-1]["hooks"][0]["command"]
        assert " -S " in command, "usage_tap is stdlib-only and should skip site import"

    def test_every_registered_script_exists(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        for groups in hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    script = hook["command"].split("scripts/")[1].rstrip('"')
                    assert (REPO / "plugin" / "scripts" / script).exists(), script


class TestCodexPayloads:
    """Codex sends PostToolUse with tool_response but documents no duration or exit code. It names
    shell commands Bash, edits apply_patch, and has no Skill tool."""

    def test_a_test_run_with_no_exit_code_is_unknown_not_a_pass(self, tmp_path):
        _run(TAP, {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "/w/proj",
                   "session_id": "s", "tool_use_id": "t1",
                   "tool_input": {"command": "pytest -q"}, "tool_response": "3 failed, 10 passed"},
             tmp_path)
        (test,) = [e for e in _ledger(tmp_path) if e["kind"] == "test"]
        assert test["status"] == "unknown" and "n" not in test

    def test_a_commit_with_no_exit_code_is_not_counted_as_one(self, tmp_path):
        _run(TAP, {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": "/w/proj",
                   "session_id": "s", "tool_use_id": "t1",
                   "tool_input": {"command": "git commit -m x"}, "tool_response": {"stdout": "[main abc] x"}},
             tmp_path)
        (commit,) = [e for e in _ledger(tmp_path) if e["kind"] == "commit"]
        assert commit["status"] == "unknown"

    def test_apply_patch_is_recorded_without_latency(self, tmp_path):
        _run(TAP, {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": "/w/proj",
                   "session_id": "s", "tool_use_id": "t1", "tool_input": {"patch": "*** Begin Patch"}},
             tmp_path)
        (tool,) = [e for e in _ledger(tmp_path) if e["kind"] == "tool"]
        assert tool["name"] == "apply_patch" and "ms" not in tool

    def test_mcp_tool_names_use_the_same_pattern(self, tmp_path):
        _run(TAP, _post("mcp__youk-core__session_start"), tmp_path)
        assert [e["name"] for e in _ledger(tmp_path) if e["kind"] == "tool"] == [
            "mcp__youk-core__session_start"]

    def test_session_end_works_without_a_reason(self, tmp_path):
        _run(TAP, {"hook_event_name": "SessionEnd", "cwd": "/w/proj", "session_id": "s"}, tmp_path)
        assert [e["name"] for e in _ledger(tmp_path) if e["kind"] == "session"] == ["end.other"]

    def test_a_real_exit_code_still_gives_ok_and_fail(self, tmp_path):
        _run(TAP, _post("Bash", {"command": "pytest"}, {"exit_code": 0}), tmp_path)
        _run(TAP, _post("Bash", {"command": "ruff check"}, {"exit_code": 1}, tool_use_id="t2"), tmp_path)
        got = {e["name"]: e["status"] for e in _ledger(tmp_path) if e["kind"] == "test"}
        assert got == {"pytest": "ok", "ruff": "fail"}
