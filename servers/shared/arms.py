"""Experiment arms: which youk configuration a session runs, and how every emitter learns it.

Arms: `full` is youk as it is today, `lean` the minimal context (S11 writes it), `bare` injects
nothing and runs ungated while events still flow, so it is the baseline.

Why a state file and not only an env var: the hooks run on the host and see YOUK_ARM, but the
server runs in a container with no such variable, so its events (gates, M+ task counts) would
have no arm and per-arm rates could not be computed. The SessionStart hook writes the arm
to state/session-arm/{slug} and every emitter reads it back through current_arm().

One file per project slug, replaced whole: no read-modify-write, so concurrent hooks cannot lose
each other's data. Limit: two sessions open in the same project at once share the slot, and the
later start wins. The battery runs one session per worktree, so it is not affected.

Stdlib only and import-light: usage_tap imports this on every tool call under `python3 -S`.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from events import _slug_dir

ARMS = ("full", "lean", "bare")
DEFAULT_ARM = "full"
ARM_ENV = "YOUK_ARM"
# Set to "randomize" to assign by session hash. Off by default so day-to-day sessions are never
# put in the ungated arm by chance; the battery pins the arm per run through YOUK_ARM instead.
MODE_ENV = "YOUK_ARM_MODE"


def override() -> str:
    """The arm pinned by YOUK_ARM, or "" if unset or not a known arm."""
    value = os.environ.get(ARM_ENV, "").strip().lower()
    return value if value in ARMS else ""


def assign_arm(session_id: str) -> str:
    """The arm for a new session. Override wins; then hash if randomizing; else the default."""
    pinned = override()
    if pinned:
        return pinned
    if os.environ.get(MODE_ENV, "").lower() != "randomize":
        return DEFAULT_ARM
    digest = hashlib.sha256(f"{session_id}:arm".encode()).digest()
    return ARMS[digest[0] % len(ARMS)]


def _arm_file(root: Path, slug: str) -> Path:
    return Path(root) / "state" / "session-arm" / _slug_dir(slug)


def write_session_arm(root: Path, slug: str, arm: str) -> bool:
    """Record the arm of the session now open in this project. Never raises."""
    try:
        if arm not in ARMS:
            return False
        path = _arm_file(root, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(arm)
        tmp.replace(path)
        return True
    except Exception:
        return False


def current_arm(root: Path | None, slug: str) -> str:
    """The arm events should carry: the pinned override, else the recorded session arm, else ""
    (an event from before arms existed or outside an experiment carries none)."""
    pinned = override()
    if pinned or root is None:
        return pinned
    try:
        arm = _arm_file(root, slug).read_text().strip()
        return arm if arm in ARMS else ""
    except Exception:
        return ""


def gates_active(arm: str) -> bool:
    """`bare` runs without youk's blocking gates. An unknown or empty arm keeps them on."""
    return arm != "bare"


def arm_context(repo_root: Path, arm: str) -> str:
    """Text the SessionStart hook injects for `lean`. Empty for `bare`; `full` injects the server
    brief instead, so it has no file."""
    if arm != "lean":
        return ""
    try:
        return (Path(repo_root) / "bench" / "arms" / arm / "context.md").read_text().strip()
    except Exception:
        return ""
