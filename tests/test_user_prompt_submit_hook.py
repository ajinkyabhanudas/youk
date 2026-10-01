"""Tests for the user_prompt_submit.py UserPromptSubmit hook entrypoint
itself -- stdin in, stdout out, via a real subprocess, same approach as
tests/test_pre_tool_use_hook.py.

CIR-155 (second finding): confirming Codex's real UserPromptSubmit payload
shape (developers.openai.com/codex/hooks, 2026) surfaced that this hook read
a "user_prompt" stdin field that neither Claude Code nor Codex actually
sends -- both send "prompt". That meant every ambient-intelligence check in
this hook (session-end detection, M+ task detection, correction capture) was
silently operating on an empty string in real sessions on both hosts, not
just Codex. This file is the regression test that would have caught it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
_HOOK = _REPO / "plugin" / "scripts" / "user_prompt_submit.py"


def _run_hook(payload: dict, youk_root: Path) -> dict:
    (youk_root / "state").mkdir(parents=True, exist_ok=True)
    full_env = dict(os.environ)
    full_env["YOUK_ROOT"] = str(youk_root)
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        env=full_env,
    )
    return json.loads(result.stdout)


class TestRealStdinFieldIsPrompt:
    def test_session_end_signal_fires_from_the_real_prompt_field(self, tmp_path):
        """"prompt" is the real field name on both hosts' UserPromptSubmit
        payload -- a short closing phrase there must trigger the session-end
        nudge."""
        out = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": "", "prompt": "ok thanks"},
            tmp_path,
        )
        context = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "Session-end detected" in context

    def test_legacy_user_prompt_field_is_not_what_either_host_sends(self, tmp_path):
        """Regression guard: a payload shaped with the old, wrong field name
        must NOT trigger the session-end nudge -- proving the hook is reading
        "prompt", not silently falling back to a key nobody sends."""
        out = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": "", "user_prompt": "ok thanks"},
            tmp_path,
        )
        context = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        assert "Session-end detected" not in context

    def test_response_envelope_names_the_hook_event(self, tmp_path):
        """Codex's documented UserPromptSubmit response shape includes
        hookEventName in hookSpecificOutput (developers.openai.com/codex/hooks);
        Claude Code tolerates it being present."""
        out = _run_hook(
            {"cwd": str(tmp_path), "transcript_path": "", "prompt": "ok thanks"},
            tmp_path,
        )
        assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
