"""Tests for challenge_gate.py — check_challenge_gate blocks M+ when challenge hasn't run."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from challenge_gate import check_challenge_gate


class TestChallengeGateBlocked:
    """M/L/XL without challenge must return blocked=True."""

    def test_m_task_challenge_not_run_is_blocked(self):
        result = check_challenge_gate("add caching layer", "M", challenge_ran=False)
        assert result["blocked"] is True

    def test_l_task_challenge_not_run_is_blocked(self):
        result = check_challenge_gate("redesign auth module", "L", challenge_ran=False)
        assert result["blocked"] is True

    def test_xl_task_challenge_not_run_is_blocked(self):
        result = check_challenge_gate("platform rewrite", "XL", challenge_ran=False)
        assert result["blocked"] is True

    def test_reason_names_challenge_skill(self):
        result = check_challenge_gate("build feature", "M", challenge_ran=False)
        assert "challenge" in result["reason"].lower()

    def test_reason_names_the_size(self):
        result = check_challenge_gate("build feature", "M", challenge_ran=False)
        assert "M" in result["reason"]

    def test_reason_names_mark_challenge_ran(self):
        result = check_challenge_gate("build feature", "M", challenge_ran=False)
        assert "mark_challenge_ran" in result["reason"]


class TestChallengeGatePasses:
    """XS/S always pass; M+ pass when challenge_ran=True."""

    def test_xs_passes_regardless(self):
        result = check_challenge_gate("fix typo", "XS", challenge_ran=False)
        assert result["blocked"] is False

    def test_s_passes_regardless(self):
        result = check_challenge_gate("rename variable", "S", challenge_ran=False)
        assert result["blocked"] is False

    def test_m_passes_when_challenge_ran(self):
        result = check_challenge_gate("add caching layer", "M", challenge_ran=True)
        assert result["blocked"] is False

    def test_l_passes_when_challenge_ran(self):
        result = check_challenge_gate("redesign auth module", "L", challenge_ran=True)
        assert result["blocked"] is False

    def test_xl_passes_when_challenge_ran(self):
        result = check_challenge_gate("platform rewrite", "XL", challenge_ran=True)
        assert result["blocked"] is False

    def test_xs_reason_is_empty_on_pass(self):
        result = check_challenge_gate("fix typo", "XS", challenge_ran=False)
        assert result["reason"] == ""

    def test_m_reason_is_empty_when_challenge_ran(self):
        result = check_challenge_gate("add feature", "M", challenge_ran=True)
        assert result["reason"] == ""


class TestChallengeGateReturnShape:
    """Return value always has blocked and reason keys."""

    def test_blocked_case_has_correct_keys(self):
        result = check_challenge_gate("task", "M", challenge_ran=False)
        assert "blocked" in result
        assert "reason" in result

    def test_pass_case_has_correct_keys(self):
        result = check_challenge_gate("task", "XS", challenge_ran=False)
        assert "blocked" in result
        assert "reason" in result

    def test_blocked_is_bool_not_truthy(self):
        blocked = check_challenge_gate("task", "M", challenge_ran=False)["blocked"]
        passed = check_challenge_gate("task", "S", challenge_ran=False)["blocked"]
        assert blocked is True
        assert passed is False
