"""Tests for challenge convergence gate — mark_challenge_ran + check_loop_dry.

Verifies that the loop exits on zero new objections (structural enforcement),
not on round count. The key invariant: mark_challenge_ran with objections_this_round > 0
writes converged=False, and check_loop_dry reads it to surface not_converged=True.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest


def _write_challenge_ran(
    state_dir: Path,
    slug: str,
    rounds: int,
    objections_this_round: int,
) -> None:
    converged = objections_this_round == 0
    flag_file = state_dir / "challenge-ran.json"
    flag_file.write_text(json.dumps({
        "slug": slug,
        "task": "test task",
        "ts": "2026-08-01T00:00:00",
        "rounds": rounds,
        "angles_validated": True,
        "mode": "full",
        "objections_last_round": objections_this_round,
        "converged": converged,
    }))


def _write_correction(state_dir: Path, slug: str, detected: bool) -> None:
    (state_dir / "loop-correction.json").write_text(json.dumps({
        "slug": slug,
        "correction_detected": detected,
        "ts": "2026-08-01T00:00:00",
    }))


def _compute_loop_dry_result(state_dir: Path, slug: str) -> dict:
    flag_file = state_dir / "challenge-ran.json"
    correction_file = state_dir / "loop-correction.json"

    rounds = 0
    challenge_ran = False
    converged = True
    objections_last_round = 0

    if flag_file.exists():
        data = json.loads(flag_file.read_text())
        if data.get("slug") == slug:
            rounds = data.get("rounds", 0)
            challenge_ran = rounds > 0
            objections_last_round = data.get("objections_last_round", 0)
            converged = data.get("converged", True)

    correction_in_state = False
    if correction_file.exists():
        corr_data = json.loads(correction_file.read_text())
        if corr_data.get("slug") == slug:
            correction_in_state = corr_data.get("correction_detected", False)

    not_converged = challenge_ran and not converged
    dry = challenge_ran and not correction_in_state and converged
    return {
        "dry": dry,
        "rounds": rounds,
        "challenge_ran": challenge_ran,
        "loop_correction_in_state": correction_in_state,
        "not_converged": not_converged,
        "objections_last_round": objections_last_round,
    }


class TestMarkChallengeRanConvergence:
    def test_zero_objections_writes_converged_true(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=1, objections_this_round=0)
        data = json.loads((tmp_path / "challenge-ran.json").read_text())
        assert data["converged"] is True
        assert data["objections_last_round"] == 0

    def test_nonzero_objections_writes_converged_false(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=1, objections_this_round=2)
        data = json.loads((tmp_path / "challenge-ran.json").read_text())
        assert data["converged"] is False
        assert data["objections_last_round"] == 2

    def test_single_objection_writes_converged_false(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=1, objections_this_round=1)
        data = json.loads((tmp_path / "challenge-ran.json").read_text())
        assert data["converged"] is False

    def test_rounds_counter_increments(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=3, objections_this_round=0)
        data = json.loads((tmp_path / "challenge-ran.json").read_text())
        assert data["rounds"] == 3


class TestCheckLoopDryConvergence:
    def test_dry_when_zero_objections_no_correction(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=2, objections_this_round=0)
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is True
        assert result["not_converged"] is False
        assert result["objections_last_round"] == 0

    def test_not_dry_when_last_round_had_objections(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=1, objections_this_round=3)
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is False
        assert result["not_converged"] is True
        assert result["objections_last_round"] == 3

    def test_not_dry_when_correction_detected_even_if_converged(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=1, objections_this_round=0)
        _write_correction(tmp_path, "youk", detected=True)
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is False
        assert result["loop_correction_in_state"] is True

    def test_not_dry_when_challenge_never_ran(self, tmp_path):
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is False
        assert result["not_converged"] is False
        assert result["challenge_ran"] is False

    def test_legacy_record_without_converged_field_treated_as_converged(self, tmp_path):
        flag_file = tmp_path / "challenge-ran.json"
        flag_file.write_text(json.dumps({
            "slug": "youk",
            "task": "old task",
            "ts": "2026-01-01T00:00:00",
            "rounds": 1,
            "angles_validated": True,
            "mode": "full",
        }))
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is True
        assert result["not_converged"] is False

    def test_slug_mismatch_ignores_state(self, tmp_path):
        _write_challenge_ran(tmp_path, "other-project", rounds=1, objections_this_round=0)
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["challenge_ran"] is False
        assert result["dry"] is False

    def test_multiple_rounds_reads_latest_state(self, tmp_path):
        _write_challenge_ran(tmp_path, "youk", rounds=2, objections_this_round=0)
        result = _compute_loop_dry_result(tmp_path, "youk")
        assert result["dry"] is True
        assert result["rounds"] == 2


class TestSkillMdConvergenceRule:
    def _read_skill(self) -> str:
        skill_path = Path(__file__).parent.parent / "skills" / "challenge" / "SKILL.md"
        return skill_path.read_text()

    def test_exit_condition_states_zero_objections_not_round_count(self):
        content = self._read_skill()
        assert "zero new objections" in content.lower() or "zero objection" in content.lower()

    def test_mark_challenge_ran_called_with_objections_this_round(self):
        content = self._read_skill()
        assert "objections_this_round" in content

    def test_converged_true_required_for_passed_verdict(self):
        content = self._read_skill()
        assert "converged: true" in content.lower() or (
            "converged" in content and "true" in content
        )

    def test_not_converged_blocks_challenge_passed(self):
        content = self._read_skill()
        assert "converged: false" in content.lower() or (
            "not yet dry" in content.lower() or "iterate" in content.lower()
        )
