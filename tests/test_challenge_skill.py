"""
Calibration testbench for the challenge skill (skills/challenge/SKILL.md).

These tests do NOT execute the full LLM skill — they validate the skill's
structural specification: required sections, quality bars, invocation grammar,
example flows, and constraint taxonomy. They catch drift when the skill is edited.

Drift detection rationale: the challenge skill is the direction gate for all M+
tasks. If it loses its BLOCKING stop, its constraint-respect rule, or its two-round
exit condition, rabbit-hole prevention silently breaks. These tests make that
break visible at CI time.

Test taxonomy:
  TestChallengeSkillStructure     — required sections present and non-empty
  TestChallengeSkillQualityBars   — each named quality bar encoded in SKILL.md
  TestChallengeSkillInvocation    — all invocation modes documented
  TestChallengeSkillLenses        — all four lenses present with probe questions
  TestChallengeSkillExitCondition — two-round cap and BLOCKING stop encoded
  TestChallengeSkillConstraintRespect — fixed constraint handling specified
  TestChallengeSkillHiringValidation  — all 5 hiring validation scenarios present
  TestChallengeSkillExampleFlows  — rabbit hole case and silent mode present
  TestChallengeSkillDriftSentinels — canary assertions that catch silent degradation
"""
from __future__ import annotations
import re
import pytest
from pathlib import Path


SKILLS_DIR = Path(__file__).parent.parent / "skills"
CHALLENGE_SKILL = SKILLS_DIR / "challenge" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_content() -> str:
    assert CHALLENGE_SKILL.exists(), (
        f"challenge skill not found at {CHALLENGE_SKILL} — "
        "was it deleted or moved?"
    )
    return CHALLENGE_SKILL.read_text()


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestChallengeSkillStructure:
    """Required sections must be present and non-empty."""

    def test_has_frontmatter(self, skill_content):
        assert skill_content.startswith("---"), "SKILL.md must open with YAML frontmatter"

    def test_frontmatter_has_name(self, skill_content):
        assert "name: challenge" in skill_content

    def test_frontmatter_has_description(self, skill_content):
        assert "description:" in skill_content

    def test_has_invocation_grammar_section(self, skill_content):
        assert "## Invocation Grammar" in skill_content

    def test_has_context_capture_section(self, skill_content):
        assert "## Context Capture" in skill_content

    def test_has_at_least_two_phases(self, skill_content):
        phases = re.findall(r"### Phase \d+ —", skill_content)
        assert len(phases) >= 2, f"Expected ≥2 phases, found {len(phases)}"

    def test_has_quality_bars_section(self, skill_content):
        assert "## Quality Bars" in skill_content

    def test_has_hiring_validation_section(self, skill_content):
        assert "Hiring Validation" in skill_content

    def test_has_example_flows_section(self, skill_content):
        assert "## Example Flows" in skill_content

    def test_description_mentions_direction_not_plan(self, skill_content):
        # The challenge skill attacks direction, not plan execution (that's stress-test).
        # If this drifts to "attacks the plan", the two skills conflate.
        assert "direction" in skill_content[:500].lower(), (
            "Frontmatter description must mention 'direction' — "
            "challenge gates direction, not plan execution"
        )

    def test_description_distinguishes_from_stress_test(self, skill_content):
        assert "stress-test" in skill_content or "stress_test" in skill_content, (
            "SKILL.md must explicitly distinguish challenge from stress-test "
            "to prevent routing conflation"
        )


# ---------------------------------------------------------------------------
# Invocation Grammar
# ---------------------------------------------------------------------------

class TestChallengeSkillInvocation:
    """All invocation modes must be documented."""

    REQUIRED_MODES = ["quick", "silent", "framing only", "assumptions only", "retest"]

    def test_all_required_modes_present(self, skill_content):
        for mode in self.REQUIRED_MODES:
            assert mode in skill_content, (
                f"Invocation mode '{mode}' missing from Invocation Grammar — "
                f"removing modes breaks callers that use them"
            )

    def test_silent_mode_documented(self, skill_content):
        assert "silent" in skill_content, "silent mode must be documented"

    def test_no_directive_row_present(self, skill_content):
        # The *(no directive)* row is the default full invocation
        assert "no directive" in skill_content, (
            "Default invocation (no directive) row missing from grammar table"
        )


# ---------------------------------------------------------------------------
# Four Lenses
# ---------------------------------------------------------------------------

class TestChallengeSkillLenses:
    """All four lenses must be present with their probe questions."""

    REQUIRED_LENSES = [
        "Problem Framing",
        "Scope Creep",
        "Hidden Assumptions",
        "Opportunity Cost",
    ]

    def test_all_four_lenses_present(self, skill_content):
        for lens in self.REQUIRED_LENSES:
            assert lens in skill_content, (
                f"Lens '{lens}' missing — removing a lens reduces coverage and "
                f"breaks the four-angle independence property"
            )

    def test_lens_1_has_simpler_version_probe(self, skill_content):
        # Lens 1 must ask whether a simpler version achieves the same outcome
        assert "simpler version" in skill_content, (
            "Lens 1 must probe for simpler framing — this is the primary "
            "rabbit-hole catch (the two-level reasoning system case)"
        )

    def test_lens_2_has_minimum_version_probe(self, skill_content):
        assert "minimum version" in skill_content, (
            "Lens 2 must probe for minimum viable direction — "
            "this is the scope-creep catch"
        )

    def test_lens_3_has_assumption_probes(self, skill_content):
        assert "assumes" in skill_content.lower(), (
            "Lens 3 must contain assumption probes"
        )

    def test_lens_4_has_opportunity_cost_probe(self, skill_content):
        assert "highest-leverage" in skill_content or "opportunity" in skill_content.lower(), (
            "Lens 4 must probe opportunity cost"
        )

    def test_lenses_are_independent(self, skill_content):
        # Independence is stated explicitly in the skill — if removed, correlation risk rises
        assert "independent" in skill_content, (
            "Lenses must be described as independent — "
            "if they share output, the multi-angle property collapses"
        )


# ---------------------------------------------------------------------------
# Quality Bars
# ---------------------------------------------------------------------------

class TestChallengeSkillQualityBars:
    """Each named quality bar must be encoded."""

    def test_specificity_bar_present(self, skill_content):
        assert "specific" in skill_content.lower(), (
            "Quality bar: objections must be specific — "
            "vague objections are the failure mode this bar prevents"
        )

    def test_fixed_constraints_bar_present(self, skill_content):
        # The constraint-respect bar is the most critical — it prevents the skill
        # from attacking walls and producing false contradictions
        assert "Fixed constraint" in skill_content or "FIXED_CONSTRAINT" in skill_content, (
            "Quality bar: fixed constraints must never be attacked — "
            "removing this bar breaks the constraint-respect property"
        )

    def test_blocking_means_stop_bar_present(self, skill_content):
        assert "BLOCKING means stop" in skill_content or (
            "BLOCKING" in skill_content and "stop" in skill_content
        ), (
            "Quality bar: BLOCKING must mean work stops — "
            "if this bar is removed, BLOCKING becomes advisory and the gate breaks"
        )

    def test_two_round_maximum_bar_present(self, skill_content):
        assert "two rounds" in skill_content.lower() or "maximum" in skill_content.lower(), (
            "Quality bar: two-round maximum must be enforced — "
            "without this, the loop has no exit condition"
        )

    def test_low_objections_do_not_block_bar_present(self, skill_content):
        assert "LOW" in skill_content and "not block" in skill_content.lower(), (
            "Quality bar: LOW objections must not block — "
            "if LOW becomes blocking, the skill adds friction without value"
        )

    def test_silent_mode_only_speaks_on_blocking(self, skill_content):
        assert "silent" in skill_content and "BLOCKING" in skill_content, (
            "Quality bar: silent mode must only surface BLOCKING objections — "
            "if silent mode becomes verbose, it produces noise on every M+ task"
        )


# ---------------------------------------------------------------------------
# Exit Condition and BLOCKING Stop
# ---------------------------------------------------------------------------

class TestChallengeSkillExitCondition:
    """Two-round cap and BLOCKING hard stop must be encoded in phase logic."""

    def test_two_round_cap_in_phase_3(self, skill_content):
        # Phase 3 is the iteration phase — must have explicit exit rule
        assert "Maximum two rounds" in skill_content or "two round" in skill_content.lower(), (
            "Phase 3 must encode the two-round maximum — "
            "infinite loops produce paralysis, not quality"
        )

    def test_blocking_triggers_stop_not_footnote(self, skill_content):
        # The skill must direct stopping, not noting, when BLOCKING is found
        assert "work does not start" in skill_content or "stop" in skill_content, (
            "BLOCKING verdict must stop work, not footnote it"
        )

    def test_exit_on_silence_stated(self, skill_content):
        assert "Exit on silence" in skill_content or "exit condition" in skill_content.lower() or \
               "nothing new" in skill_content, (
            "Exit condition must be explicit: loop exits when no new objections are found"
        )

    def test_phase_3_only_runs_on_needs_sharpening(self, skill_content):
        assert "NEEDS SHARPENING" in skill_content, (
            "Phase 3 conditional trigger must be named — "
            "if removed, Phase 3 runs unconditionally and always iterates"
        )

    def test_direction_wrong_verdict_present(self, skill_content):
        assert "DIRECTION WRONG" in skill_content or "direction WRONG" in skill_content, (
            "BLOCKING verdict label must be present — "
            "CLAUDE.md routes on this string to stop and surface to user"
        )


# ---------------------------------------------------------------------------
# Constraint Respect
# ---------------------------------------------------------------------------

class TestChallengeSkillConstraintRespect:
    """Fixed constraint handling must be specified in context capture and quality bars."""

    def test_fixed_constraints_in_context_capture(self, skill_content):
        assert "FIXED_CONSTRAINTS" in skill_content, (
            "Context Capture must include FIXED_CONSTRAINTS field — "
            "without it, the skill has no way to know what is a wall"
        )

    def test_constraint_inference_from_conversation(self, skill_content):
        # The skill must infer constraints from conversation, not ask
        assert "Infer" in skill_content or "infer" in skill_content, (
            "Skill must infer fixed constraints from conversation — "
            "asking the user for constraints adds friction on every M+ task"
        )

    def test_constraints_described_as_walls_not_surfaces(self, skill_content):
        assert "wall" in skill_content.lower(), (
            "Fixed constraints must be described as walls not attack surfaces — "
            "this is the phrasing that prevents Lens 3 from attacking them"
        )

    def test_constraint_markers_listed(self, skill_content):
        # The skill must give examples of constraint language to scan for
        constraint_markers = ["we're using", "we can't", "given that"]
        found = any(m in skill_content for m in constraint_markers)
        assert found, (
            "Skill must list constraint language markers (e.g. 'we're using X') — "
            "without examples, constraint inference is undefined"
        )


# ---------------------------------------------------------------------------
# Hiring Validation
# ---------------------------------------------------------------------------

class TestChallengeSkillHiringValidation:
    """All 5 hiring validation scenarios must be present."""

    def test_constraint_respect_scenario(self, skill_content):
        assert "Constraint respect" in skill_content or "Redis" in skill_content, (
            "Hiring validation must include the constraint-respect scenario (Redis/task-queue)"
        )

    def test_blocking_stop_scenario(self, skill_content):
        assert "BLOCKING stop" in skill_content or "DIRECTION WRONG" in skill_content, (
            "Hiring validation must include the BLOCKING hard-stop scenario"
        )

    def test_scope_lens_fires_scenario(self, skill_content):
        # The two-level reasoning system is the canonical scope-creep example
        assert "two-level" in skill_content or "Scope lens" in skill_content, (
            "Hiring validation must include the scope-lens scenario "
            "(the two-level reasoning system rabbit hole case)"
        )

    def test_silent_mode_discipline_scenario(self, skill_content):
        assert "Silent mode discipline" in skill_content or \
               ("silent" in skill_content and "LOW objections" in skill_content), (
            "Hiring validation must include the silent mode discipline scenario"
        )

    def test_two_round_exit_scenario(self, skill_content):
        assert "Two-round exit" in skill_content or \
               ("round 2" in skill_content.lower() and "stops" in skill_content.lower()), (
            "Hiring validation must include the two-round exit scenario"
        )


# ---------------------------------------------------------------------------
# Example Flows
# ---------------------------------------------------------------------------

class TestChallengeSkillExampleFlows:
    """Key example flows must be present to demonstrate invocation modes."""

    def test_rabbit_hole_example_present(self, skill_content):
        # This is the canonical case: the two-level reasoning system was the rabbit hole
        assert "rabbit hole" in skill_content.lower() or "two-level" in skill_content, (
            "Example flows must include the rabbit hole case — "
            "this is the primary design motivation for the skill"
        )

    def test_silent_mode_example_present(self, skill_content):
        assert "Silent mode" in skill_content or "silent mode" in skill_content, (
            "Example flows must include a silent mode example — "
            "without it, implementers don't know when to suppress output"
        )

    def test_direction_confirmed_skip_example_present(self, skill_content):
        # When direction is already confirmed this session, challenge should skip
        assert "already confirmed" in skill_content or "already resolved" in skill_content or \
               "explicitly confirmed" in skill_content, (
            "Example flows must show the skip case (direction already confirmed) — "
            "without it, the skill adds friction even when the user just said 'yes'"
        )

    def test_challenge_passed_token_present(self, skill_content):
        assert "[CHALLENGE PASSED]" in skill_content, (
            "The [CHALLENGE PASSED] output token must be in example flows — "
            "CLAUDE.md and route_task look for this token to proceed"
        )


# ---------------------------------------------------------------------------
# Drift Sentinels — canary assertions
# ---------------------------------------------------------------------------

class TestChallengeSkillDriftSentinels:
    """
    Canary assertions that catch silent degradation.
    These encode the specific properties that make the challenge skill work.
    If any fails after a SKILL.md edit, review the edit before merging.
    """

    def test_skill_is_not_empty(self, skill_content):
        assert len(skill_content) > 2000, (
            f"SKILL.md is suspiciously short ({len(skill_content)} chars) — "
            "likely truncated or replaced with a stub"
        )

    def test_phase_tokens_present(self, skill_content):
        # Phase tokens are how the skill signals phase transitions in output
        phase_tokens = re.findall(r"\[PHASE:", skill_content)
        assert len(phase_tokens) >= 2, (
            f"Expected ≥2 [PHASE:] tokens, found {len(phase_tokens)} — "
            "phase tokens drive output structure; missing = unstructured output"
        )

    def test_verdict_labels_complete(self, skill_content):
        # All verdict labels that CLAUDE.md and callers route on must be present
        required_verdicts = ["CHALLENGE PASSED", "NEEDS SHARPENING"]
        for v in required_verdicts:
            assert v in skill_content, (
                f"Verdict label '{v}' missing — callers route on these strings"
            )

    def test_lens_count_is_four(self, skill_content):
        # Drift risk: someone adds a fifth lens or removes one
        lens_matches = re.findall(r"\*\*Lens \d+ —", skill_content)
        assert len(lens_matches) == 4, (
            f"Expected exactly 4 lenses, found {len(lens_matches)} — "
            "adding/removing lenses changes the coverage model"
        )

    def test_no_directive_still_runs_all_lenses(self, skill_content):
        # Default invocation must run all lenses — if this drifts to "quick" by default,
        # the full challenge loop is never used
        grammar_section = skill_content[
            skill_content.find("## Invocation Grammar"):
            skill_content.find("## Context Capture")
        ]
        assert "all four" in grammar_section.lower() or "full" in grammar_section.lower(), (
            "Default (no directive) invocation must run all four lenses — "
            "if default becomes quick, M+ tasks get reduced coverage silently"
        )

    def test_challenge_skill_does_not_mention_plan_execution(self, skill_content):
        # challenge attacks direction; stress-test attacks plan execution
        # If "plan execution" appears in challenge, the two skills are conflating
        lower = skill_content.lower()
        plan_exec_phrases = ["plan execution", "attacks the plan", "plan's execution"]
        conflation = [p for p in plan_exec_phrases if p in lower]
        assert not conflation, (
            f"Found plan-execution language in challenge skill: {conflation} — "
            "challenge attacks direction, stress-test attacks plan execution; "
            "conflation breaks routing"
        )

    def test_skill_references_assumption_taxonomy(self, skill_content):
        # Lens 3 reads assumption-taxonomy.md — if this reference is removed,
        # Lens 3 runs without its category taxonomy and produces generic findings
        assert "assumption-taxonomy" in skill_content, (
            "Reference to stress-test/references/assumption-taxonomy.md must remain — "
            "Lens 3 reads it for hidden assumption categories"
        )

    def test_max_two_objections_per_lens_stated(self, skill_content):
        assert "at most 2 objections" in skill_content or "2 objections" in skill_content, (
            "Per-lens objection cap (≤2) must be stated — "
            "without it, lenses produce unbounded findings and overwhelm the synthesis"
        )
