"""Persistence for the comprehension channel (output_channels.ComprehensionDigest).

output_channels defines the two-channel view but holds no state, so its pacing —
"accrue across a task, emit once at a boundary" — had nowhere to live and nothing
ever called it. This is that store.

Three properties the design turns on:

Project-scoped, not slug-scoped. Every session gets a fresh slug, so a file under
state/sessions/{slug}/ would be invisible to the next session and the resume case
would silently never fire. That is the same writer/reader path mismatch that
orphaned every gate write in this repo until PR #109.

Render marks, never deletes. An interrupted session or a model switch leaves its
un-surfaced items sitting in the file for whoever picks the work up next. Deleting
on read would destroy exactly the payload the store exists to carry, and would
reintroduce the write/consume ambiguity where absence cannot distinguish "never
written" from "written and consumed".

Rejection, not truncation, on oversize input. An append-only free-text store that a
model writes to on its own initiative is a latent transcript log, which the platform
forbids. A cap that truncates would silently accept a transcript-shaped payload and
store it anyway; a cap that rejects keeps the store what it claims to be.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/shared")
from output_channels import CompItem, ComprehensionDigest, Load  # noqa: E402
from schemas import ErrorType  # noqa: E402

# A takeaway is one mental-model update, not a paragraph. The context is a pointer
# (a file, a decision), not a description. Both are enforced by rejection.
MAX_TAKEAWAY = 280
MAX_CONTEXT = 120

# Surfaced records are kept for history but pruned oldest-first past this bound.
# Un-surfaced records are NEVER pruned — they are the resume payload.
MAX_RECORDS = 1000


def digest_path(youk_root: Path) -> Path:
    """Resolve the digest path. Does not create anything — resolution is not a write."""
    return youk_root / "state" / "comprehension-digest.jsonl"


def _read(path: Path) -> list[dict]:
    """Load all records. A corrupt line is skipped rather than failing the whole read:
    one bad append must not make the remaining resume payload unreachable."""
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
    """Drop the oldest surfaced records once over the bound. Un-surfaced records are
    exempt: pruning one would silently discard something nobody has read yet."""
    if len(records) <= MAX_RECORDS:
        return records
    unsurfaced = [r for r in records if not r.get("surfaced")]
    surfaced = [r for r in records if r.get("surfaced")]
    keep = max(0, MAX_RECORDS - len(unsurfaced))
    return unsurfaced + surfaced[-keep:] if keep else unsurfaced


def admit(
    youk_root: Path,
    kind: str,
    takeaway: str,
    context: str = "",
    session_slug: str = "",
) -> dict:
    """Record one load-bearing item. Returns {ok, ...} or {ok: False, error_type, error}.

    Deduplicates on (kind, takeaway) within the un-surfaced set, so a repeated call
    during a retry does not double-enter the same item. An identical takeaway that was
    already surfaced is allowed back in — the same lesson recurring later is signal.
    """
    valid_kinds = {k.value for k in Load}
    if kind not in valid_kinds:
        return {
            "ok": False,
            "error_type": ErrorType.INPUT,
            "error": f"kind must be one of {sorted(valid_kinds)}; got {kind!r}",
        }

    takeaway = takeaway.strip()
    if not takeaway:
        return {"ok": False, "error_type": ErrorType.INPUT, "error": "takeaway is empty"}
    if len(takeaway) > MAX_TAKEAWAY:
        return {
            "ok": False,
            "error_type": ErrorType.INPUT,
            "error": (
                f"takeaway is {len(takeaway)} chars, over the {MAX_TAKEAWAY} cap. "
                "Rewrite it as one mental-model update — this store holds extracted "
                "takeaways, not transcript."
            ),
        }
    if len(context) > MAX_CONTEXT:
        return {
            "ok": False,
            "error_type": ErrorType.INPUT,
            "error": f"context is {len(context)} chars, over the {MAX_CONTEXT} cap",
        }

    path = digest_path(youk_root)
    records = _read(path)

    for r in records:
        if not r.get("surfaced") and r.get("kind") == kind and r.get("takeaway") == takeaway:
            return {"ok": True, "admitted": False, "reason": "duplicate of a pending item"}

    records.append({
        "kind": kind,
        "takeaway": takeaway,
        "context": context,
        "session_slug": session_slug,
        "ts": datetime.now(UTC).isoformat(),
        "surfaced": False,
    })

    try:
        _write(path, _prune(records))
    except OSError as exc:
        return {"ok": False, "error_type": ErrorType.SYSTEM, "error": f"digest write failed: {exc}"}

    pending_count = sum(1 for r in records if not r.get("surfaced"))
    return {
        "ok": True,
        "admitted": True,
        "pending": pending_count,
        "state_written": ["state/comprehension-digest.jsonl"],
    }


def pending(youk_root: Path) -> list[dict]:
    """Un-surfaced records, oldest first. Read-only — safe to call for a resume peek."""
    return [r for r in _read(digest_path(youk_root)) if not r.get("surfaced")]


def render(youk_root: Path, mark_surfaced: bool = True) -> dict:
    """Render the pending items as the paced digest.

    Empty pending renders to an empty string: nothing load-bearing happened is a valid
    and common outcome, and manufacturing teaching where none occurred is the failure
    this channel exists to avoid.
    """
    path = digest_path(youk_root)
    records = _read(path)
    items = [r for r in records if not r.get("surfaced")]

    digest = ComprehensionDigest([
        CompItem(kind=Load(r["kind"]), takeaway=r["takeaway"], context=r.get("context", ""))
        for r in items
        if r.get("kind") in {k.value for k in Load}
    ])
    view = digest.render()

    result: dict = {"ok": True, "view": view, "item_count": len(items)}

    # Carry which sessions the items came from: a digest rendered in a later session is
    # a handoff, and the reader should know it is reading someone else's leftovers.
    origins = sorted({r.get("session_slug", "") for r in items if r.get("session_slug")})
    if origins:
        result["origin_sessions"] = origins

    if mark_surfaced and items:
        for r in records:
            if not r.get("surfaced"):
                r["surfaced"] = True
        try:
            _write(path, _prune(records))
        except OSError as exc:
            return {
                "ok": False,
                "error_type": ErrorType.SYSTEM,
                "error": f"digest write failed after render: {exc}",
            }
        result["state_written"] = ["state/comprehension-digest.jsonl"]

    return result
