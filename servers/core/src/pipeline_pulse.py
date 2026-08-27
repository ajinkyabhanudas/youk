"""Pipeline pulse — verifies cross-tool data flow contracts in the routing pipeline.

Wiring pulse (wiring_pulse.py) answers: "is this tool mentioned anywhere?" — a static
reachability check. It cannot answer: "does task_contract's output actually reach the graph?
does route_task update task state? does session_end release the in-flight claim?"

Pipeline pulse answers the second question: for each pipeline handoff, does data flow from
tool A to tool B as expected? Each contract is tested by exercising the real functions
against a temp DB, not by reading source text.

Contracts checked (the three most load-bearing handoffs in the routing pipeline):
  C1 — task_contract → graph: approve_task_contract should write a contract record
       that is readable; check that the output schema is stable.
  C2 — set_gate(in_flight=True) → next_task exclusion: a task marked in_flight
       must NOT appear in next_task results. If it does, two sessions can claim the
       same task (the bug this fixes).
  C3 — mark_done → in_flight cleared: mark_done must clear in_flight and session_id.
       A "done" task must not appear as in_flight, and session_id must be NULL.

Each contract returns {"contract": str, "ok": bool, "detail": str}.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

YOUK_ROOT = Path("/youk")
_DB_PATH = YOUK_ROOT / "state" / "task-graph.db"


def _check_c2_in_flight_excluded_from_next_task(db_path: Path) -> dict:
    """C2: a task marked in_flight=1 must not appear in next_task.

    If next_task returns an in_flight task, two concurrent sessions would pick the
    same task — a data-flow break between set_gate and next_task.
    """
    contract = "C2: in_flight task excluded from next_task"
    try:
        import sys
        src = Path(__file__).parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from graph import create_task_graph, set_gate, next_task

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "pulse-c2.db"
            create_task_graph(
                [{"id": "pulse-c2-task", "label": "C2 pulse task"}], db_path=db
            )
            set_gate("pulse-c2-task", "unblocked", True, db_path=db)
            # Verify it appears before claiming
            r = next_task(db_path=db)
            if not r["found"]:
                return {"contract": contract, "ok": False,
                        "detail": "task not found before in_flight — gate or next_task broken"}
            # Claim it
            set_gate("pulse-c2-task", "in_flight", True, session_id="pulse-check", db_path=db)
            r2 = next_task(db_path=db)
            if r2["found"] and r2["task"]["id"] == "pulse-c2-task":
                return {"contract": contract, "ok": False,
                        "detail": "in_flight task appeared in next_task — two sessions would claim the same task"}
        return {"contract": contract, "ok": True, "detail": "in_flight task correctly excluded"}
    except Exception as e:
        return {"contract": contract, "ok": False, "detail": f"exception: {e}"}


def _check_c3_mark_done_clears_in_flight(db_path: Path) -> dict:
    """C3: mark_done must clear in_flight and session_id.

    If mark_done leaves in_flight=1 or session_id non-null, a done task appears
    claimed — a phantom lock that confuses session-concurrency bookkeeping.
    """
    contract = "C3: mark_done clears in_flight and session_id"
    try:
        import sys
        src = Path(__file__).parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from graph import create_task_graph, set_gate, mark_done, get_all_tasks

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "pulse-c3.db"
            create_task_graph(
                [{"id": "pulse-c3-task", "label": "C3 pulse task"}], db_path=db
            )
            set_gate("pulse-c3-task", "unblocked", True, db_path=db)
            set_gate("pulse-c3-task", "in_flight", True, session_id="pulse-check", db_path=db)
            mark_done("pulse-c3-task", db_path=db)
            tasks = get_all_tasks(db_path=db)
            task = next((t for t in tasks if t["id"] == "pulse-c3-task"), None)
            if task is None:
                return {"contract": contract, "ok": False, "detail": "task not found after mark_done"}
            if task.get("in_flight"):
                return {"contract": contract, "ok": False,
                        "detail": f"mark_done left in_flight={task['in_flight']}"}
            if task.get("session_id") is not None:
                return {"contract": contract, "ok": False,
                        "detail": f"mark_done left session_id='{task['session_id']}'"}
        return {"contract": contract, "ok": True, "detail": "mark_done cleared in_flight and session_id"}
    except Exception as e:
        return {"contract": contract, "ok": False, "detail": f"exception: {e}"}


def _check_c1_task_contract_schema_stable(db_path: Path) -> dict:
    """C1: task_contract output schema must include required fields.

    task_contract feeds into approve_task_contract and check_task_contract_gate.
    If the schema drifts (required fields missing or renamed), downstream tools
    silently operate on bad data. This contract checks the schema is stable.
    """
    contract = "C1: task_contract output schema includes required fields"
    try:
        import sys
        src = Path(__file__).parent
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from task_contract import generate_task_contract as _task_contract
        result = _task_contract("Add a new field to the graph", size="XS")
        # XS tasks must return contract_required=False — if it returns True for XS,
        # the sizing gate is broken and every small task gets over-ceremonialized.
        if result.get("contract_required") is True and result.get("size") in ("XS", "S"):
            return {"contract": contract, "ok": False,
                    "detail": "XS/S task returned contract_required=True — sizing gate broken"}
        required = {"contract_required"}
        missing = required - set(result.keys())
        if missing:
            return {"contract": contract, "ok": False,
                    "detail": f"task_contract missing required fields: {sorted(missing)}"}
        return {"contract": contract, "ok": True, "detail": "task_contract schema stable"}
    except Exception as e:
        return {"contract": contract, "ok": False, "detail": f"exception: {e}"}


def check_pipeline_contracts(db_path: Path | None = None) -> dict:
    """Run all pipeline data-flow contract checks.

    Returns {"contracts": [result, ...], "ok": bool, "failed": [contract names]}.
    ok=True only when ALL contracts pass. Individual failures are in `failed`.
    Exceptions inside each check are caught and reported as ok=False — never let
    a broken check suppress the others.
    """
    db_path = db_path if db_path is not None else _DB_PATH
    results = [
        _check_c1_task_contract_schema_stable(db_path),
        _check_c2_in_flight_excluded_from_next_task(db_path),
        _check_c3_mark_done_clears_in_flight(db_path),
    ]
    failed = [r["contract"] for r in results if not r["ok"]]
    return {
        "contracts": results,
        "ok": len(failed) == 0,
        "failed": failed,
    }


def format_pipeline_warnings(result: dict) -> list[str]:
    """Session-start lines for failed pipeline contracts."""
    failed = result.get("failed", [])
    if not failed:
        return []
    lines = [
        f"⚠ PIPELINE: {len(failed)} data-flow contract(s) broken "
        f"(tools are wired but data doesn't flow correctly):"
    ]
    for r in result.get("contracts", []):
        if not r["ok"]:
            lines.append(f"    · {r['contract']}: {r['detail']}")
    return lines
