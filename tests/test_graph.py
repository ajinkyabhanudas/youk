"""Unit tests for graph.py — SQLite task graph with gate booleans.

All tests use tmp_path-scoped DB files so they never touch state/task-graph.db.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
for _p in [str(_REPO / "servers" / "shared"), str(_REPO / "servers" / "core" / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import graph as G


# ---------------------------------------------------------------------------
# create_task_graph
# ---------------------------------------------------------------------------

class TestCreateTaskGraph:

    def test_creates_tasks(self, tmp_path):
        db = tmp_path / "graph.db"
        r = G.create_task_graph([{"id": "t1", "label": "Task 1"}], db_path=db)
        assert r["created"] == 1
        assert r["total_tasks"] == 1

    def test_idempotent_on_repeat(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task 1"}], db_path=db)
        r2 = G.create_task_graph([{"id": "t1", "label": "Task 1"}], db_path=db)
        assert r2["created"] == 0  # INSERT OR IGNORE
        assert r2["total_tasks"] == 1

    def test_creates_edges(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "t1", "label": "A"}, {"id": "t2", "label": "B"}],
            edges=[("t1", "t2")],
            db_path=db,
        )
        r = G.create_task_graph([], db_path=db)
        assert r["total_tasks"] == 2

    def test_edges_idempotent(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "t1", "label": "A"}, {"id": "t2", "label": "B"}],
            edges=[("t1", "t2")],
            db_path=db,
        )
        r2 = G.create_task_graph([], edges=[("t1", "t2")], db_path=db)
        assert r2["edges_added"] == 0


# ---------------------------------------------------------------------------
# set_gate / is_unblocked
# ---------------------------------------------------------------------------

class TestSetGate:

    def test_set_valid_gate(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        r = G.set_gate("t1", "challenge_cleared", True, db_path=db)
        assert r["ok"] is True
        assert r["gate"] == "challenge_cleared"
        assert r["value"] is True

    def test_set_gate_reflects_in_is_unblocked(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        G.set_gate("t1", "challenge_cleared", True, db_path=db)
        G.set_gate("t1", "nfr_cleared", True, db_path=db)
        G.set_gate("t1", "unblocked", True, db_path=db)
        state = G.is_unblocked("t1", db_path=db)
        assert state["found"] is True
        assert state["gates"]["challenge_cleared"] is True
        assert state["gates"]["nfr_cleared"] is True
        assert state["unblocked"] is True

    def test_set_gate_idempotent(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        G.set_gate("t1", "unblocked", True, db_path=db)
        r2 = G.set_gate("t1", "unblocked", True, db_path=db)
        assert r2["ok"] is True

    def test_set_gate_false_clears(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        G.set_gate("t1", "in_flight", True, db_path=db)
        G.set_gate("t1", "in_flight", False, db_path=db)
        state = G.is_unblocked("t1", db_path=db)
        assert state["gates"]["in_flight"] is False

    def test_invalid_gate_name_returns_error(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        r = G.set_gate("t1", "nonexistent_gate", True, db_path=db)
        assert r["ok"] is False
        assert "unknown gate" in r["error"]

    def test_set_gate_auto_creates_stub_task(self, tmp_path):
        """set_gate on unknown task_id creates a stub entry."""
        db = tmp_path / "graph.db"
        r = G.set_gate("unknown-task", "unblocked", True, db_path=db)
        assert r["ok"] is True
        state = G.is_unblocked("unknown-task", db_path=db)
        assert state["found"] is True

    def test_is_unblocked_missing_task(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([], db_path=db)
        state = G.is_unblocked("missing-id", db_path=db)
        assert state["found"] is False
        assert state["unblocked"] is False


# ---------------------------------------------------------------------------
# next_task
# ---------------------------------------------------------------------------

class TestNextTask:

    def test_no_tasks_returns_not_found(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([], db_path=db)
        r = G.next_task(db_path=db)
        assert r["found"] is False
        assert r["task"] is None

    def test_unblocked_task_is_returned(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Ready"}], db_path=db)
        G.set_gate("t1", "unblocked", True, db_path=db)
        r = G.next_task(db_path=db)
        assert r["found"] is True
        assert r["task"]["id"] == "t1"

    def test_in_flight_task_skipped(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "In flight"}], db_path=db)
        G.set_gate("t1", "unblocked", True, db_path=db)
        G.set_gate("t1", "in_flight", True, db_path=db)
        r = G.next_task(db_path=db)
        assert r["found"] is False

    def test_child_blocked_until_parent_unblocked(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "p", "label": "Parent"}, {"id": "c", "label": "Child"}],
            edges=[("p", "c")],
            db_path=db,
        )
        # Child is unblocked but parent is not
        G.set_gate("c", "unblocked", True, db_path=db)
        r = G.next_task(db_path=db)
        assert r["found"] is False  # child blocked by unfinished parent

    def test_child_stays_blocked_until_parent_DONE_not_merely_ready(self, tmp_path):
        # THE REGRESSION GUARD for the gating bug: a parent being merely `unblocked`
        # (ready to start) must NOT release its child. Only `done` releases the child.
        # Previously next_task gated on parent.unblocked, so a ready-but-unfinished parent
        # wrongly surfaced its child — the exact bug this fix closes.
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "p", "label": "Parent"}, {"id": "c", "label": "Child"}],
            edges=[("p", "c")],
            db_path=db,
        )
        G.set_gate("p", "unblocked", True, db_path=db)  # parent READY, not done
        G.set_gate("c", "unblocked", True, db_path=db)
        # Only the parent is actionable; the child is still gated by the unfinished parent.
        assert G.next_task(db_path=db)["task"]["id"] == "p"

    def test_child_ready_only_after_parent_marked_done(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "p", "label": "Parent"}, {"id": "c", "label": "Child"}],
            edges=[("p", "c")],
            db_path=db,
        )
        G.set_gate("p", "unblocked", True, db_path=db)
        G.set_gate("c", "unblocked", True, db_path=db)
        G.mark_done("p", db_path=db)  # NOW the parent is finished
        r = G.next_task(db_path=db)
        assert r["found"] is True
        # parent is done (excluded); the child is now the actionable leaf
        assert r["task"]["id"] == "c"

    def test_multi_parent_child_waits_for_ALL_parents_done(self, tmp_path):
        # ADVERSARY FINDING (highest-value): the AND-semantics across >1 parent was untested.
        # A regression flipping AND→OR would pass every single-parent test but break here.
        db = tmp_path / "graph.db"
        G.create_task_graph(
            [{"id": "p1", "label": "P1"}, {"id": "p2", "label": "P2"},
             {"id": "c", "label": "Child"}],
            edges=[("p1", "c"), ("p2", "c")],
            db_path=db,
        )
        for t in ("p1", "p2", "c"):
            G.set_gate(t, "unblocked", True, db_path=db)
        G.mark_done("p1", db_path=db)  # only ONE parent done
        # child must NOT surface — the other parent is unfinished
        ids = []
        r = G.next_task(db_path=db)
        while r["found"]:
            ids.append(r["task"]["id"])
            G.mark_done(r["task"]["id"], db_path=db)
            r = G.next_task(db_path=db)
        # p2 comes before c; c only after BOTH parents done
        assert ids.index("p2") < ids.index("c")


class TestDagValidation:

    def test_self_edge_rejected(self, tmp_path):
        db = tmp_path / "graph.db"
        r = G.create_task_graph(
            [{"id": "t1", "label": "T"}], edges=[("t1", "t1")], db_path=db,
        )
        assert r.get("ok") is False
        assert "self-edge" in r["error"]

    def test_cycle_rejected(self, tmp_path):
        db = tmp_path / "graph.db"
        r = G.create_task_graph(
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            edges=[("a", "b"), ("b", "a")],
            db_path=db,
        )
        assert r.get("ok") is False
        assert "cycle" in r["error"]

    def test_valid_dag_still_accepted(self, tmp_path):
        db = tmp_path / "graph.db"
        r = G.create_task_graph(
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
            edges=[("a", "b"), ("b", "c")],
            db_path=db,
        )
        assert r["edges_added"] == 2

    def test_orphan_parent_edge_auto_stubs_no_crash(self, tmp_path):
        # ADVERSARY FINDING: an edge to a never-inserted parent raised an uncaught
        # IntegrityError. Now it auto-stubs and returns gracefully.
        db = tmp_path / "graph.db"
        r = G.create_task_graph(
            [{"id": "c", "label": "Child"}], edges=[("ghost-parent", "c")], db_path=db,
        )
        assert r.get("ok") is not False  # did not error out
        assert G.is_unblocked("ghost-parent", db_path=db)["found"] is True

    def test_is_unblocked_reports_done(self, tmp_path):
        # ADVERSARY FINDING: done was invisible on the public read-path.
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "T"}], db_path=db)
        assert G.is_unblocked("t1", db_path=db)["gates"]["done"] is False
        G.mark_done("t1", db_path=db)
        assert G.is_unblocked("t1", db_path=db)["gates"]["done"] is True


# ---------------------------------------------------------------------------
# mark_done
# ---------------------------------------------------------------------------

class TestMarkDone:

    def test_mark_done_sets_done_and_clears_in_flight(self, tmp_path):
        # mark_done sets the dedicated `done` bit and clears in_flight. It must NOT touch
        # `unblocked` — that bit means 'ready to start', a distinct concept from 'finished'.
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        G.set_gate("t1", "in_flight", True, db_path=db)
        G.mark_done("t1", db_path=db)
        state = G.is_unblocked("t1", db_path=db)
        assert state["gates"]["in_flight"] is False
        task = next(t for t in G.get_all_tasks(db_path=db) if t["id"] == "t1")
        assert task["done"] == 1

    def test_mark_done_is_idempotent(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        G.mark_done("t1", db_path=db)
        r2 = G.mark_done("t1", db_path=db)
        assert r2["ok"] is True


# ---------------------------------------------------------------------------
# check_graph_health
# ---------------------------------------------------------------------------

class TestCheckGraphHealth:

    def test_absent_db(self, tmp_path):
        h = G.check_graph_health(tmp_path / "nonexistent.db")
        assert h["status"] == "absent"
        assert h["task_count"] == 0

    def test_healthy_db(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "T"}], db_path=db)
        h = G.check_graph_health(db)
        assert h["status"] == "healthy"
        assert h["task_count"] == 1

    def test_corrupt_db(self, tmp_path):
        db = tmp_path / "graph.db"
        db.write_bytes(b"this is not sqlite")
        h = G.check_graph_health(db)
        assert h["status"] == "corrupt"
        assert "task_count" in h


# ---------------------------------------------------------------------------
# stale column — present but not mutated (reserved for dirty-bit propagation)
# ---------------------------------------------------------------------------

class TestStaleColumn:

    def test_stale_defaults_to_false(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "Task"}], db_path=db)
        state = G.is_unblocked("t1", db_path=db)
        assert state["gates"]["stale"] is False

    def test_get_all_tasks_includes_stale(self, tmp_path):
        db = tmp_path / "graph.db"
        G.create_task_graph([{"id": "t1", "label": "T"}], db_path=db)
        tasks = G.get_all_tasks(db_path=db)
        assert len(tasks) == 1
        assert "stale" in tasks[0]
        assert tasks[0]["stale"] == 0
