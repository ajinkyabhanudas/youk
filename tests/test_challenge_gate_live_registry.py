"""Tests for challenge_gate.validate_angles() reading from the live registry.

The frozen-literal tests in test_challenge_angle_validation.py cover the
REQUIRED_ANGLES constants. This file covers the live-registry path introduced
by get_convergence_angles():

  - Fallback to frozen literal when _SEVEN_CONVERGENCE is not enrolled
  - Live read when enrolled (enrolled=True, degraded=False)
  - Degraded sentinel when enrolled but registry is corrupt/empty
  - validate_angles returns enrolled/degraded fields in every result shape
  - Grow round-trip: a new element added to the live set is enforced by validate_angles
  - Prune round-trip: a pruned element is no longer required

Non-goals: this file does not re-test REQUIRED_ANGLES constants or mode routing
— those live in test_challenge_angle_validation.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from challenge_gate import (
    _FOUR_LENSES,
    _SEVEN_CONVERGENCE,
    get_convergence_angles,
    validate_angles,
)
from revisable_sets import enroll, learn_add, unlearn_prune

_ALL_FROZEN = list(_FOUR_LENSES | _SEVEN_CONVERGENCE)


@pytest.fixture
def reg(tmp_path) -> Path:
    return tmp_path / "revisable-sets.json"


# ---------------------------------------------------------------------------
# get_convergence_angles — fallback paths
# ---------------------------------------------------------------------------

class TestGetConvergenceAnglesFallback:

    def test_returns_frozen_literal_when_registry_absent(self, reg):
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert angles == _SEVEN_CONVERGENCE
        assert enrolled is False
        assert degraded is False

    def test_returns_frozen_literal_when_set_not_enrolled(self, reg):
        # Registry exists but _SEVEN_CONVERGENCE not in it.
        reg.write_text(json.dumps({"_OTHER_SET": {"name": "_OTHER_SET", "policy": "grow",
                                                   "elements": {}, "version": 0, "history": []}}))
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert angles == _SEVEN_CONVERGENCE
        assert enrolled is False
        assert degraded is False

    def test_returns_degraded_when_registry_corrupt(self, reg):
        reg.write_text("not json {{{")
        _, enrolled, degraded = get_convergence_angles(reg)
        # Corrupt file — cannot confirm enrollment state, treat as degraded.
        assert degraded is True

    def test_returns_degraded_when_enrolled_but_elements_empty(self, reg):
        # Enrolled with no elements is a broken state.
        reg.write_text(json.dumps({
            "_SEVEN_CONVERGENCE": {
                "name": "_SEVEN_CONVERGENCE", "policy": "both",
                "elements": {}, "version": 0, "history": [],
            }
        }))
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert angles == _SEVEN_CONVERGENCE
        assert enrolled is True
        assert degraded is True


# ---------------------------------------------------------------------------
# get_convergence_angles — live read after enrollment
# ---------------------------------------------------------------------------

class TestGetConvergenceAnglesLive:

    def test_returns_live_set_when_enrolled(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert angles == _SEVEN_CONVERGENCE
        assert enrolled is True
        assert degraded is False

    def test_live_set_reflects_grow(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        learn_add("_SEVEN_CONVERGENCE", "ethical", driver="test", path=reg)
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert "ethical" in angles
        assert enrolled is True
        assert degraded is False

    def test_live_set_reflects_prune(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        unlearn_prune("_SEVEN_CONVERGENCE", "semantic", driver="test", path=reg)
        angles, enrolled, degraded = get_convergence_angles(reg)
        assert "semantic" not in angles
        assert enrolled is True
        assert degraded is False


# ---------------------------------------------------------------------------
# validate_angles — enrolled/degraded fields always present
# ---------------------------------------------------------------------------

class TestValidateAnglesMetaFields:

    def test_enrolled_false_when_not_in_registry(self, reg):
        result = validate_angles(_ALL_FROZEN, "full", registry_path=reg)
        assert "enrolled" in result
        assert result["enrolled"] is False
        assert result["degraded"] is False

    def test_enrolled_true_when_registered(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        result = validate_angles(_ALL_FROZEN, "full", registry_path=reg)
        assert result["enrolled"] is True
        assert result["degraded"] is False

    def test_degraded_true_on_corrupt_registry(self, reg):
        reg.write_text("{bad json")
        result = validate_angles(_ALL_FROZEN, "full", registry_path=reg)
        assert result["degraded"] is True

    def test_quick_mode_no_enrolled_degraded_fields(self, reg):
        # Quick mode doesn't read the registry — enrolled/degraded are both False.
        result = validate_angles(list(_FOUR_LENSES), "quick", registry_path=reg)
        assert result["valid"] is True
        assert result["enrolled"] is False
        assert result["degraded"] is False


# ---------------------------------------------------------------------------
# validate_angles — live grow/prune round-trips
# ---------------------------------------------------------------------------

class TestValidateAnglesLiveRoundTrip:

    def test_new_element_via_grow_becomes_required(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        learn_add("_SEVEN_CONVERGENCE", "ethical", driver="test", path=reg)
        # All 7 frozen angles + ethical — but not "ethical" in the angles_checked list.
        result = validate_angles(_ALL_FROZEN, "full", registry_path=reg)
        assert result["valid"] is False
        assert "ethical" in result["missing_angles"]

    def test_grown_element_passes_when_included(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        learn_add("_SEVEN_CONVERGENCE", "ethical", driver="test", path=reg)
        result = validate_angles(_ALL_FROZEN + ["ethical"], "full", registry_path=reg)
        assert result["valid"] is True

    def test_pruned_element_no_longer_required(self, reg):
        enroll("_SEVEN_CONVERGENCE", "both", list(_SEVEN_CONVERGENCE), path=reg)
        unlearn_prune("_SEVEN_CONVERGENCE", "semantic", driver="test", path=reg)
        # Remove "semantic" from angles_checked — should still pass.
        angles_without_semantic = [a for a in _ALL_FROZEN if a != "semantic"]
        result = validate_angles(angles_without_semantic, "full", registry_path=reg)
        assert result["valid"] is True

    def test_fallback_still_requires_all_7_when_not_enrolled(self, reg):
        # No enrollment — frozen literal is used; all 11 required.
        result = validate_angles(list(_FOUR_LENSES), "full", registry_path=reg)
        assert result["valid"] is False
        assert len(result["missing_angles"]) == 7
