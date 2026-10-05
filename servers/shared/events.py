"""The event ledger: one typed, append-only record of what youk actually did.

Why it exists: nothing recorded per-call usage, so "what delivers value" could not be
answered from data. Hooks and server code emit here; reports read from here.

Content rule (ADR-011, same as the trace metadata): events carry enums, vocabulary names,
numbers and hashed ids. Never free text from the session. A task description, a file path,
a project name or a prompt does not belong in an event. `emit` enforces this by shape, not
by trust: a name must look like an identifier, and session and task ids are hashed.

Storage: state/events/{slug}/{YYYY-MM}.jsonl. Sharded per project and month so no file grows
without bound and readers can skip months. Append-only through locked_jsonl_append: writers
never read first, so concurrent hooks and the server cannot lose each other's lines.

emit never raises and never blocks the caller. A failed write returns False. Instrumentation
that can break the thing it measures would be removed the first time it did.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from jsonl_lock import locked_jsonl_append

SCHEMA_VERSION = 1

# One event line stays small. The cap is a backstop; a line this long means a field got free text.
_MAX_LINE_BYTES = 512
_NAME_RE = re.compile(r"^[A-Za-z0-9_.:/+-]{1,64}$")
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class Kind(StrEnum):
    TOOL = "tool"
    SKILL = "skill"
    GATE = "gate"
    HOOK = "hook"
    CORRECTION = "correction"
    TEST = "test"
    COMMIT = "commit"
    OUTCOME = "outcome"
    SESSION = "session"


class Status(StrEnum):
    OK = "ok"
    FAIL = "fail"
    BLOCK = "block"


def hash_identifier(value: str) -> str:
    """Stable, non-reversible id for grouping. Same function as observability.hash_identifier,
    kept here so shared code does not import from core."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Event:
    kind: str
    name: str
    status: str = Status.OK
    session: str = ""   # hashed on emit
    task: str = ""      # hashed on emit
    arm: str = ""       # experiment arm, a short enum-like word
    src: str = ""       # emitter, e.g. "hook" or "server"
    ms: int | None = None
    n: int | None = None
    tok_in: int | None = None
    tok_out: int | None = None
    v: int = SCHEMA_VERSION
    ts: str = ""
    eid: str = ""


# Every key an event line may carry. Adding a field is a deliberate act and has to be added
# here too; tests/test_events.py fails if the dataclass and this set drift apart.
ALLOWED_KEYS = frozenset(f.name for f in fields(Event))

_INT_FIELDS = ("ms", "n", "tok_in", "tok_out")


class EventRejected(ValueError):
    """An event that breaks the content rule. emit() catches this and returns False."""


def _validate(raw: dict) -> dict:
    unknown = set(raw) - ALLOWED_KEYS
    if unknown:
        raise EventRejected(f"unknown fields: {sorted(unknown)}")
    event = Event(**raw)
    out = asdict(event)
    try:
        out["kind"] = Kind(out["kind"]).value
        out["status"] = Status(out["status"]).value
    except ValueError as exc:
        raise EventRejected(str(exc)) from exc
    if not _NAME_RE.match(str(out["name"])):
        raise EventRejected("name must be a short identifier, not free text")
    for key in ("arm", "src"):
        if out[key] and not _NAME_RE.match(str(out[key])):
            raise EventRejected(f"{key} must be a short identifier")
    for key in _INT_FIELDS:
        val = out[key]
        if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val < 0):
            raise EventRejected(f"{key} must be a non-negative integer")
    for key in ("session", "task"):
        if out[key]:
            out[key] = hash_identifier(str(out[key]))
    out["ts"] = out["ts"] or datetime.now(UTC).isoformat(timespec="microseconds")
    if not out["eid"]:
        basis = "|".join(str(out[k]) for k in ("kind", "name", "session", "task", "ts", "n", "ms"))
        out["eid"] = hash_identifier(basis)
    return {k: v for k, v in out.items() if v not in ("", None)}


def _slug_dir(slug: str) -> str:
    """A safe path component. A slug that is not one is replaced by its hash, so a hostile or
    odd project name can never walk out of state/events/."""
    return slug if _SLUG_RE.match(slug or "") else f"h-{hash_identifier(slug or 'unknown')}"


def events_path(youk_root: Path, slug: str, when: datetime | None = None) -> Path:
    month = (when or datetime.now(UTC)).strftime("%Y-%m")
    return Path(youk_root) / "state" / "events" / _slug_dir(slug) / f"{month}.jsonl"


def emit(youk_root: Path, slug: str, **raw) -> bool:
    """Record one event. Returns True if written. Never raises."""
    try:
        record = _validate(raw)
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
            raise EventRejected("event line too long")
        locked_jsonl_append(events_path(youk_root, slug), line)
        return True
    except Exception:
        return False


def _months_between(since: datetime | None) -> set[str] | None:
    if since is None:
        return None
    since = since.astimezone(UTC)
    now = datetime.now(UTC)
    months, y, m = set(), since.year, since.month
    while (y, m) <= (now.year, now.month):
        months.add(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def read_events(
    youk_root: Path,
    slug: str,
    since: datetime | None = None,
    kinds: set[str] | None = None,
) -> Iterator[dict]:
    """Stream events oldest shard first, one line at a time. Skips unparseable lines (a write
    in flight) and duplicate eids. Memory is bounded by one month of one project."""
    shard_dir = Path(youk_root) / "state" / "events" / _slug_dir(slug)
    if not shard_dir.is_dir():
        return
    wanted = _months_between(since)
    since_iso = since.astimezone(UTC).isoformat(timespec="microseconds") if since else None
    for shard in sorted(shard_dir.glob("*.jsonl")):
        if wanted is not None and shard.stem not in wanted:
            continue
        seen: set[str] = set()
        with shard.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = event.get("eid")
                if eid in seen:
                    continue
                seen.add(eid)
                if kinds and event.get("kind") not in kinds:
                    continue
                if since_iso and event.get("ts", "") < since_iso:
                    continue
                yield event
