"""Session slug resolution — shared utility for challenge gate correlation.

Both mark_challenge_ran and check_challenge_gate need to agree on the slug
that identifies the current session. This module provides a single source
of truth so both always resolve the same value.

After the slug-scoped state isolation change, slug resolution uses
state_paths.current_session_slug() which reads from state/sessions/*/open.json
(per-slug, written_at-gated). The legacy session-open.json at root is a redirect
pointer only and must not be parsed for the slug value.
"""
from __future__ import annotations
from pathlib import Path
import state_paths as _sp


def get_session_slug(youk_root: Path) -> str:
    """Return a stable session identifier for challenge-ran.json correlation.

    Reads from state/sessions/*/open.json (slug-scoped, most recent active entry).
    Returns "unknown" only when no active session open.json exists.
    """
    _sp.YOUK_ROOT = youk_root
    return _sp.current_session_slug()
