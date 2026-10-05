"""post_tool_use reads the host's real payload field, `tool_response`.

It used to read `tool_result`, which the host never sends, so the saved "last signal" from
command output was always empty. For Bash the real field is a dict, not a string.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
HOOK = REPO / "plugin" / "scripts" / "post_tool_use.py"


def _run(tmp_path, tool_name, tool_input, **payload_extra) -> dict:
    root = tmp_path / "youk"
    (root / "state").mkdir(parents=True)
    payload = {"hook_event_name": "PostToolUse", "tool_name": tool_name, "tool_input": tool_input,
               "cwd": "/work/proj", "session_id": "s", **payload_extra}
    subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                   capture_output=True, env={**os.environ, "YOUK_ROOT": str(root)}, timeout=30)
    return json.loads((root / "state" / "sessions" / "proj" / "active_task.json").read_text())


class TestToolResponse:
    def test_bash_stdout_last_line_becomes_the_signal(self, tmp_path):
        state = _run(tmp_path, "Bash", {"command": "pytest"},
                     tool_response={"stdout": "collecting\n.....\n5 passed in 0.3s\n", "exit_code": 0})
        assert state["last_signal"] == "5 passed in 0.3s"

    def test_stderr_is_used_when_stdout_is_empty(self, tmp_path):
        state = _run(tmp_path, "Bash", {"command": "make"},
                     tool_response={"stdout": "", "stderr": "make: *** No rule to make target", "exit_code": 2})
        assert state["last_signal"] == "make: *** No rule to make target"

    def test_a_plain_string_response_still_works(self, tmp_path):
        state = _run(tmp_path, "Bash", {"command": "ls"}, tool_response="a\nb\nlast line")
        assert state["last_signal"] == "last line"

    def test_the_old_tool_result_key_is_still_read_as_a_fallback(self, tmp_path):
        state = _run(tmp_path, "Bash", {"command": "ls"}, tool_result="old\nformat")
        assert state["last_signal"] == "format"

    def test_a_dict_with_no_text_field_gives_no_signal_and_does_not_crash(self, tmp_path):
        state = _run(tmp_path, "Bash", {"command": "true"}, tool_response={"exit_code": 0})
        assert state["last_signal"] == ""
