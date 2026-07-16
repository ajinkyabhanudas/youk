"""
Drift sentinel tests for the four depth fixes added to challenge/SKILL.md
and the adversary-loop skill.

These tests assert that key structural sections exist in the skill files.
They catch /forge or manual regeneration silently dropping load-bearing instructions.
"""
from __future__ import annotations
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "code" / "src"))

_YOUK_ROOT = Path(__file__).parent.parent
_CHALLENGE_SKILL = _YOUK_ROOT / "skills" / "challenge" / "SKILL.md"
_ADVERSARY_SKILL = _YOUK_ROOT / "skills" / "adversary-loop" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text()


# ---------------------------------------------------------------------------
# Fix 1 — Abstraction-level declaration in Lens 1
# ---------------------------------------------------------------------------

class TestAbstractionLevelDeclaration:

    def test_abstraction_level_section_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Abstraction-level declaration" in content

    def test_four_levels_named(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Goal" in content
        assert "Strategy" in content
        assert "Tactic" in content
        assert "Implementation" in content

    def test_highest_level_instruction_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "highest relevant level" in content

    def test_tactic_implementation_trigger_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Tactic or Implementation" in content


# ---------------------------------------------------------------------------
# Fix 2 — Steelman gate per lens
# ---------------------------------------------------------------------------

class TestSteelmanGate:

    def test_steelman_gate_section_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Steelman gate" in content

    def test_steelman_format_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Steelman:" in content
        assert "Verdict:" in content

    def test_steelman_weak_holds_verdicts_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "WEAK" in content
        assert "HOLDS" in content

    def test_steelman_holds_converts_to_high(self):
        content = _read(_CHALLENGE_SKILL)
        assert "convert" in content.lower() or "HIGH, not CLEAR" in content or "HIGH" in content

    def test_one_word_steelman_rejected(self):
        content = _read(_CHALLENGE_SKILL)
        assert "one-word" in content.lower() or '"nothing"' in content or "not valid" in content


# ---------------------------------------------------------------------------
# Fix 3 — Inter-angle coherence check
# ---------------------------------------------------------------------------

class TestInterAngleCoherence:

    def test_inter_angle_coherence_section_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "INTER-ANGLE COHERENCE" in content

    def test_aligned_diverged_verdicts_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "ALIGNED" in content
        assert "DIVERGED" in content

    def test_diverged_is_high_objection(self):
        content = _read(_CHALLENGE_SKILL)
        assert "HIGH objection" in content or "divergence is a HIGH" in content

    def test_coherence_check_before_mark_challenge_ran(self):
        content = _read(_CHALLENGE_SKILL)
        coherence_pos = content.find("INTER-ANGLE COHERENCE")
        mark_pos = content.find("mark_challenge_ran")
        assert coherence_pos < mark_pos, (
            "Inter-angle coherence check must appear before mark_challenge_ran call"
        )


# ---------------------------------------------------------------------------
# Fix 4 — CLEAR positive-claim rule
# ---------------------------------------------------------------------------

class TestClearPositiveClaim:

    def test_clear_requires_positive_claim_present(self):
        content = _read(_CHALLENGE_SKILL)
        assert "CLEAR requires a positive claim" in content

    def test_team_can_decide_rejected(self):
        content = _read(_CHALLENGE_SKILL)
        assert "team can decide" in content.lower()

    def test_deferral_masking_named(self):
        content = _read(_CHALLENGE_SKILL)
        assert "deferral" in content.lower() or "Deferral" in content

    def test_false_convergence_pattern_named(self):
        content = _read(_CHALLENGE_SKILL)
        assert "false-convergence" in content or "false convergence" in content.lower()


# ---------------------------------------------------------------------------
# Adversary-loop skill existence and structure
# ---------------------------------------------------------------------------

class TestAdversaryLoopSkill:

    def test_skill_file_exists(self):
        assert _ADVERSARY_SKILL.exists(), "adversary-loop/SKILL.md must exist"

    def test_adversary_dry_signal_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "ADVERSARY DRY" in content

    def test_adversary_found_signal_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "ADVERSARY FOUND" in content

    def test_handoff_stripping_instruction_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "stripped" in content.lower() or "strip" in content.lower()

    def test_proposer_cannot_declare_dry(self):
        content = _read(_ADVERSARY_SKILL)
        assert "Proposer cannot declare dry" in content or "proposer" in content.lower()

    def test_stuck_loop_is_blocking(self):
        content = _read(_ADVERSARY_SKILL)
        assert "Stuck" in content or "stuck" in content

    def test_ten_round_emergency_brake_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "10 rounds" in content or "Round 10" in content

    def test_tier_routing_table_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "Tier Routing" in content or "tier routing" in content.lower()

    def test_m_plus_uses_adversary_loop(self):
        content = _read(_ADVERSARY_SKILL)
        assert "M/L/XL" in content or "M+" in content

    def test_s_uses_in_session_challenge(self):
        content = _read(_ADVERSARY_SKILL)
        assert "in-session challenge" in content

    def test_patterns_field_in_handoff(self):
        content = _read(_ADVERSARY_SKILL)
        assert "failure_patterns" in content
        assert "shortcut_patterns" in content

    def test_rca_trigger_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "Phase 4" in content and "RCA" in content

    def test_rca_routes_through_learn(self):
        content = _read(_ADVERSARY_SKILL)
        assert "learn" in content and "rca" in content.lower()

    def test_verdict_confirmed_on_dry_rerun(self):
        content = _read(_ADVERSARY_SKILL)
        assert "VERDICT CONFIRMED" in content

    def test_efficiency_scoring_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "EFFICIENT" in content
        assert "MODERATE" in content
        assert "COSTLY" in content

    def test_justified_overrun_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "JUSTIFIED OVERRUN" in content

    def test_depth_reward_is_significant(self):
        content = _read(_ADVERSARY_SKILL)
        assert "DEPTH REWARD" in content
        assert "prevented_cost_score" in content

    def test_shortcut_pattern_from_depth_reward(self):
        content = _read(_ADVERSARY_SKILL)
        assert "shortcut pattern" in content.lower() or "Shortcut patterns" in content

    def test_silence_discipline_present(self):
        content = _read(_ADVERSARY_SKILL)
        assert "Silence Discipline" in content or "silence" in content.lower()

    def test_verdict_format_has_efficiency(self):
        content = _read(_ADVERSARY_SKILL)
        assert "ADVERSARY LOOP PASSED" in content and "EFFICIENT" in content


# ---------------------------------------------------------------------------
# challenge/SKILL.md — round cap updated to 10
# ---------------------------------------------------------------------------

class TestChallengeRoundCap:

    def test_ten_round_cap_in_exit_rule(self):
        content = _read(_CHALLENGE_SKILL)
        assert "Ten rounds" in content or "10 rounds" in content or "Round 10" in content

    def test_five_round_cap_removed(self):
        content = _read(_CHALLENGE_SKILL)
        # "Five rounds" should not appear as the cap (may appear in other contexts)
        assert "Five rounds is the emergency brake" not in content

    def test_efficiency_scoring_in_challenge(self):
        content = _read(_CHALLENGE_SKILL)
        assert "EFFICIENT" in content or "Efficiency scoring" in content


# ---------------------------------------------------------------------------
# reasoning-integrity.md — RCA section headers present
# ---------------------------------------------------------------------------

_REASONING_INTEGRITY = _YOUK_ROOT / "knowledge" / "domain" / "reasoning-integrity.md"

# knowledge/domain/ is gitignored — these tests only run when the local file exists.
_reasoning_integrity_present = pytest.mark.skipif(
    not _REASONING_INTEGRITY.exists(),
    reason="knowledge/domain/reasoning-integrity.md is local-only (gitignored); skip in CI",
)


class TestReasoningIntegrityRcaSections:

    @_reasoning_integrity_present
    def test_adversary_failure_patterns_section_present(self):
        content = _read(_REASONING_INTEGRITY)
        assert "Adversary Failure Patterns" in content

    @_reasoning_integrity_present
    def test_adversary_shortcut_patterns_section_present(self):
        content = _read(_REASONING_INTEGRITY)
        assert "Adversary Shortcut Patterns" in content
