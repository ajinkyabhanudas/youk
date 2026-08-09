"""Task graph — SQLite-backed DAG with gate state per node.

Schema
------
tasks  : id, label, challenge_cleared, nfr_cleared, unblocked, in_flight, done, stale
edges  : parent_id → child_id (directed: parent must complete before child)

Gate booleans (written by set_gate, read by is_unblocked):
  challenge_cleared  — challenge skill ran and passed
  nfr_cleared        — nfr_check ran and gate unblocked
  unblocked          — both challenge + nfr cleared (derived; means READY to start)
  in_flight          — currently being worked on this session
  done               — task is FINISHED. Distinct from unblocked: a task can be
                       unblocked (ready) without being done. next_task gates a child
                       on its parents' `done`, NOT `unblocked` — previously these were
                       the same bit, so a child unblocked when its parent was merely
                       ready, not finished. mark_done sets this; next_task excludes it.

stale column is reserved for dirty-bit propagation (impact() tool — future build).
It is written to 0 on insert and never mutated here.

All writes are idempotent (INSERT OR IGNORE, UPDATE is always safe to repeat).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

YOUK_ROOT = Path("/youk")
_DB_PATH = YOUK_ROOT / "state" / "task-graph.db"

# Gate names accepted by set_gate / get_gate
GATE_NAMES = frozenset({"challenge_cleared", "nfr_cleared", "unblocked", "in_flight"})

_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    id                  TEXT PRIMARY KEY,
    label               TEXT NOT NULL,
    project             TEXT,
    challenge_cleared   INTEGER NOT NULL DEFAULT 0,
    nfr_cleared         INTEGER NOT NULL DEFAULT 0,
    unblocked           INTEGER NOT NULL DEFAULT 0,
    in_flight           INTEGER NOT NULL DEFAULT 0,
    done                INTEGER NOT NULL DEFAULT 0,
    stale               INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
    parent_id   TEXT NOT NULL REFERENCES tasks(id),
    child_id    TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (parent_id, child_id)
);
"""


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Additive migrations for DBs created before a column existed.

    The `project` column (Task 1.4 / contract R1) makes next_task project-scoped so
    "next task for youk" can never again return another project's task. Existing rows
    get project=NULL and are treated as unscoped (visible to any project query) until
    re-tagged — a backward-compatible default, not a breaking change.
    Idempotent: checks the column exists before adding.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "project" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN project TEXT")
    if "done" not in cols:
        # Completion state, split out from the overloaded `unblocked` bit. Existing rows
        # backfill to done=0: nothing is ASSUMED finished — a genuinely-done task is
        # re-marked via mark_done going forward. Conservative: never a false "done" that
        # would wrongly release a child. Idempotent.
        conn.execute("ALTER TABLE tasks ADD COLUMN done INTEGER NOT NULL DEFAULT 0")


class _DB:
    """Context manager that opens, initialises, and closes a SQLite connection."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = sqlite3.connect(str(self._path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # busy_timeout: a concurrent writer (e.g. a second Claude tab) WAITS up to 5s
        # for the lock rather than failing immediately. NFR decision for the state-store
        # rework (Task 1). Paired with the sqlite3.connect(timeout=5.0) above.
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_DDL)
        _migrate_schema(self._conn)
        self._conn.commit()
        return self._conn

    def __exit__(self, *args: object) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()
            self._conn = None


def _connect(db_path: Path = _DB_PATH) -> _DB:
    return _DB(db_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_task_graph(tasks: list[dict], edges: list[tuple[str, str]] | None = None,
                      db_path: Path = _DB_PATH) -> dict:
    """Create or extend the task graph.

    tasks: list of {"id": str, "label": str}
    edges: list of (parent_id, child_id) — parent must complete before child

    Idempotent: existing tasks and edges are silently skipped (INSERT OR IGNORE).
    Rejects edges that would break the DAG (a self-edge or a cycle) — because next_task gates
    a child on its parents' done state, a self-edge makes a task its own unfinished parent
    (never actionable) and a cycle deadlocks every task in it. These are surfaced as an error,
    not silently inserted. Returns {"created", "edges_added", "total_tasks"}
    or {"ok": False, "error": ...} when an edge would break the DAG.
    """
    edges = edges or []
    created = 0
    edges_added = 0

    # Self-edge guard: parent == child can never be satisfied (a task can't finish before
    # itself), so it permanently removes the task from next_task. Reject up front.
    self_edges = [e for e in edges if e[0] == e[1]]
    if self_edges:
        return {"ok": False, "error": f"self-edge(s) not allowed: {self_edges}"}

    with _connect(db_path) as conn:
        for t in tasks:
            cur = conn.execute(
                "INSERT OR IGNORE INTO tasks (id, label, project) VALUES (?, ?, ?)",
                (t["id"], t["label"], t.get("project")),
            )
            created += cur.rowcount

        # Cycle guard: build the adjacency of existing + proposed edges and reject if adding
        # them introduces a cycle (a cycle deadlocks next_task for the whole component).
        existing = [(r["parent_id"], r["child_id"])
                    for r in conn.execute("SELECT parent_id, child_id FROM edges")]
        if _would_cycle(existing + list(edges)):
            conn.rollback()
            return {"ok": False, "error": "edge(s) would introduce a cycle in the task DAG"}

        for parent, child in edges:
            # Auto-stub any edge endpoint not already a task, so an edge referencing a
            # not-yet-created node degrades gracefully (matching set_gate's stub behavior)
            # instead of raising an uncaught FK IntegrityError that aborts the whole call.
            for node in (parent, child):
                conn.execute(
                    "INSERT OR IGNORE INTO tasks (id, label) VALUES (?, ?)", (node, node),
                )
            cur = conn.execute(
                "INSERT OR IGNORE INTO edges (parent_id, child_id) VALUES (?, ?)",
                (parent, child),
            )
            edges_added += cur.rowcount

        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        conn.commit()

    return {"created": created, "edges_added": edges_added, "total_tasks": total}


def _would_cycle(edges: list[tuple[str, str]]) -> bool:
    """True if the directed edge set contains a cycle (DFS three-colour). Pure function."""
    adj: dict[str, list[str]] = {}
    for p, c in edges:
        adj.setdefault(p, []).append(c)
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def visit(node: str) -> bool:
        color[node] = GREY
        for nxt in adj.get(node, []):
            c = color.get(nxt, WHITE)
            if c == GREY:            # back-edge → cycle
                return True
            if c == WHITE and visit(nxt):
                return True
        color[node] = BLACK
        return False

    return any(color.get(n, WHITE) == WHITE and visit(n) for n in list(adj))


def set_gate(task_id: str, gate_name: str, value: bool,
             db_path: Path = _DB_PATH) -> dict:
    """Set a gate boolean on a task node. Idempotent.

    gate_name: one of challenge_cleared, nfr_cleared, unblocked, in_flight
    Returns {"ok": bool, "task_id": str, "gate": str, "value": bool}
    """
    if gate_name not in GATE_NAMES:
        return {"ok": False, "error": f"unknown gate '{gate_name}'; valid: {sorted(GATE_NAMES)}"}

    int_val = 1 if value else 0

    with _connect(db_path) as conn:
        # Ensure task exists (creates a stub if called before create_task_graph)
        conn.execute(
            "INSERT OR IGNORE INTO tasks (id, label) VALUES (?, ?)",
            (task_id, task_id),
        )
        conn.execute(
            f"UPDATE tasks SET {gate_name} = ? WHERE id = ?",
            (int_val, task_id),
        )
        conn.commit()

    return {"ok": True, "task_id": task_id, "gate": gate_name, "value": value}


def is_unblocked(task_id: str, db_path: Path = _DB_PATH) -> dict:
    """Return gate state for a task.

    Returns {"found": bool, "task_id": str, "gates": dict, "unblocked": bool}
    """
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    if row is None:
        return {"found": False, "task_id": task_id, "gates": {}, "unblocked": False}

    gates = {
        "challenge_cleared": bool(row["challenge_cleared"]),
        "nfr_cleared": bool(row["nfr_cleared"]),
        "unblocked": bool(row["unblocked"]),
        "in_flight": bool(row["in_flight"]),
        # `done` must be readable here: mark_done sets it, and external gate logic asking
        # "is this task finished?" uses is_unblocked. Omitting it (the original API gap) left
        # completion invisible on the one public read-path a caller would reach for.
        "done": bool(row["done"]) if "done" in row.keys() else False,
        "stale": bool(row["stale"]),
    }
    return {
        "found": True,
        "task_id": task_id,
        "gates": gates,
        "unblocked": gates["unblocked"],
    }


def next_task(project: str | None = None, db_path: Path = _DB_PATH) -> dict:
    """Return the next actionable task: unblocked=True, in_flight=False, all parents done.

    project: when given, restrict to that project's tasks (plus untagged project=NULL
    tasks, which are legacy/unscoped). When None, current behavior — any project's task.
    This makes "next task for youk" structurally unable to return another project's task
    (contract R1). Optional with a None default so existing callers are unaffected — the
    blast-radius check found 3 call sites that pass no project; they keep working.

    Uses the edge DAG to find leaf-ready nodes.
    Returns {"found": bool, "task": dict | None}
    """
    params: tuple = ()
    project_clause = ""
    if project is not None:
        # match the project OR untagged legacy rows (project IS NULL)
        # youk: NULL-inclusion is a transitional bridge for pre-tag rows → upgrade when
        # all live rows are project-tagged (drop "OR t.project IS NULL" so an untagged
        # task from another project can never surface as this project's next task).
        project_clause = " AND (t.project = ? OR t.project IS NULL)"
        params = (project,)

    with _connect(db_path) as conn:
        # A task is actionable when:
        # 1. unblocked = 1 (gates cleared), in_flight = 0, done = 0 (not itself finished)
        # 2. All parents are DONE (done = 1) — a child stays blocked until its parent is
        #    actually finished, not merely ready. This gates on `done`, not `unblocked`;
        #    conflating them let a child surface while its parent was still in flight.
        # 3. (if project given) belongs to that project or is untagged
        rows = conn.execute(f"""
            SELECT t.id, t.label, t.project, t.challenge_cleared, t.nfr_cleared,
                   t.unblocked, t.in_flight, t.done, t.stale
            FROM tasks t
            WHERE t.unblocked = 1
              AND t.in_flight = 0
              AND t.done = 0
              AND NOT EXISTS (
                  SELECT 1 FROM edges e
                  JOIN tasks p ON p.id = e.parent_id
                  WHERE e.child_id = t.id
                    AND p.done = 0
              )
              {project_clause}
            ORDER BY t.id
            LIMIT 1
        """, params).fetchall()

    if not rows:
        return {"found": False, "task": None}

    row = rows[0]
    return {
        "found": True,
        "task": {
            "id": row["id"],
            "label": row["label"],
            "project": row["project"],
            "challenge_cleared": bool(row["challenge_cleared"]),
            "nfr_cleared": bool(row["nfr_cleared"]),
            "unblocked": bool(row["unblocked"]),
            "in_flight": bool(row["in_flight"]),
            "done": bool(row["done"]),
            "stale": bool(row["stale"]),
        },
    }


def mark_done(task_id: str, db_path: Path = _DB_PATH) -> dict:
    """Mark a task as FINISHED: set done=1 and clear in_flight.

    Sets the dedicated `done` bit — NOT `unblocked` (which means 'ready to start'). This
    is what releases the task's children in next_task, and what excludes the task itself
    from future next_task results. Idempotent.

    Returns {"ok": bool, "task_id": str}
    """
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET done = 1, in_flight = 0 WHERE id = ?",
            (task_id,),
        )
        conn.commit()
    return {"ok": True, "task_id": task_id}


def get_all_tasks(db_path: Path = _DB_PATH) -> list[dict[str, Any]]:
    """Return all tasks with their gate state. Used by health checks."""
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def check_graph_health(db_path: Path = _DB_PATH) -> dict:
    """Verify graph DB is present and readable.

    Returns {
        "status": "healthy" | "absent" | "corrupt",
        "task_count": int,
        "message": str,
    }
    Used by session_start to detect corrupt DB before falling back to JSON gate files.
    """
    if not db_path.exists():
        return {"status": "absent", "task_count": 0, "message": "task-graph.db not found"}

    try:
        with _connect(db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            return {"status": "healthy", "task_count": count, "message": ""}
    except Exception as exc:
        return {
            "status": "corrupt",
            "task_count": 0,
            "message": f"task-graph.db unreadable: {exc}",
        }
