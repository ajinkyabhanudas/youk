"""Tests for the nfr_autonomy_mode branch in nfr.py — Phase 2 of the
reaction-classifier plan (~/.claude/plans/zany-squishing-crayon.md).

session.py already computes nfr_autonomy_mode ("standard" vs "validate", based on
a 90-day rolling nfr_check autonomy rate >= 0.4) and returns it from session_start,
but nothing downstream ever read it — a real, currently-inert decision point. These
tests pin the branch that makes it live: "validate" only changes the M-path
instruction text (coverage-check framing instead of fresh-prompting framing), never
the questions asked or the L/XL path, and any unrecognized value safely falls back
to "standard".
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nfr import nfr_check_quick, run_nfr_check, _QUICK_4Q_QUESTIONS
from models import TaskSize


@pytest.fixture(autouse=True)
def _real_skills_dir(monkeypatch):
    """nfr.py loads the real nfr-check/SKILL.md by name; point skill_loader at
    this checkout's actual skills/ directory rather than the production /claude
    mount these tests don't have."""
    import skill_loader
    repo_skills = Path(__file__).parent.parent / "skills"
    monkeypatch.setattr(skill_loader, "SKILLS_DIR", repo_skills)


class TestNfrCheckQuickDefaultsToStandard:
    def test_no_argument_is_standard(self):
        result = nfr_check_quick("do the thing")
        assert result["autonomy_mode"] == "standard"

    def test_explicit_standard(self):
        result = nfr_check_quick("do the thing", autonomy_mode="standard")
        assert result["autonomy_mode"] == "standard"

    def test_unrecognized_value_falls_back_to_standard(self):
        result = nfr_check_quick("do the thing", autonomy_mode="not-a-real-mode")
        assert result["autonomy_mode"] == "standard"


class TestNfrCheckQuickValidateMode:
    def test_validate_sets_the_field(self):
        result = nfr_check_quick("do the thing", autonomy_mode="validate")
        assert result["autonomy_mode"] == "validate"

    def test_validate_and_standard_ask_the_same_questions(self):
        """The mode changes how the answer is framed, never what's being checked."""
        standard = nfr_check_quick("do the thing", autonomy_mode="standard")
        validate = nfr_check_quick("do the thing", autonomy_mode="validate")
        assert standard["questions"] == validate["questions"] == _QUICK_4Q_QUESTIONS

    def test_validate_instruction_says_confirm_not_derive(self):
        result = nfr_check_quick("do the thing", autonomy_mode="validate")
        assert "CONFIRMED" in result["instruction"]

    def test_standard_and_validate_instructions_differ(self):
        standard = nfr_check_quick("do the thing", autonomy_mode="standard")
        validate = nfr_check_quick("do the thing", autonomy_mode="validate")
        assert standard["instruction"] != validate["instruction"]


class TestRunNfrCheckThreadsAutonomyMode:
    def test_m_task_validate_mode_reaches_the_quick_path(self):
        result = run_nfr_check("do the thing", "M", autonomy_mode="validate")
        assert result["autonomy_mode"] == "validate"

    def test_m_task_default_is_standard(self):
        result = run_nfr_check("do the thing", "M")
        assert result["autonomy_mode"] == "standard"

    def test_xs_task_ignores_autonomy_mode(self):
        """Fast path (XS/S) returns an NFRBlock — no autonomy_mode field exists there."""
        result = run_nfr_check("tiny fix", "XS", autonomy_mode="validate")
        assert result.size == TaskSize.S
        assert not hasattr(result, "autonomy_mode")

    def test_xl_task_ignores_autonomy_mode(self):
        """L/XL always run the full check — higher-stakes work earns no reduction."""
        result = run_nfr_check("big architecture change", "XL", autonomy_mode="validate")
        assert "autonomy_mode" not in result
