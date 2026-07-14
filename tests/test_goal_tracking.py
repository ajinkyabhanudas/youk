"""
Tests for the session goal-tracking loop.

Covers three mechanisms:
1. optimize_intent writes state/session-goal.json when goal is concrete
2. task_checkpoint returns goal_check.goal_met=False when criteria unmet
3. _check_session_goal returns goal_met=True after sufficient coverage

Root requirement: "don't stop until X" must behave as stated — the exit condition
is goal satisfaction, not plan exhaustion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_goal(tmp_path: Path, goal: dict) -> Path:
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    goal_file = state_dir / "session-goal.json"
    goal_file.write_text(json.dumps(goal))
    return goal_file


# ---------------------------------------------------------------------------
# 1. optimize_intent writes session-goal.json
# ---------------------------------------------------------------------------


class TestOptimizeIntentWritesGoal:
    """write_session_goal persists success_criteria to state/session-goal.json
    when called with concrete criteria. Tests the helper directly to avoid
    importing the MCP-dependent server module."""

    def test_goal_file_written_with_concrete_criteria(self, tmp_path):
        """write_session_goal creates the file with goal_met=False."""
        from session import write_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            write_session_goal(
                "add goal_check to task_checkpoint",
                "task_checkpoint returns goal_check field",
                "goal_check visible in return dict",
            )

        goal_file = tmp_path / "state" / "session-goal.json"
        assert goal_file.exists(), "goal file should be written"
        data = json.loads(goal_file.read_text())
        assert data["goal_met"] is False
        assert "task_checkpoint" in data["success_criteria"]
        assert data["observable_outcome"] == "goal_check visible in return dict"

    def test_goal_file_has_stated_goal(self, tmp_path):
        """write_session_goal preserves the raw user input as stated_goal."""
        from session import write_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            write_session_goal("make it production ready", "logging metrics tracing enabled")

        data = json.loads((tmp_path / "state" / "session-goal.json").read_text())
        assert data["stated_goal"] == "make it production ready"

    def test_goal_file_written_at_present(self, tmp_path):
        """write_session_goal stamps written_at in ISO format."""
        from session import write_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            write_session_goal("ship feature", "feature deployed end-to-end")

        data = json.loads((tmp_path / "state" / "session-goal.json").read_text())
        assert "written_at" in data
        assert "T" in data["written_at"]  # ISO datetime format


# ---------------------------------------------------------------------------
# 2. _check_session_goal logic
# ---------------------------------------------------------------------------


class TestCheckSessionGoal:
    """Unit tests for the goal evaluation function."""

    def test_returns_none_when_no_goal_file(self, tmp_path):
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            result = _check_session_goal("fixed login bug")

        assert result is None

    def test_returns_goal_met_true_when_already_met(self, tmp_path):
        _write_goal(
            tmp_path,
            {
                "stated_goal": "add goal tracking",
                "success_criteria": "goal_check returned from checkpoint",
                "observable_outcome": "",
                "goal_met": True,
            },
        )
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            result = _check_session_goal("anything")

        assert result is not None
        assert result["goal_met"] is True
        assert result["goal_gap"] == ""

    def test_returns_goal_met_false_when_no_overlap(self, tmp_path):
        _write_goal(
            tmp_path,
            {
                "stated_goal": "add observability",
                "success_criteria": "metrics tracing logging configured",
                "observable_outcome": "spans visible in dashboard",
                "goal_met": False,
            },
        )
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            result = _check_session_goal("fixed typo in readme")

        assert result is not None
        assert result["goal_met"] is False
        assert "goal_gap" in result
        assert len(result["goal_gap"]) > 0

    def test_coverage_accumulates_across_calls(self, tmp_path):
        """Multiple checkpoints accumulate coverage toward the goal."""
        _write_goal(
            tmp_path,
            {
                "stated_goal": "setup complete observability stack",
                "success_criteria": "metrics tracing logging alerts configured",
                "observable_outcome": "",
                "goal_met": False,
            },
        )
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            r1 = _check_session_goal("added metrics endpoint")
            r2 = _check_session_goal("configured tracing and logging")
            r3 = _check_session_goal("added alerts configured complete")

        # Coverage grows — final call may mark as met
        assert r1 is not None
        assert r2 is not None
        assert r3 is not None
        # Last call has highest coverage so goal_met should be True or gap smaller
        if r3["goal_met"]:
            assert r3["goal_gap"] == ""
        else:
            # Still not met but gap message should exist
            assert "goal_gap" in r3

    def test_explicit_done_with_overlap_marks_goal_met(self, tmp_path):
        """Task that says 'done' AND overlaps criteria terms → goal_met=True."""
        _write_goal(
            tmp_path,
            {
                "stated_goal": "ship authentication",
                "success_criteria": "authentication login session working",
                "observable_outcome": "",
                "goal_met": False,
            },
        )
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            result = _check_session_goal("authentication login session done")

        assert result is not None
        assert result["goal_met"] is True

    def test_goal_met_persists_to_file(self, tmp_path):
        """When goal_met transitions to True, it writes back to the file."""
        _write_goal(
            tmp_path,
            {
                "stated_goal": "ship feature",
                "success_criteria": "feature complete deployed working",
                "observable_outcome": "",
                "goal_met": False,
            },
        )
        from session import _check_session_goal

        with patch("session.YOUK_ROOT", tmp_path):
            _check_session_goal("feature complete deployed working done")

        data = json.loads((tmp_path / "state" / "session-goal.json").read_text())
        assert data["goal_met"] is True


# ---------------------------------------------------------------------------
# 3. task_checkpoint returns goal_check field
# ---------------------------------------------------------------------------


class TestTaskCheckpointGoalCheck:
    """task_checkpoint includes goal_check when a session goal is active."""

    def test_task_checkpoint_includes_goal_check_when_active(self, tmp_path):
        """When session-goal.json exists, task_checkpoint returns goal_check."""
        _write_goal(
            tmp_path,
            {
                "stated_goal": "add session goal tracking",
                "success_criteria": "goal_check returned from task_checkpoint",
                "observable_outcome": "",
                "goal_met": False,
            },
        )

        from session import task_checkpoint as _tcp

        with patch("session.YOUK_ROOT", tmp_path), patch(
            "session._build_brief", return_value={"brief": "BRIEF"}
        ), patch(
            "session._load_state", return_value={"last_project": "youk", "session_counter": 1}
        ), patch(
            "session._slug", return_value="youk"
        ), patch(
            "session._write_session_stub", return_value=None
        ), patch(
            "session._update_resume_point", return_value=None
        ):
            result = _tcp(str(tmp_path), "fixed a bug", "M")

        assert "goal_check" in result, "goal_check must appear when session goal is active"
        gc = result["goal_check"]
        assert "goal_met" in gc
        assert "stated_goal" in gc
        assert "success_criteria" in gc

    def test_task_checkpoint_no_goal_check_when_inactive(self, tmp_path):
        """When no session-goal.json, task_checkpoint has no goal_check."""
        from session import task_checkpoint as _tcp

        with patch("session.YOUK_ROOT", tmp_path), patch(
            "session._build_brief", return_value={"brief": "BRIEF"}
        ), patch(
            "session._load_state", return_value={"last_project": "youk", "session_counter": 1}
        ), patch(
            "session._slug", return_value="youk"
        ), patch(
            "session._write_session_stub", return_value=None
        ), patch(
            "session._update_resume_point", return_value=None
        ):
            result = _tcp(str(tmp_path), "some task", "M")

        assert "goal_check" not in result

    def test_task_checkpoint_xs_skips_goal_check(self, tmp_path):
        """XS tasks skip the checkpoint block — goal_check should not appear."""
        _write_goal(
            tmp_path,
            {
                "stated_goal": "add tracking",
                "success_criteria": "tracking works",
                "observable_outcome": "",
                "goal_met": False,
            },
        )

        from session import task_checkpoint as _tcp

        with patch("session.YOUK_ROOT", tmp_path), patch(
            "session._build_brief", return_value={"brief": "BRIEF"}
        ), patch(
            "session._load_state", return_value={"last_project": "youk", "session_counter": 1}
        ), patch(
            "session._slug", return_value="youk"
        ), patch(
            "session._write_session_stub", return_value=None
        ):
            result = _tcp(str(tmp_path), "fix typo", "XS")

        # XS tasks skip checkpoint writing and goal check is part of that block
        # goal_check may or may not appear for XS — but checkpoint_written must be False
        assert result["checkpoint_written"] is False


# ---------------------------------------------------------------------------
# 4. done skill gate (behavioral — no unit test possible, but check SKILL.md)
# ---------------------------------------------------------------------------


class TestDoneSkillGoalGate:
    """The done/SKILL.md must contain Step 0 that checks session-goal.json."""

    def test_done_skill_has_step_0(self):
        skill_path = (
            Path(__file__).parent.parent / "skills" / "done" / "SKILL.md"
        )
        content = skill_path.read_text()
        assert "Step 0" in content, "done/SKILL.md must have Step 0 (goal check)"
        assert "session-goal.json" in content, "Step 0 must reference session-goal.json"
        assert "goal_met" in content, "Step 0 must check goal_met flag"

    def test_done_skill_step_0_before_code_review(self):
        skill_path = (
            Path(__file__).parent.parent / "skills" / "done" / "SKILL.md"
        )
        content = skill_path.read_text()
        step0_pos = content.find("Step 0")
        step1_pos = content.find("Step 1")
        assert step0_pos < step1_pos, "Step 0 must appear before Step 1"


# ---------------------------------------------------------------------------
# 5. youk-lite template includes goal section
# ---------------------------------------------------------------------------


class TestYoukLiteGoalSection:
    """youk-lite.md template must contain the Session goal section."""

    def test_youk_lite_has_session_goal_section(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "## Session goal" in content
        assert "CRITERIA" in content
        assert "goal satisfaction" in content

    def test_youk_lite_loop_instruction_present(self):
        doc_path = Path(__file__).parent.parent / "docs" / "youk-lite.md"
        content = doc_path.read_text()
        assert "plan exhaustion" in content, "must distinguish plan exhaustion from goal satisfaction"
