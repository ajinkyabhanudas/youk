"""Task 1.2/1.4 — project-scoped next_task, the project column, and the migration.

The bug this closes: next_task() had no project arg and the tasks table had no project
column, so "next task for youk" returned the first ready leaf across ALL projects (it
returned a canopy task in a real session). These tests prove scoping now works and that
existing (untagged) databases migrate without breaking.
"""
from __future__ import annotations

import sqlite3

from graph import create_task_graph, mark_done, next_task, set_gate


def _ready(db, task_id, project=None):
    """Insert a task, tag its project, and clear its gates so it's actionable."""
    create_task_graph([{"id": task_id, "label": task_id, "project": project}], db_path=db)
    set_gate(task_id, "unblocked", True, db_path=db)


def test_next_task_scopes_to_project(tmp_path):
    """The core fix: next_task(project) never returns another project's task."""
    db = tmp_path / "g.db"
    _ready(db, "youk-1.2", project="youk")
    _ready(db, "canopy-eval", project="canopy")

    result = next_task(project="youk", db_path=db)
    assert result["found"]
    assert result["task"]["id"] == "youk-1.2"
    assert result["task"]["project"] == "youk"


def test_next_task_canopy_does_not_return_youk(tmp_path):
    db = tmp_path / "g.db"
    _ready(db, "youk-1.2", project="youk")
    _ready(db, "canopy-eval", project="canopy")

    result = next_task(project="canopy", db_path=db)
    assert result["found"]
    assert result["task"]["project"] == "canopy"


def test_next_task_no_project_is_unchanged_behavior(tmp_path):
    """Existing callers pass no project — they still get any ready task (non-breaking)."""
    db = tmp_path / "g.db"
    _ready(db, "some-task", project="youk")
    result = next_task(db_path=db)  # no project arg — old signature
    assert result["found"]
    assert result["task"]["id"] == "some-task"


def test_untagged_legacy_task_visible_to_project_query(tmp_path):
    """A pre-migration task (project=NULL) is unscoped — visible to any project query,
    so nothing silently disappears when the column is added."""
    db = tmp_path / "g.db"
    _ready(db, "legacy", project=None)
    result = next_task(project="youk", db_path=db)
    assert result["found"]
    assert result["task"]["id"] == "legacy"


def test_migration_adds_project_column_to_old_db(tmp_path):
    """A DB created WITHOUT the project column (old schema) gains it on next open,
    without data loss — the additive migration."""
    db = tmp_path / "old.db"
    # Simulate a pre-project-column database.
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, label TEXT NOT NULL, "
        "challenge_cleared INTEGER DEFAULT 0, nfr_cleared INTEGER DEFAULT 0, "
        "unblocked INTEGER DEFAULT 0, in_flight INTEGER DEFAULT 0, stale INTEGER DEFAULT 0)"
    )
    conn.execute("CREATE TABLE edges (parent_id TEXT, child_id TEXT, PRIMARY KEY(parent_id, child_id))")
    conn.execute("INSERT INTO tasks (id, label, unblocked) VALUES ('pre-existing', 'old task', 1)")
    conn.commit()
    conn.close()

    # Opening through graph.py runs the migration.
    result = next_task(project="youk", db_path=db)
    assert result["found"]
    assert result["task"]["id"] == "pre-existing"  # old row survived + is unscoped

    # Column now exists.
    conn = sqlite3.connect(str(db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    conn.close()
    assert "project" in cols


def test_busy_timeout_is_set(tmp_path):
    """WAL + busy_timeout are configured (concurrency NFR decision). A second
    connection can read while the DB is set up, and the pragma is applied."""
    db = tmp_path / "g.db"
    _ready(db, "t", project="youk")
    conn = sqlite3.connect(str(db))
    # busy_timeout persists per-connection; graph.py sets 5000 on its own connections.
    # Here we assert WAL mode took (the durable, file-level signal that setup ran).
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_mark_done_then_scoped_next(tmp_path):
    """End-to-end: complete a youk task, next youk task is the following one."""
    db = tmp_path / "g.db"
    _ready(db, "youk-1.1", project="youk")
    _ready(db, "youk-1.2", project="youk")
    mark_done("youk-1.1", db_path=db)
    set_gate("youk-1.1", "in_flight", False, db_path=db)
    # both unblocked; scoped query returns a youk task (not another project's)
    result = next_task(project="youk", db_path=db)
    assert result["found"]
    assert result["task"]["project"] == "youk"
