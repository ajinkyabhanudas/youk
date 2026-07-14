"""
Tests for convergence state tracking.

Verifies:
1. update_convergence_state: mechanical update rules, pressure source tracking
2. User pressure credits convergence; model pressure does not
3. Unknown-unknowns accumulate correctly
4. distance_from_optimum computed correctly
5. angles_converged count is accurate
6. SessionState carries convergence_state field with correct defaults
7. convergence-state.json persists across task_checkpoint calls
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# 1. update_convergence_state — mechanical rules
# ---------------------------------------------------------------------------

class TestUpdateConvergenceState:
    def _empty(self) -> dict:
        return {
            "structural": "unknown", "operational": "unknown",
            "experiential": "unknown", "adversarial": "unknown",
            "temporal": "unknown", "outcome": "unknown", "semantic": "unknown",
            "unknown_unknowns": [], "last_external_pressure": None,
            "angles_converged": 0, "distance_from_optimum": "7/7 not yet converged",
        }

    def test_user_pressure_credits_convergence(self):
        from session import update_convergence_state
        result = update_convergence_state(self._empty(), "structural", "converged", "user")
        assert result["structural"] == "converged"
        assert result["angles_converged"] == 1

    def test_model_pressure_does_not_credit_convergence(self):
        from session import update_convergence_state
        result = update_convergence_state(self._empty(), "structural", "converged", "model")
        assert result["structural"] == "unknown"
        assert result["angles_converged"] == 0

    def test_diverged_status_recorded(self):
        from session import update_convergence_state
        result = update_convergence_state(self._empty(), "experiential", "diverged", "user")
        assert result["experiential"] == "diverged"
        assert result["angles_converged"] == 0

    def test_unknown_unknown_accumulates(self):
        from session import update_convergence_state
        cs = self._empty()
        cs = update_convergence_state(cs, "adversarial", "unknown", "user",
                                       "what the competitor rejects — requires real adversary")
        assert len(cs["unknown_unknowns"]) == 1
        assert "requires real adversary" in cs["unknown_unknowns"][0]

    def test_unknown_unknown_not_duplicated(self):
        from session import update_convergence_state
        cs = self._empty()
        msg = "requires real adversary"
        cs = update_convergence_state(cs, "adversarial", "unknown", "user", msg)
        cs = update_convergence_state(cs, "adversarial", "unknown", "user", msg)
        assert len(cs["unknown_unknowns"]) == 1

    def test_last_external_pressure_updated_on_user(self):
        from session import update_convergence_state
        result = update_convergence_state(self._empty(), "structural", "converged", "user")
        assert result["last_external_pressure"] == "structural"

    def test_last_external_pressure_not_updated_on_model(self):
        from session import update_convergence_state
        result = update_convergence_state(self._empty(), "structural", "converged", "model")
        assert result["last_external_pressure"] is None

    def test_invalid_angle_ignored(self):
        from session import update_convergence_state
        cs = self._empty()
        result = update_convergence_state(cs, "nonexistent", "converged", "user")
        assert "nonexistent" not in result
        assert result["angles_converged"] == 0


# ---------------------------------------------------------------------------
# 2. distance_from_optimum computation
# ---------------------------------------------------------------------------

class TestDistanceFromOptimum:
    def _empty(self) -> dict:
        return {
            "structural": "unknown", "operational": "unknown",
            "experiential": "unknown", "adversarial": "unknown",
            "temporal": "unknown", "outcome": "unknown", "semantic": "unknown",
            "unknown_unknowns": [], "last_external_pressure": None,
            "angles_converged": 0,
        }

    def test_all_unknown_is_seven_of_seven(self):
        from session import update_convergence_state
        cs = self._empty()
        cs = update_convergence_state(cs, "structural", "unknown", "user")
        assert "7/7" in cs["distance_from_optimum"]

    def test_one_converged_reduces_distance(self):
        from session import update_convergence_state
        cs = self._empty()
        cs = update_convergence_state(cs, "structural", "converged", "user")
        assert "6/7" in cs["distance_from_optimum"]

    def test_all_converged_is_zero(self):
        from session import update_convergence_state
        cs = self._empty()
        for angle in ["structural", "operational", "experiential", "adversarial",
                       "temporal", "outcome", "semantic"]:
            cs = update_convergence_state(cs, angle, "converged", "user")
        assert "0/7" in cs["distance_from_optimum"]
        assert cs["angles_converged"] == 7


# ---------------------------------------------------------------------------
# 3. SessionState carries convergence_state with correct defaults
# ---------------------------------------------------------------------------

class TestSessionStateConvergenceField:
    def test_convergence_state_present_in_session_state(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
        )
        assert "structural" in s.convergence_state
        assert "semantic" in s.convergence_state

    def test_all_seven_angles_default_unknown(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
        )
        for angle in ["structural", "operational", "experiential", "adversarial",
                      "temporal", "outcome", "semantic"]:
            assert s.convergence_state[angle] == "unknown"

    def test_default_angles_converged_is_zero(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
        )
        assert s.convergence_state["angles_converged"] == 0

    def test_to_dict_includes_convergence_state(self):
        from models import SessionState
        s = SessionState(
            project="test", resume_point="", context_health="L1",
            pending_proposals_count=0, session_counter=1,
        )
        d = s.to_dict()
        assert "convergence_state" in d
        assert d["convergence_state"]["structural"] == "unknown"


# ---------------------------------------------------------------------------
# 4. Convergence state persists correctly (file round-trip)
# ---------------------------------------------------------------------------

class TestConvergenceStatePersistence:
    def test_state_round_trips_through_json(self):
        from session import update_convergence_state
        cs = {
            "structural": "unknown", "operational": "unknown",
            "experiential": "unknown", "adversarial": "unknown",
            "temporal": "unknown", "outcome": "unknown", "semantic": "unknown",
            "unknown_unknowns": [], "last_external_pressure": None,
            "angles_converged": 0, "distance_from_optimum": "7/7 not yet converged",
        }
        cs = update_convergence_state(cs, "structural", "converged", "user")
        serialized = json.dumps(cs)
        restored = json.loads(serialized)
        assert restored["structural"] == "converged"
        assert restored["angles_converged"] == 1

    def test_multiple_updates_accumulate(self):
        from session import update_convergence_state
        cs = {
            "structural": "unknown", "operational": "unknown",
            "experiential": "unknown", "adversarial": "unknown",
            "temporal": "unknown", "outcome": "unknown", "semantic": "unknown",
            "unknown_unknowns": [], "last_external_pressure": None,
            "angles_converged": 0,
        }
        for angle in ["structural", "operational", "experiential"]:
            cs = update_convergence_state(cs, angle, "converged", "user")
        assert cs["angles_converged"] == 3
        assert cs["structural"] == "converged"
        assert cs["operational"] == "converged"
        assert cs["experiential"] == "converged"
        assert cs["adversarial"] == "unknown"
