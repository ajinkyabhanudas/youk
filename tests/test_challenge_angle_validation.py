"""
Tests for validate_angles() in challenge_gate.py — angle completeness gate for
mark_challenge_ran. Ensures the dry-loop gate blocks incomplete angle lists and
passes complete ones, per mode.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))

from challenge_gate import validate_angles, REQUIRED_ANGLES, _FOUR_LENSES, _SEVEN_CONVERGENCE

ALL_11 = list(_FOUR_LENSES | _SEVEN_CONVERGENCE)
FOUR_ONLY = list(_FOUR_LENSES)


# ---------------------------------------------------------------------------
# Full mode — requires all 11 angles
# ---------------------------------------------------------------------------

class TestValidateAnglesFull:

    def test_all_11_angles_passes(self):
        result = validate_angles(ALL_11, "full")
        assert result["valid"] is True
        assert result["missing_angles"] == []

    def test_missing_one_convergence_angle_blocks(self):
        angles = [a for a in ALL_11 if a != "adversarial"]
        result = validate_angles(angles, "full")
        assert result["valid"] is False
        assert "adversarial" in result["missing_angles"]

    def test_missing_one_lens_blocks(self):
        angles = [a for a in ALL_11 if a != "framing"]
        result = validate_angles(angles, "full")
        assert result["valid"] is False
        assert "framing" in result["missing_angles"]

    def test_empty_list_blocks_with_all_missing(self):
        result = validate_angles([], "full")
        assert result["valid"] is False
        assert len(result["missing_angles"]) == 11

    def test_four_lenses_only_blocks_in_full_mode(self):
        result = validate_angles(FOUR_ONLY, "full")
        assert result["valid"] is False
        assert len(result["missing_angles"]) == 7

    def test_reason_names_missing_angles(self):
        angles = [a for a in ALL_11 if a != "temporal"]
        result = validate_angles(angles, "full")
        assert "temporal" in result["reason"]

    def test_extra_angles_beyond_required_still_passes(self):
        angles = ALL_11 + ["custom_angle"]
        result = validate_angles(angles, "full")
        assert result["valid"] is True

    def test_case_insensitive_matching(self):
        angles = [a.upper() for a in ALL_11]
        result = validate_angles(angles, "full")
        assert result["valid"] is True

    def test_whitespace_stripped_from_angle_names(self):
        angles = [f"  {a}  " for a in ALL_11]
        result = validate_angles(angles, "full")
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# Quick / silent / plan modes — require 4 lenses only
# ---------------------------------------------------------------------------

class TestValidateAnglesReducedModes:

    def test_quick_mode_passes_with_4_lenses(self):
        result = validate_angles(FOUR_ONLY, "quick")
        assert result["valid"] is True

    def test_silent_mode_passes_with_4_lenses(self):
        result = validate_angles(FOUR_ONLY, "silent")
        assert result["valid"] is True

    def test_plan_mode_passes_with_4_lenses(self):
        result = validate_angles(FOUR_ONLY, "plan")
        assert result["valid"] is True

    def test_quick_mode_does_not_require_convergence_angles(self):
        result = validate_angles(FOUR_ONLY, "quick")
        assert result["valid"] is True
        assert result["missing_angles"] == []

    def test_quick_mode_blocks_when_lens_missing(self):
        angles = [a for a in FOUR_ONLY if a != "scope"]
        result = validate_angles(angles, "quick")
        assert result["valid"] is False
        assert "scope" in result["missing_angles"]

    def test_quick_mode_empty_list_blocks_with_4_missing(self):
        result = validate_angles([], "quick")
        assert result["valid"] is False
        assert len(result["missing_angles"]) == 4


# ---------------------------------------------------------------------------
# Unknown mode fallback
# ---------------------------------------------------------------------------

class TestValidateAnglesUnknownMode:

    def test_unknown_mode_falls_back_to_full(self):
        result = validate_angles(FOUR_ONLY, "nonexistent_mode")
        assert result["valid"] is False
        assert len(result["missing_angles"]) == 7

    def test_unknown_mode_passes_with_all_11(self):
        result = validate_angles(ALL_11, "nonexistent_mode")
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# REQUIRED_ANGLES registry shape
# ---------------------------------------------------------------------------

class TestRequiredAnglesRegistry:

    def test_full_mode_has_11_angles(self):
        assert len(REQUIRED_ANGLES["full"]) == 11

    def test_quick_mode_has_4_angles(self):
        assert len(REQUIRED_ANGLES["quick"]) == 4

    def test_silent_mode_has_4_angles(self):
        assert len(REQUIRED_ANGLES["silent"]) == 4

    def test_plan_mode_has_4_angles(self):
        assert len(REQUIRED_ANGLES["plan"]) == 4

    def test_full_is_superset_of_quick(self):
        assert REQUIRED_ANGLES["quick"].issubset(REQUIRED_ANGLES["full"])

    def test_four_lenses_in_full_set(self):
        assert _FOUR_LENSES.issubset(REQUIRED_ANGLES["full"])

    def test_seven_convergence_in_full_set(self):
        assert _SEVEN_CONVERGENCE.issubset(REQUIRED_ANGLES["full"])
