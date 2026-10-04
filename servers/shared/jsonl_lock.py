"""Exclusive-lock append for the JSONL event logs in this initiative.

Real gap found 2026-10-04: every append_* function across this codebase
(disposition_event.py, domain_scope_event.py, reversal_check.py's
confirm_reversed_pattern, pattern_promotion.py's promote_group) opened its
log file with plain `open(path, "a")` -- no lock. This session itself ran
two concurrent processes (a Codex session and this Claude Code session)
connected to the same youk-core server at once; nothing stops two real
concurrent callers from interleaving writes to the same file today. Not a
future-scale problem -- a present, already-possible correctness gap.

flock (not a separate .lock file) because unlocking is automatic on close/
process exit, so a crashed writer can never leave a stale lock other writers
wait on forever -- the single failure mode a sidecar lock file has that this
avoids by construction.
"""
from __future__ import annotations

import fcntl
from pathlib import Path
from typing import Any


def locked_jsonl_append(path: Path, line: str) -> None:
    """Append `line` (plus a trailing newline) to `path` under an exclusive
    advisory lock held for the duration of the write. Creates parent
    directories if needed. The lock is released automatically when the file
    handle closes (including on an unhandled exception), so a crash never
    leaves a stale lock blocking future writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(line + "\n")
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def locked_append_if_id_absent(path: Path, entry_id: str, line: str) -> bool:
    """Append `line` to `path` only if no existing row has "id" == entry_id,
    with the presence-check and the write happening under the SAME held
    lock. Plain locked_jsonl_append doesn't close this gap: two concurrent
    callers could both pass a separate has-id check before either writes,
    duplicating a real reversal/promotion despite its deterministic id
    existing precisely to prevent that. Returns True if it appended, False
    if the id was already present (no-op, matching the prior
    check-then-append callers' semantics). A line that fails to parse is
    skipped, same resilience discipline as every other reader of these
    files."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            for existing_line in f:
                if not existing_line.strip():
                    continue
                try:
                    if json.loads(existing_line).get("id") == entry_id:
                        return False
                except json.JSONDecodeError:
                    continue
            f.write(line + "\n")
            f.flush()
            return True
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def locked_jsonl_read_all(path: Path) -> list[dict[str, Any]]:
    """Read every line of `path` as JSON under a shared (read) advisory
    lock, so a reader never observes a partially-written line from a
    concurrent locked_jsonl_append call. Returns [] if the file doesn't
    exist -- a missing file is 'no real entries yet', never an error."""
    import json

    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            lines = f.readlines()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    result = []
    for line in lines:
        if not line.strip():
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result
