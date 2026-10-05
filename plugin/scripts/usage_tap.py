#!/usr/bin/env python3
"""Usage tap: turns hook payloads into ledger events, with no help from the model.

One script for PostToolUse, PostToolUseFailure and SessionEnd. Model-reported logging
failed (one skill-invocation record across every session), so usage is captured here,
mechanically, from what the host already sends.

What it records, all as enums, identifiers and numbers (see servers/shared/events.py):
  tool     every matched tool call: name, duration, ok or fail
  skill    a Skill tool call: the skill's name
  test     a Bash command that ran a known test or lint runner: runner enum, exit code
  commit   a Bash command that ran `git commit`: ok or fail
  session  end of session, with the host's exit reason
  hook     this script's own run time, sampled 1 in 10 calls (the latency budget check)

What it never records: the command text, file paths, prompts, tool output.

Never blocks and never prints. Any error exits 0 silently.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

_START = time.perf_counter()
_SHARED = Path(__file__).resolve().parents[2] / "servers" / "shared"
sys.path.insert(0, str(_SHARED))

_RUNNERS = (
    ("pytest", re.compile(r"\b(pytest|py\.test)\b")),
    ("ruff", re.compile(r"\bruff\b")),
    ("npm-test", re.compile(r"\b(npm|yarn|pnpm)\s+(run\s+)?test\b")),
    ("vitest", re.compile(r"\bvitest\b")),
    ("jest", re.compile(r"\bjest\b")),
    ("go-test", re.compile(r"\bgo\s+test\b")),
    ("cargo-test", re.compile(r"\bcargo\s+test\b")),
    ("make-test", re.compile(r"\bmake\s+(test|check|lint)\b")),
)
_COMMIT = re.compile(r"\bgit\s+(?:-[Cc]\s+\S+\s+)*commit\b")
_DRY_RUN = re.compile(r"--dry-run")
_EXIT_CODE = re.compile(r"Exit code (\d+)")
_MAX_RUNNERS = 3
_HOOK_SAMPLE_EVERY = 10


def _youk_root() -> Path | None:
    env = os.environ.get("YOUK_ROOT")
    candidates = [Path(env)] if env else []
    candidates.append(Path.home() / ".claude" / "youk")
    return next((p for p in candidates if p.exists()), None)


def _exit_code(payload: dict, failed: bool) -> int | None:
    response = payload.get("tool_response")
    if isinstance(response, dict) and isinstance(response.get("exit_code"), int):
        return response["exit_code"]
    if failed:
        error = payload.get("error")
        text = error.get("message", "") if isinstance(error, dict) else str(error or "")
        match = _EXIT_CODE.search(text)
        if match:
            return int(match.group(1))
    return None


def _skill_name(tool_input: dict) -> str:
    for key in ("skill", "skill_name", "name"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value.lstrip("/")
    return ""


def _sampled(tool_use_id: str) -> bool:
    digest = hashlib.sha1((tool_use_id or "").encode("utf-8")).digest()
    return digest[0] % _HOOK_SAMPLE_EVERY == 0


def _tool_events(payload: dict, failed: bool) -> list[dict]:
    tool = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    duration = payload.get("duration")
    ms = duration if isinstance(duration, int) and duration >= 0 else None
    status = "fail" if failed else "ok"
    out = [{"kind": "tool", "name": tool[:64], "status": status, "ms": ms}]

    if tool == "Skill":
        name = _skill_name(tool_input)
        if name:
            out.append({"kind": "skill", "name": name[:64], "status": status})

    if tool == "Bash":
        command = str(tool_input.get("command", ""))
        code = _exit_code(payload, failed)
        # A non-zero exit is a fail even if the host delivered it as a normal result.
        cmd_status = "fail" if failed or (code not in (None, 0)) else "ok"
        found = [name for name, rx in _RUNNERS if rx.search(command)][:_MAX_RUNNERS]
        for name in found:
            out.append({"kind": "test", "name": name, "status": cmd_status, "n": code})
        if _COMMIT.search(command) and not _DRY_RUN.search(command):
            out.append({"kind": "commit", "name": "git", "status": cmd_status})
    return out


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    root = _youk_root()
    if root is None:
        return

    from events import emit  # after sys.path is set

    event_name = payload.get("hook_event_name", "")
    slug = Path(payload.get("cwd", "") or ".").name or "unknown"
    common = {
        "session": str(payload.get("session_id", "")),
        "arm": os.environ.get("YOUK_ARM", ""),
        "src": "hook",
    }

    if event_name == "SessionEnd":
        reason = str(payload.get("exit_reason") or payload.get("reason") or "other")
        events = [{"kind": "session", "name": f"end.{reason}"[:64]}]
        always_hook = True
    elif event_name in ("PostToolUse", "PostToolUseFailure"):
        events = _tool_events(payload, failed=event_name == "PostToolUseFailure")
        always_hook = False
    else:
        return

    for event in events:
        emit(root, slug, **common, **event)

    hook_name = {"SessionEnd": "session_end", "PostToolUse": "post_tool_use",
                 "PostToolUseFailure": "post_tool_use_failure"}[event_name]
    if always_hook or _sampled(str(payload.get("tool_use_id", ""))):
        elapsed = int((time.perf_counter() - _START) * 1000)
        emit(root, slug, **common, kind="hook", name=hook_name, ms=elapsed, n=_HOOK_SAMPLE_EVERY
             if not always_hook else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
