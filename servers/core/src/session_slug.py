"""Session slug resolution — shared utility for challenge gate correlation.

Both mark_challenge_ran and check_challenge_gate need to agree on the slug
that identifies the current session. This module provides a single source
of truth so both always resolve the same value.
"""
from __future__ import annotations
import json
from pathlib import Path


def get_session_slug(youk_root: Path) -> str:
    """Return a stable session identifier for challenge-ran.json correlation.

    Reads session-open.json first (legacy). Falls back to session_counter from
    session.json as a string. Returns "unknown" only when both files are missing.
    """
    open_file = youk_root / "state" / "session-open.json"
    if open_file.exists():
        try:
            return json.loads(open_file.read_text()).get("slug", "unknown")
        except Exception:
            pass
    session_file = youk_root / "state" / "session.json"
    if session_file.exists():
        try:
            counter = json.loads(session_file.read_text()).get("session_counter")
            if counter is not None:
                return f"session-{counter}"
        except Exception:
            pass
    return "unknown"
