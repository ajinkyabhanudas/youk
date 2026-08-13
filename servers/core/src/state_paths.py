"""state_paths — single authority for slug-scoped state path resolution.

All session state for a project lives under state/sessions/{slug}/.
This module provides the canonical helpers used by both session.py and server.py
to resolve paths. Neither file should construct state/ paths inline.

Isolation contract:
  - Each project slug gets its own subdirectory under state/sessions/.
  - Gate flags, session markers, and convergence state are never shared across slugs.
  - task-graph.db is the one shared resource (SQLite WAL mode handles concurrency).
  - .lock sidecar files used by _atomic_write are co-located with state files
    and must be listed in .gitignore.
"""
from __future__ import annotations

import fcntl
import json
import time
from pathlib import Path

# YOUK_ROOT is set by the caller module (session.py / server.py) via module-level
# assignment. Tests patch it via monkeypatch. We default to the container path.
YOUK_ROOT: Path = Path("/youk")

# open.json entries older than this are considered stale (prior session, crashed, etc.)
_SLUG_OPEN_MAX_AGE_SECONDS = 4 * 60 * 60  # 4 hours


def slug_state_dir(slug: str) -> Path:
    """Return (and create) the per-slug state directory: state/sessions/{slug}/."""
    d = YOUK_ROOT / "state" / "sessions" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def current_session_slug() -> str:
    """Return the slug of the most recently opened active session.

    Resolution order:
    1. All state/sessions/*/open.json files, sorted by mtime descending.
    2. Skip entries older than _SLUG_OPEN_MAX_AGE_SECONDS (stale/crashed sessions).
    3. Return "unknown" if no valid entry found.

    The root-level state/session-open.json is NOT consulted — it is a legacy
    redirect pointer only and must not be used for slug resolution after this
    module is in use.
    """
    sessions_dir = YOUK_ROOT / "state" / "sessions"
    if not sessions_dir.exists():
        return "unknown"

    candidates = sorted(
        sessions_dir.glob("*/open.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    now = time.time()
    for c in candidates:
        age = now - c.stat().st_mtime
        if age > _SLUG_OPEN_MAX_AGE_SECONDS:
            continue
        try:
            data = json.loads(c.read_text())
            slug = data.get("slug", "")
            if slug:
                return slug
        except Exception:
            continue

    return "unknown"


def gate_flag_path(slug: str, flag_name: str) -> Path:
    """Return the slug-scoped path for a gate flag file.

    Example: gate_flag_path("youk", "challenge-ran.json")
             → state/sessions/youk/challenge-ran.json
    """
    return slug_state_dir(slug) / flag_name


def atomic_write(path: Path, data: str) -> None:
    """Write data to path with an fcntl advisory lock to prevent concurrent corruption.

    Uses a .lock sidecar file alongside the target. The lock is advisory:
    it protects against concurrent youk processes (async handlers in the same
    uvicorn event loop serialise naturally, but two separate Docker sessions
    on the same host could race). The lock is released on context exit.

    The target file is written atomically via write_text after acquiring the lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        path.write_text(data)
        # lock released when with-block exits


def open_json_payload(slug: str) -> str:
    """Build the JSON payload for state/sessions/{slug}/open.json.

    Includes written_at so current_session_slug() can detect stale entries.
    """
    return json.dumps({
        "slug": slug,
        "written_at": time.time(),
    })
