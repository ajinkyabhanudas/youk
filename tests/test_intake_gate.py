"""Tests for intake_gate.py — check_intake_gate blocks M+ when intake was required
but has not run, passes otherwise. Mirrors test_nfr_gate.py (the gate it's modeled on).

Task 1.7: the last direction-gate to become machine-checkable rather than prose-enforced.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from intake_gate import check_intake_gate


class TestIntakeGateBlocked:
    """M/L/XL with intake_required=True and not yet run must block."""

    def test_m_required_not_run_is_blocked(self):
        result = check_intake_gate("make it feel polished", "M", intake_required=True, intake_has_run=False)
        assert result["blocked"] is True
        assert "intake" in result["reason"].lower()

    def test_l_required_not_run_is_blocked(self):
        result = check_intake_gate("improve onboarding", "L", intake_required=True, intake_has_run=False)
        assert result["blocked"] is True

    def test_xl_required_not_run_is_blocked(self):
        result = check_intake_gate("rethink the system", "XL", intake_required=True, intake_has_run=False)
        assert result["blocked"] is True

    def test_reason_names_the_size(self):
        result = check_intake_gate("vague goal", "L", intake_required=True, intake_has_run=False)
        assert "L" in result["reason"]


class TestIntakeGatePasses:
    """XS/S always pass; M+ passes when intake not required OR already ran."""

    def test_xs_passes_even_if_required(self):
        result = check_intake_gate("typo", "XS", intake_required=True, intake_has_run=False)
        assert result["blocked"] is False

    def test_s_passes_even_if_required(self):
        result = check_intake_gate("small fix", "S", intake_required=True, intake_has_run=False)
        assert result["blocked"] is False

    def test_m_passes_when_intake_not_required(self):
        result = check_intake_gate("concrete task", "M", intake_required=False, intake_has_run=False)
        assert result["blocked"] is False
        assert result["reason"] == ""

    def test_m_passes_when_intake_already_ran(self):
        result = check_intake_gate("was vague, now clarified", "M", intake_required=True, intake_has_run=True)
        assert result["blocked"] is False

    def test_l_passes_when_intake_ran(self):
        result = check_intake_gate("clarified goal", "L", intake_required=True, intake_has_run=True)
        assert result["blocked"] is False


class TestIntakeGateEdgeCases:
    def test_unknown_size_passes(self):
        result = check_intake_gate("do something", "UNKNOWN", intake_required=True, intake_has_run=False)
        assert result["blocked"] is False

    def test_lowercase_size_passes(self):
        result = check_intake_gate("task", "m", intake_required=True, intake_has_run=False)
        assert result["blocked"] is False

    def test_result_always_has_blocked_and_reason(self):
        for size in ("XS", "S", "M", "L", "XL"):
            result = check_intake_gate("task", size, intake_required=True, intake_has_run=False)
            assert "blocked" in result
            assert "reason" in result
