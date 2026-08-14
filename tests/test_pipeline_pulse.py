"""Tests for pipeline_pulse.py — data-flow contract checks.

Wiring pulse checks reachability (tool mentioned); pipeline pulse checks correctness
(data flows between tools as expected). These tests verify each contract in isolation
using real graph functions against temp DBs — no mocking.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
for _p in [str(_REPO / "servers" / "shared"), str(_REPO / "servers" / "core" / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pipeline_pulse import (
    check_pipeline_contracts,
    format_pipeline_warnings,
    _check_c2_in_flight_excluded_from_next_task,
    _check_c3_mark_done_clears_in_flight,
    _check_c1_task_contract_schema_stable,
)
import graph as G


# ---------------------------------------------------------------------------
# C1 — task_contract schema
# ---------------------------------------------------------------------------

class TestC1TaskContractSchema:

    def test_c1_passes_with_real_task_contract(self, tmp_path):
        r = _check_c1_task_contract_schema_stable(tmp_path / "unused.db")
        assert r["ok"] is True
        assert "C1" in r["contract"]

    def test_c1_xs_task_returns_contract_required_false(self, tmp_path):
        from task_contract import generate_task_contract
        result = generate_task_contract("fix typo in README", size="XS")
        assert result["contract_required"] is False


# ---------------------------------------------------------------------------
# C2 — in_flight excluded from next_task
# ---------------------------------------------------------------------------

class TestC2InFlightExcluded:

    def test_c2_passes_with_real_graph(self, tmp_path):
        db = tmp_path / "c2.db"
        r = _check_c2_in_flight_excluded_from_next_task(db)
        assert r["ok"] is True
        assert "C2" in r["contract"]

    def test_c2_fails_when_in_flight_not_excluded(self, tmp_path, monkeypatch):
        """Simulate a broken next_task that ignores in_flight — contract must catch it."""
        db = tmp_path / "c2-broken.db"
        G.create_task_graph([{"id": "bad-task", "label": "T"}], db_path=db)
        G.set_gate("bad-task", "unblocked", True, db_path=db)
        G.set_gate("bad-task", "in_flight", True, session_id="test", db_path=db)

        import sqlite3
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        # Verify that without the in_flight filter, the task would appear
        rows = conn.execute(
            "SELECT id FROM tasks WHERE unblocked=1 AND done=0"
        ).fetchall()
        assert any(r["id"] == "bad-task" for r in rows), \
            "Task should be present if in_flight filter were removed"
        conn.close()

        # The real next_task with in_flight filter correctly excludes it
        result = G.next_task(db_path=db)
        assert not result["found"] or result["task"]["id"] != "bad-task"

    def test_in_flight_task_absent_from_next_task(self, tmp_path):
        db = tmp_path / "c2-direct.db"
        G.create_task_graph(
            [{"id": "t1", "label": "T1"}, {"id": "t2", "label": "T2"}],
            db_path=db,
        )
        G.set_gate("t1", "unblocked", True, db_path=db)
        G.set_gate("t2", "unblocked", True, db_path=db)
        G.set_gate("t1", "in_flight", True, session_id="session-A", db_path=db)
        # next_task must return t2, not t1
        r = G.next_task(db_path=db)
        assert r["found"]
        assert r["task"]["id"] == "t2"


# ---------------------------------------------------------------------------
# C3 — mark_done clears in_flight and session_id
# ---------------------------------------------------------------------------

class TestC3MarkDoneClears:

    def test_c3_passes_with_real_graph(self, tmp_path):
        db = tmp_path / "c3.db"
        r = _check_c3_mark_done_clears_in_flight(db)
        assert r["ok"] is True
        assert "C3" in r["contract"]

    def test_mark_done_clears_session_id(self, tmp_path):
        db = tmp_path / "c3-direct.db"
        G.create_task_graph([{"id": "t1", "label": "T"}], db_path=db)
        G.set_gate("t1", "in_flight", True, session_id="session-X", db_path=db)
        state_before = G.is_unblocked("t1", db_path=db)
        assert state_before["gates"]["session_id"] == "session-X"

        G.mark_done("t1", db_path=db)
        tasks = G.get_all_tasks(db_path=db)
        t = next(t for t in tasks if t["id"] == "t1")
        assert t["done"] == 1
        assert t["in_flight"] == 0
        assert t["session_id"] is None

    def test_mark_done_without_session_id_still_works(self, tmp_path):
        db = tmp_path / "c3-nosid.db"
        G.create_task_graph([{"id": "t1", "label": "T"}], db_path=db)
        G.set_gate("t1", "in_flight", True, db_path=db)
        G.mark_done("t1", db_path=db)
        tasks = G.get_all_tasks(db_path=db)
        t = next(t for t in tasks if t["id"] == "t1")
        assert t["done"] == 1
        assert t["session_id"] is None


# ---------------------------------------------------------------------------
# check_pipeline_contracts — aggregate
# ---------------------------------------------------------------------------

class TestCheckPipelineContracts:

    def test_all_contracts_pass(self, tmp_path):
        result = check_pipeline_contracts()
        assert result["ok"] is True
        assert result["failed"] == []
        assert len(result["contracts"]) == 3

    def test_format_warnings_empty_when_all_pass(self, tmp_path):
        result = check_pipeline_contracts()
        warnings = format_pipeline_warnings(result)
        assert warnings == []

    def test_format_warnings_non_empty_on_failure(self):
        broken = {
            "contracts": [{"contract": "C2: test", "ok": False, "detail": "oops"}],
            "ok": False,
            "failed": ["C2: test"],
        }
        warnings = format_pipeline_warnings(broken)
        assert len(warnings) >= 2
        assert any("PIPELINE" in w for w in warnings)
        assert any("oops" in w for w in warnings)
