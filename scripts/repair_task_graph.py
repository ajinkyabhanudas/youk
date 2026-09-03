#!/usr/bin/env python3
"""Repair task-graph.db rows created by the routing-breadcrumb path mismatch.

Before the fix in server.py, the nfr and challenge gate mirrors read
state/routing-breadcrumb.json while route_task wrote
state/sessions/{slug}/routing-breadcrumb.json. The read always missed, both mirrors
fell back to `task[:40]`, and set_gate's INSERT OR IGNORE created a stub task row
keyed on the truncated task text instead of route_task's sha1 id.

Every youk install that ran an M+ task before the fix has these rows. They are
identifiable without guesswork: a stub is exactly a row where id == label, because
create_task_graph always writes a 12-char sha1 id alongside a full-text label.

The repair deliberately does not try to match a stub back to the real task row it
should have updated. The stub id is a truncation of the task text passed to the gate,
which is often a paraphrase of the real row's label rather than a prefix of it, so any
matching rule is a guess that can silently merge two different tasks.

What it does instead:

  1. Deletes stubs with done=1. They are complete, carry no edges, and reference
     nothing, so they hold no actionable information.
  2. Clears challenge_cleared, nfr_cleared and unblocked on stubs with done=0, and
     marks them stale. Those flags were written on behalf of a different task and are
     meaningless here. Clearing unblocked is what stops next_task serving a phantom:
     the mirror only ever wrote to stub ids, so before this repair a stub was the only
     kind of row that could become actionable.

Run with --apply to write. Without it, prints the plan and changes nothing.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "state" / "task-graph.db"

# A stub is a row whose id is its own label. create_task_graph always supplies a
# 12-char sha1 id and a separate full-text label, so a real task never matches this.
STUB_PREDICATE = "id = label"


def snapshot(db: Path) -> Path:
    """Copy the db next to itself, stamped. Safe to call repeatedly."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db.with_name(f"{db.name}.pre-repair-{stamp}")
    shutil.copy2(db, dest)
    return dest


def plan(conn: sqlite3.Connection) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """Return (stubs to delete, stubs to defuse) without modifying anything."""
    delete = conn.execute(
        f"SELECT id, project FROM tasks WHERE {STUB_PREDICATE} AND done = 1 ORDER BY id"
    ).fetchall()
    defuse = conn.execute(
        f"SELECT id, project, challenge_cleared, nfr_cleared, unblocked "
        f"FROM tasks WHERE {STUB_PREDICATE} AND done = 0 ORDER BY id"
    ).fetchall()
    return delete, defuse


def referenced_by_edges(conn: sqlite3.Connection) -> list[str]:
    """Stub ids that appear in the edge DAG. Deleting one of these would orphan an edge."""
    rows = conn.execute(
        f"""SELECT DISTINCT t.id FROM tasks t
            JOIN edges e ON e.parent_id = t.id OR e.child_id = t.id
            WHERE {STUB_PREDICATE} AND t.done = 1"""
    ).fetchall()
    return [r[0] for r in rows]


def apply(conn: sqlite3.Connection) -> dict:
    deleted = conn.execute(
        f"DELETE FROM tasks WHERE {STUB_PREDICATE} AND done = 1"
    ).rowcount
    defused = conn.execute(
        f"""UPDATE tasks
            SET challenge_cleared = 0, nfr_cleared = 0, unblocked = 0, stale = 1
            WHERE {STUB_PREDICATE} AND done = 0"""
    ).rowcount
    conn.commit()
    return {"deleted": deleted, "defused": defused}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args(argv)

    if not args.db.exists():
        print(f"no task graph at {args.db} — nothing to repair")
        return 0

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        delete, defuse = plan(conn)

        if not delete and not defuse:
            print("no stub rows found — task graph is clean")
            return 0

        blocked = referenced_by_edges(conn)
        if blocked:
            print("refusing to delete stubs referenced by edges:", ", ".join(blocked))
            print("inspect these by hand — an edge means something depends on the row")
            return 1

        print(f"delete ({len(delete)} complete stubs, no edges, nothing actionable):")
        for r in delete:
            print(f"  - {r['id']!r}")
        print(f"\ndefuse ({len(defuse)} open stubs — clear borrowed gate flags, mark stale):")
        for r in defuse:
            flags = f"challenge={r['challenge_cleared']} nfr={r['nfr_cleared']} unblocked={r['unblocked']}"
            print(f"  - {r['id']!r}  [{flags}]")

        if not args.apply:
            print("\ndry run — pass --apply to write")
            return 0

        backup = snapshot(args.db)
        print(f"\nsnapshot: {backup}")
        result = apply(conn)
        print(f"deleted {result['deleted']}, defused {result['defused']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
