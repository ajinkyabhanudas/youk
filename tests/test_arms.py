"""Arms: deterministic assignment, override, bare runs ungated, and every event carries the arm."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import arms
import events
import tool_spans

REPO = Path(__file__).parent.parent
START_HOOK = REPO / "plugin" / "scripts" / "session_start.py"
PRE_HOOK = REPO / "plugin" / "scripts" / "pre_tool_use.py"
TAP = REPO / "plugin" / "scripts" / "usage_tap.py"
PROMPT_HOOK = REPO / "plugin" / "scripts" / "user_prompt_submit.py"


class TestAssignment:
    def test_default_is_full_so_daily_work_is_never_ungated_by_chance(self, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        monkeypatch.delenv("YOUK_ARM_MODE", raising=False)
        assert {arms.assign_arm(f"s{i}") for i in range(50)} == {"full"}

    def test_randomize_is_deterministic_and_reaches_every_arm(self, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        monkeypatch.setenv("YOUK_ARM_MODE", "randomize")
        first = [arms.assign_arm(f"s{i}") for i in range(300)]
        assert first == [arms.assign_arm(f"s{i}") for i in range(300)]
        assert set(first) == set(arms.ARMS)
        assert min(first.count(a) for a in arms.ARMS) > 60  # roughly a third each

    def test_override_beats_randomize(self, monkeypatch):
        monkeypatch.setenv("YOUK_ARM_MODE", "randomize")
        monkeypatch.setenv("YOUK_ARM", "bare")
        assert {arms.assign_arm(f"s{i}") for i in range(30)} == {"bare"}

    def test_unknown_override_is_ignored(self, monkeypatch):
        monkeypatch.setenv("YOUK_ARM", "superpowers")
        monkeypatch.delenv("YOUK_ARM_MODE", raising=False)
        assert arms.assign_arm("s") == "full" and arms.override() == ""


class TestSessionArmState:
    def test_written_arm_is_read_back_per_project(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        assert arms.write_session_arm(tmp_path, "proj-a", "lean")
        assert arms.write_session_arm(tmp_path, "proj-b", "bare")
        assert arms.current_arm(tmp_path, "proj-a") == "lean"
        assert arms.current_arm(tmp_path, "proj-b") == "bare"

    def test_unknown_arm_is_not_written_and_missing_state_reads_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        assert not arms.write_session_arm(tmp_path, "p", "gold")
        assert arms.current_arm(tmp_path, "p") == ""
        assert arms.current_arm(None, "p") == ""

    def test_hostile_slug_cannot_leave_the_state_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        arms.write_session_arm(tmp_path, "../../etc/x", "bare")
        assert not (tmp_path.parent / "etc").exists()
        assert arms.current_arm(tmp_path, "../../etc/x") == "bare"

    def test_gates_are_off_only_for_bare(self):
        assert [arms.gates_active(a) for a in ("full", "lean", "bare", "")] == [
            True, True, False, True]


class TestServerEventsCarryTheArm:
    def test_tool_and_gate_events_get_the_recorded_arm(self, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUK_ARM", raising=False)
        arms.write_session_arm(tmp_path, "proj", "lean")

        class Fake:
            registered: dict = {}

            def tool(self, *a, **k):
                def reg(fn):
                    self.registered[fn.__name__] = fn
                    return fn
                return reg

        mcp = Fake()
        tool_spans.install_tool_spans(mcp, lambda: tmp_path, lambda: "proj")

        @mcp.tool()
        def check_nfr_gate(task: str, size: str) -> dict:
            return {"blocked": False}

        mcp.registered["check_nfr_gate"]("t", "M")
        got = list(events.read_events(tmp_path, "proj"))
        assert {e["kind"] for e in got} == {"tool", "gate"}
        assert all(e["arm"] == "lean" for e in got)


def _env(root: Path, arm: str = "", **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("YOUK_ARM", "YOUK_ARM_MODE")}
    env.update({"YOUK_ROOT": str(root), "YOUK_CORE_URL": "http://127.0.0.1:1", **extra})
    if arm:
        env["YOUK_ARM"] = arm
    return env


def _run(script: Path, payload: dict, env: dict) -> subprocess.CompletedProcess:
    flags = ["-S"] if script == TAP else []
    return subprocess.run([sys.executable, *flags, str(script)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, timeout=30)


class _Brief(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"brief": "SERVER-BRIEF"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Brief)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class TestSessionStartInjection:
    def _start(self, tmp_path, arm):
        srv = _serve()
        try:
            env = _env(tmp_path, arm, YOUK_CORE_URL=f"http://127.0.0.1:{srv.server_port}")
            return _run(START_HOOK, {"cwd": "/work/proj", "session_id": "s1"}, env)
        finally:
            srv.shutdown()

    def test_full_injects_the_server_brief(self, tmp_path):
        assert self._start(tmp_path, "full").stdout.strip() == "SERVER-BRIEF"

    def test_bare_injects_nothing_but_still_logs_the_session_with_its_arm(self, tmp_path):
        out = self._start(tmp_path, "bare")
        assert out.returncode == 0 and out.stdout == ""
        start = [e for e in events.read_events(tmp_path, "proj") if e["kind"] == "session"]
        assert start and start[0]["arm"] == "bare"

    def test_lean_injects_only_its_own_context_file(self, tmp_path):
        out = self._start(tmp_path, "lean").stdout
        assert "SERVER-BRIEF" not in out
        assert out.strip() == (REPO / "bench" / "arms" / "lean" / "context.md").read_text().strip()

    def test_arm_is_recorded_for_the_server_to_read(self, tmp_path):
        self._start(tmp_path, "lean")
        # the env pin is gone for later readers (the container), so only the file can answer
        assert arms.current_arm(tmp_path, "proj") == "lean"


class TestHookEventsCarryTheArm:
    def test_tap_and_prompt_hook_read_the_arm_from_state_when_no_env_pin(self, tmp_path):
        arms.write_session_arm(tmp_path, "proj", "bare")
        post = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {},
                "cwd": "/work/proj", "session_id": "s1", "tool_use_id": "t1", "duration": 5}
        _run(TAP, post, _env(tmp_path))
        _run(PROMPT_HOOK, {"prompt": "no that's wrong, redo it", "cwd": "/work/proj",
                           "session_id": "s1"}, _env(tmp_path))
        got = list(events.read_events(tmp_path, "proj"))
        assert {e["kind"] for e in got} >= {"tool", "correction"}
        assert all(e.get("arm") == "bare" for e in got), got


class TestBareDisablesGates:
    def _gated_root(self, tmp_path) -> Path:
        root = tmp_path / "root"
        (root / "state").mkdir(parents=True)
        (root / "state" / "kill-criterion-triggered.json").write_text('{"triggered": true}')
        return root

    def _edit(self, root: Path, arm: str) -> dict:
        project = root.parent / "proj"
        project.mkdir(exist_ok=True)
        out = _run(PRE_HOOK, {"tool_name": "Edit", "tool_input": {}, "cwd": str(project)},
                   _env(root, arm))
        return json.loads(out.stdout)

    def test_the_write_gate_denies_full_and_lean_but_not_bare(self, tmp_path):
        root = self._gated_root(tmp_path)
        for arm in ("full", "lean"):
            denied = self._edit(root, arm)
            assert denied["hookSpecificOutput"]["permissionDecision"] == "deny", arm
        assert "hookSpecificOutput" not in self._edit(root, "bare")
