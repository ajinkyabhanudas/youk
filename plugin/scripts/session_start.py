#!/usr/bin/env python3
"""
SessionStart hook (CIR-155) — fires once per Claude Code session, before the
model's first turn, and delivers the real youk session-start brief as context.

Why this exists: Claude Code's hooks.json previously had no SessionStart entry at
all. The only thing delivering session context was a CLAUDE.md instruction telling
the model to call `youk-core.session_start(project_dir)` itself — prose with zero
technical backstop, the exact weakness CIR-150 closed for Edit/Write via a real
PreToolUse gate. scripts/host_inventory.py's structural scanner correctly flagged
this as session_context:claude-code "wired": false.

Claude Code's own `mcp_tool` hook type is documented as inert at SessionStart (MCP
servers aren't attached to the session yet), so this can't call the MCP tool the
way Codex's SessionStart hook does. Instead it makes a plain HTTP GET directly to
the already-running youk-core server's /session-start-hook route (server.py), the
same no-MCP-handshake precedent /agent-guards already established for callers that
can't do an MCP handshake. That route runs the exact same start_session() codepath
session_start's own MCP tool wraps — not a second implementation.

Never blocks session start: SessionStart hooks can't block on any exit code, and
this additionally degrades to silent no-output if the server is unreachable (e.g.
still booting, or not installed) so a slow/absent server never delays the session.

A project's CLAUDE.md may still instruct the model to call `youk-core.session_start`
manually (older template, or a resume-after-compaction guard). That's safe alongside
this hook: start_session() recognizes a same-session duplicate call within 90 seconds
(session.py's _is_recent_duplicate_session_start) and skips re-running its mutating
bookkeeping on the second call.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "servers", "shared"))
from youk_hook_utils import read_stdin

_YOUK_CORE_URL = os.environ.get("YOUK_CORE_URL", "http://127.0.0.1:8001")
_TIMEOUT_SECONDS = 8


def _emit_session_start(data: dict, cwd: str) -> None:
    """Record the session opening in the ledger. Never raises, never blocks."""
    try:
        from pathlib import Path

        from events import emit
        from youk_hook_utils import youk_root

        root = youk_root()
        if root is None:
            return
        source = str(data.get("source") or "startup")
        emit(root, Path(cwd).name or "unknown", kind="session", name=f"start.{source}"[:64],
             session=str(data.get("session_id", "")), arm=os.environ.get("YOUK_ARM", ""), src="hook")
    except Exception:
        pass


def main() -> None:
    data = read_stdin()
    cwd = data.get("cwd", "")
    if not cwd:
        sys.exit(0)

    _emit_session_start(data, cwd)

    query = urllib.parse.urlencode({"project_dir": cwd})
    url = f"{_YOUK_CORE_URL}/session-start-hook?{query}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Server unreachable/still booting — never block or warn; the
        # pre-existing CLAUDE.md manual-call path (if any) still covers this.
        sys.exit(0)

    brief = payload.get("brief", "")
    if brief:
        print(brief)
    sys.exit(0)


if __name__ == "__main__":
    main()
