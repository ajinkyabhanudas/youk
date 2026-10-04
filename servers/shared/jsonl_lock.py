"""Exclusive-lock append for the JSONL event logs in this initiative.

Protects against concurrent writers interleaving or losing writes to the
same file. Uses flock, not a sidecar .lock file, so a crashed writer can
never leave a stale lock blocking others -- the lock releases automatically
on close or process exit.
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
    checking and writing under one held lock -- a separate check-then-append
    is a TOCTOU race between concurrent callers. Returns True if appended,
    False if the id was already present. Unparseable lines are skipped."""
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
