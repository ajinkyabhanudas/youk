"""Wiring guard for deploy_freshness — the adversary's #1 finding.

The module's whole value is the integration point: session_start must CALL check_freshness,
and it must persist the current HEAD so the NEXT session has a baseline to diff. A
perfectly-tested pure function that nothing calls is the wiring_pulse false-green the module's
own docstring warns against. These tests assert the wiring exists.
"""
from __future__ import annotations

from pathlib import Path

SESSION_PY = Path(__file__).resolve().parents[1] / "servers" / "core" / "src" / "session.py"


def _text() -> str:
    return SESSION_PY.read_text()


def test_session_start_calls_freshness_check():
    t = _text()
    assert "_check_deploy_freshness" in t, "session.py never calls the freshness gate"
    assert "deploy_freshness" in t, "deploy_freshness module not imported in session.py"


def test_session_persists_head_baseline():
    t = _text()
    # the current HEAD must be recorded so the next session can diff against it
    assert 'state["last_head"]' in t, "session never persists last_head baseline"
    assert "_current_project_head" in t, "no HEAD-capture helper wired"


def test_freshness_warning_surfaces_in_plan():
    t = _text()
    # the warning must reach the session_plan (not computed then dropped)
    assert "_freshness" in t and "session_plan.insert(0, _freshness.warning())" in t, (
        "freshness warning is computed but never surfaced in session_plan"
    )
