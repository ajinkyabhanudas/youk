"""Cheap, frequent save points between the heavy checkpoints (compact_context,
task_checkpoint, session_end).

Those write a full brief and only fire at big moments — after a commit, every
8 calls, at session boundaries. Between them, anything decided only in the live
conversation is invisible to a fresh session and gone entirely if the agent
switches (Claude to Codex or back) or the session ends without warning, e.g. a
usage limit with no advance signal.

This is the gap-filler: a one-line note, cheap enough to write on every
non-trivial decision, surfaced automatically at the next brief and then
consumed — so the loss window shrinks from "since the last full checkpoint" to
"since the last note," which callers control directly.

Same three properties as comprehension_digest.py, and for the same reasons:
project-scoped (not session-scoped, so a fresh session/agent can see it),
render marks rather than deletes (an interrupted read must not destroy the
payload), and oversize input is rejected rather than truncated (this is a
save point, not a transcript log).
"""
from __future__ import annotations

import fcntl
import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/shared")
from schemas import ErrorType  # noqa: E402

MAX_NOTE = 280
MAX_RECORDS = 200


def checkpoint_path(youk_root: Path, slug: str) -> Path:
    """Resolve the note-log path for a project slug. Does not create anything."""
    return youk_root / "knowledge" / "projects" / slug / "turn-checkpoint.jsonl"


@contextmanager
def _locked(path: Path):
    """Hold an exclusive lock across a full read-modify-write cycle.

    Two agents (Claude, Codex) calling checkpoint_now near-simultaneously is the
    normal case this store exists for, not an edge case — a lock only around the
    write (as state_paths.atomic_write does) still lets both read the same stale
    state first and the second writer silently drops the first note. The lock has
    to span read through write to actually prevent that.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            pass  # lock released when the `with` block exits


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def _prune(records: list[dict]) -> list[dict]:
    """Drop oldest consumed records past the bound. Unconsumed records are exempt —
    pruning one would silently discard a save point nobody has read yet."""
    if len(records) <= MAX_RECORDS:
        return records
    unconsumed = [r for r in records if not r.get("consumed")]
    consumed = [r for r in records if r.get("consumed")]
    keep = max(0, MAX_RECORDS - len(unconsumed))
    return unconsumed + consumed[-keep:] if keep else unconsumed


def write_note(youk_root: Path, slug: str, note: str, agent: str = "", session_slug: str = "") -> dict:
    """Record one save-point note. Returns {ok, ...} or {ok: False, error_type, error}.

    note: the current sub-goal or decision, in one line — not a transcript excerpt.
    agent: which agent wrote this ("claude" | "codex" | ""), so a receiving session
    knows whether it's reading its own trail or a handoff from the other agent.
    """
    note = note.strip()
    if not note:
        return {"ok": False, "error_type": ErrorType.INPUT, "error": "note is empty"}
    if len(note) > MAX_NOTE:
        return {
            "ok": False,
            "error_type": ErrorType.INPUT,
            "error": (
                f"note is {len(note)} chars, over the {MAX_NOTE} cap. "
                "Write the current sub-goal or decision, not a transcript excerpt."
            ),
        }

    path = checkpoint_path(youk_root, slug)
    try:
        with _locked(path):
            records = _read(path)
            records.append({
                "note": note,
                "agent": agent,
                "session_slug": session_slug,
                "ts": datetime.now(UTC).isoformat(),
                "consumed": False,
            })
            _write(path, _prune(records))
    except OSError as exc:
        return {"ok": False, "error_type": ErrorType.SYSTEM, "error": f"checkpoint write failed: {exc}"}

    return {
        "ok": True,
        "written": True,
        "pending": sum(1 for r in records if not r.get("consumed")),
        "state_written": [f"knowledge/projects/{slug}/turn-checkpoint.jsonl"],
    }


def pending_notes(youk_root: Path, slug: str) -> list[dict]:
    """Unconsumed notes, oldest first. Read-only — safe for a peek without marking."""
    return [r for r in _read(checkpoint_path(youk_root, slug)) if not r.get("consumed")]


def render_and_consume(youk_root: Path, slug: str) -> dict:
    """Render pending notes as brief-ready lines and mark them consumed.

    Called from build_brief on full-mode builds (session_start, compact_context,
    task_checkpoint) — the same points that already rebuild from contracts.md and
    decisions.md. Empty pending renders to no lines: most checkpoints will have
    nothing to add, and that's the common case, not a gap.
    """
    path = checkpoint_path(youk_root, slug)
    try:
        with _locked(path):
            records = _read(path)
            items = [r for r in records if not r.get("consumed")]
            if not items:
                return {"ok": True, "lines": [], "item_count": 0}

            lines = []
            for r in items:
                tag = f"[{r['agent']}] " if r.get("agent") else ""
                lines.append(f"- {tag}{r['note']}")

            for r in records:
                if not r.get("consumed"):
                    r["consumed"] = True
            _write(path, _prune(records))
    except OSError as exc:
        return {"ok": False, "error_type": ErrorType.SYSTEM, "error": f"checkpoint write failed after render: {exc}"}

    return {
        "ok": True,
        "lines": lines,
        "item_count": len(items),
        "state_written": [f"knowledge/projects/{slug}/turn-checkpoint.jsonl"],
    }
