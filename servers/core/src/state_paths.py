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
import os
import tempfile
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

# YOUK_ROOT is set by the caller module (session.py / server.py) via module-level
# assignment. Tests patch it via monkeypatch. We default to the container path.
YOUK_ROOT: Path = Path("/youk")
from youk_paths import HOST_ROOT
HOST_HOME: Path = Path("/host-home")

# open.json entries older than this are considered stale (prior session, crashed, etc.)
_SLUG_OPEN_MAX_AGE_SECONDS = 4 * 60 * 60  # 4 hours

# Actor extension (defaulted off): every session carries an actor, "founder" unless
# explicitly set otherwise. Unrecognised values fall back to "founder" rather than
# raising — a malformed or future actor value must never block a session from starting.
_VALID_ACTORS = frozenset({"founder", "member"})
_DEFAULT_ACTOR = "founder"


def resolve_actor(raw: str | None) -> str:
    """Validate a candidate actor value, falling back to the default on anything else."""
    if raw in _VALID_ACTORS:
        return raw
    return _DEFAULT_ACTOR


def session_actor(slug: str) -> str:
    """Return the actor recorded for slug's current open session, defaulting to "founder".

    Old sessions written before this field existed (or any read/parse failure) resolve
    to the default — this is intentionally the same fail-safe shape as current_session_slug().
    """
    open_file = slug_state_dir(slug) / "open.json"
    if not open_file.exists():
        return _DEFAULT_ACTOR
    try:
        data = json.loads(open_file.read_text())
        return resolve_actor(data.get("actor"))
    except Exception:
        return _DEFAULT_ACTOR


# Tenant scope, defaulted off. The default scope (no scope configured) uses the
# flat state/sessions/{slug}/ layout unchanged — this is what makes the extension
# zero-migration for every existing single-tenant install. Only a NON-default scope
# gets a nested state/scopes/{scope}/sessions/{slug}/ tree, so isolation is a
# directory boundary rather than a value that could be filtered on incorrectly.
_DEFAULT_SCOPE = "_default"


def resolve_scope(raw: str | None) -> str:
    """Normalise a candidate tenant-scope value, falling back to the default scope."""
    if raw and raw.strip():
        return raw.strip()
    return _DEFAULT_SCOPE


def scope_state_root(scope: str | None = None) -> Path:
    """Root state directory for a tenant scope.

    The default scope resolves to YOUK_ROOT/state (today's layout, untouched).
    Any other scope resolves to YOUK_ROOT/state/scopes/{scope}/ — a separate
    subtree, so a session in one scope cannot reach another's state by any
    relative-path mistake.
    """
    resolved = resolve_scope(scope)
    if resolved == _DEFAULT_SCOPE:
        return YOUK_ROOT / "state"
    return YOUK_ROOT / "state" / "scopes" / resolved


def slug_state_dir(slug: str, scope: str | None = None) -> Path:
    """Return the per-slug state directory for a scope without creating it.

    Default scope (the common case, and every call site before this change):
    state/sessions/{slug}/, identical to pre-scope behaviour. A configured
    scope: state/scopes/{scope}/sessions/{slug}/.
    """
    return scope_state_root(scope) / "sessions" / slug


def ensure_slug_state_dir(slug: str, scope: str | None = None) -> Path:
    """Create and return the per-slug state directory for a write operation."""
    directory = slug_state_dir(slug, scope)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def current_session_slug(scope: str | None = None) -> str:
    """Return the slug of the most recently opened active session within a scope.

    Resolution order:
    1. All sessions/*/open.json files under this scope's root, sorted by mtime descending.
    2. Skip entries older than _SLUG_OPEN_MAX_AGE_SECONDS (stale/crashed sessions).
    3. Return "unknown" if no valid entry found.

    Scopes are resolved independently — a session open in one scope is invisible to
    current_session_slug() called for a different scope, by construction (different
    glob root), not by a filter that could be forgotten.

    The root-level state/session-open.json is NOT consulted — it is a legacy
    redirect pointer only and must not be used for slug resolution after this
    module is in use.
    """
    sessions_dir = scope_state_root(scope) / "sessions"
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


def skills_invoked_log_path(slug: str, scope: str | None = None) -> Path:
    """Path to this session's mechanically-logged skill invocations.

    Written by log_skill_invocation() (server.py) immediately after each
    route_to_skill call — the write-authorized half, since route_to_skill itself
    runs in the read-only youk-code container. Read and cleared by session_end
    as a fallback when the self-reported skills_used argument is empty or
    incomplete (self-reporting at session close is unreliable; this is checkable).
    """
    return slug_state_dir(slug, scope) / "skills-invoked.jsonl"


def gate_flag_path(slug: str, flag_name: str, scope: str | None = None) -> Path:
    """Return the slug-scoped path for a gate flag file, within a tenant scope.

    Example: gate_flag_path("youk", "challenge-ran.json")
             → state/sessions/youk/challenge-ran.json   (default scope, unchanged)
    """
    return slug_state_dir(slug, scope) / flag_name


def _locked_write(path: Path, data: str) -> None:
    """Replace path while its sidecar lock is held by the caller."""
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def atomic_write(path: Path, data: str) -> None:
    """Crash-safe replacement write protected by an fcntl advisory lock.

    Uses a .lock sidecar file alongside the target. The lock is advisory:
    it protects against concurrent youk processes (async handlers in the same
    uvicorn event loop serialise naturally, but two separate Docker sessions
    on the same host could race). The lock is released on context exit.

    A temporary file is fsynced and replaced while the lock is held. Readers therefore
    see either the old complete file or the new complete file, never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        _locked_write(path, data)


def update_json(path: Path, update: Callable[[Any], Any]) -> Any:
    """Atomically apply update to a JSON value and return the updated value.

    The read and replacement occur under one lock so concurrent read-modify-write
    callers cannot silently discard each other's update.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        except (OSError, json.JSONDecodeError):
            current = None
        updated = update(current)
        _locked_write(path, json.dumps(updated))
        return updated


def open_json_payload(slug: str) -> str:
    """Build the JSON payload for state/sessions/{slug}/open.json.

    Includes written_at so current_session_slug() can detect stale entries.
    """
    return json.dumps({
        "slug": slug,
        "written_at": time.time(),
    })


def resolve_project_path(host_path: str) -> Path:
    """Translate a host-absolute project path to a path accessible inside this container.

    The container has fixed mount points:
      /youk  = host YOUK_DIR  (e.g. ~/.claude/youk)
      /claude = host CLAUDE_DIR (e.g. ~/.claude)

    Two fallback mechanisms (tried in order):
    1. state/path-map.env — written by install.sh; maps YOUK_HOST_DIR and CLAUDE_HOST_DIR
    2. /host-home         — host $HOME mounted :ro (requires updated install.sh re-run)
    """
    p = Path(host_path)
    if p.exists():
        return p  # already accessible (local dev, or running outside Docker)

    path_map_file = YOUK_ROOT / "state" / "path-map.env"
    if path_map_file.exists():
        try:
            mapping: dict[str, str] = {}
            for line in path_map_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    mapping[key.strip()] = val.strip()

            youk_host = mapping.get("YOUK_HOST_DIR", "")
            # HOST_CONFIG_DIR is the host-neutral key; CLAUDE_HOST_DIR is what installs made
            # before host-neutral paths wrote.
            host_config = mapping.get("HOST_CONFIG_DIR") or mapping.get("CLAUDE_HOST_DIR", "")

            if youk_host and host_path.startswith(youk_host):
                relative = host_path[len(youk_host):].lstrip("/")
                candidate = YOUK_ROOT / relative if relative else YOUK_ROOT
                if candidate.exists():
                    return candidate

            if host_config and host_path.startswith(host_config):
                relative = host_path[len(host_config):].lstrip("/")
                candidate = HOST_ROOT / relative if relative else HOST_ROOT
                if candidate.exists():
                    return candidate
        except Exception:
            pass

    if HOST_HOME.exists():
        for prefix in ("/Users/", "/home/"):
            if host_path.startswith(prefix):
                rest = host_path[len(prefix):]
                rest_parts = Path(rest).parts
                if len(rest_parts) > 1:
                    relative = Path(*rest_parts[1:])
                    candidate = HOST_HOME / relative
                    if candidate.exists():
                        return candidate

    return p  # return as-is; callers check .exists() and degrade gracefully
