"""
Tests for the Developer Growth Loop (Steps 1–6).

Covers:
1. session_end() audit line format for three new fields
2. health._parse_audit_sessions parses Retrospectives, AutonomyDepth, ContractViolation
3. _compute_decision_durability_rate returns None when < 3 data sessions; correct rate after
4. _compute_autonomy_depth_score weighting (SURFACE=0.25, WORKING=0.5, DEEP=1.0, ELITE=1.5)
5. _compute_contract_compliance_rate (fraction of sessions with zero violations)
6. org_score: DEEP autonomy + validated retrospectives + no violations > SURFACE + invalidated + violations
7. Skill rubric drift sentinels: SURFACE/WORKING/DEEP/ELITE present in nfr-check, challenge, adversary-loop
8. guardrails.py: git commit --no-verify blocked as destructive
9. guardrails.py: normal git commit not blocked
10. scripts/generate_precommit_hook.py: produces executable hook with ruff + pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers — audit block builders
# ---------------------------------------------------------------------------

def _base_block(
    *,
    skills: str = "nfr-check, dev-loop, learn",
    close: bool = True,
    retrospectives: str = "",
    autonomy_depth: str = "",
    contract_violations: list[str] | None = None,
    developer_caught: str = "",
) -> str:
    lines = [
        "### Session — 2026-01-01 10:00 UTC",
        "Project: youk",
        "Session summary",
        f"Skills: {skills}",
        f"CloseCluster: {'yes' if close else 'no'}",
        "Commits: yes",
    ]
    if developer_caught:
        lines.append(f"DeveloperCaught: {developer_caught}")
    if retrospectives:
        lines.append(retrospectives)
    if autonomy_depth:
        lines.append(f"AutonomyDepth: {autonomy_depth}")
    if contract_violations:
        for v in contract_violations:
            lines.append(f"ContractViolation: {v}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 1 + 2. Audit line parsing
# ---------------------------------------------------------------------------

class TestParseGrowthFields:

    def test_retrospectives_parsed(self):
        from health import _parse_audit_sessions
        block = _base_block(
            retrospectives="Retrospectives: 2 (VALIDATED=1, INVALIDATED=1)\n"
                           "  - Redis caching: VALIDATED (cache hit 65%)\n"
                           "  - skip retry: INVALIDATED (write failures)"
        )
        sessions = _parse_audit_sessions([block])
        assert len(sessions) == 1
        s = sessions[0]
        assert s["retrospectives_total"] == 2
        assert s["retrospectives_validated"] == 1
        assert s["retrospectives_invalidated"] == 1

    def test_retrospectives_absent_gives_zero(self):
        from health import _parse_audit_sessions
        block = _base_block()
        sessions = _parse_audit_sessions([block])
        s = sessions[0]
        assert s.get("retrospectives_total", 0) == 0
        assert s.get("retrospectives_validated", 0) == 0

    def test_autonomy_depth_parsed_single(self):
        from health import _parse_audit_sessions
        block = _base_block(autonomy_depth="nfr_check=DEEP")
        sessions = _parse_audit_sessions([block])
        s = sessions[0]
        assert s.get("autonomy_depth", {}).get("nfr_check") == "DEEP"

    def test_autonomy_depth_parsed_multiple(self):
        from health import _parse_audit_sessions
        block = _base_block(autonomy_depth="nfr_check=ELITE,challenge=WORKING")
        sessions = _parse_audit_sessions([block])
        s = sessions[0]
        depth = s.get("autonomy_depth", {})
        assert depth.get("nfr_check") == "ELITE"
        assert depth.get("challenge") == "WORKING"

    def test_contract_violations_parsed(self):
        from health import _parse_audit_sessions
        block = _base_block(contract_violations=[
            "always run ruff check — skipped before commit at 14:30",
            "always run pytest — skipped",
        ])
        sessions = _parse_audit_sessions([block])
        s = sessions[0]
        violations = s.get("contract_violations", [])
        assert len(violations) == 2
        assert any("ruff" in v for v in violations)

    def test_contract_violations_absent_gives_empty(self):
        from health import _parse_audit_sessions
        block = _base_block()
        sessions = _parse_audit_sessions([block])
        s = sessions[0]
        assert s.get("contract_violations", []) == []


# ---------------------------------------------------------------------------
# 3. Decision durability rate
# ---------------------------------------------------------------------------

class TestDecisionDurabilityRate:

    def test_returns_none_when_fewer_than_3_data_sessions(self):
        from health import _compute_decision_durability_rate
        # 2 sessions with retrospective data
        sessions = [
            {"retrospectives_total": 1, "retrospectives_validated": 1},
            {"retrospectives_total": 1, "retrospectives_validated": 0},
        ]
        assert _compute_decision_durability_rate(sessions) is None

    def test_returns_none_when_no_sessions_have_data(self):
        from health import _compute_decision_durability_rate
        sessions = [{"retrospectives_total": 0}] * 5
        assert _compute_decision_durability_rate(sessions) is None

    def test_all_validated(self):
        from health import _compute_decision_durability_rate
        sessions = [
            {"retrospectives_total": 2, "retrospectives_validated": 2},
            {"retrospectives_total": 1, "retrospectives_validated": 1},
            {"retrospectives_total": 3, "retrospectives_validated": 3},
        ]
        rate = _compute_decision_durability_rate(sessions)
        assert rate == pytest.approx(1.0)

    def test_half_validated(self):
        from health import _compute_decision_durability_rate
        sessions = [
            {"retrospectives_total": 2, "retrospectives_validated": 1},
            {"retrospectives_total": 2, "retrospectives_validated": 1},
            {"retrospectives_total": 2, "retrospectives_validated": 1},
        ]
        rate = _compute_decision_durability_rate(sessions)
        assert rate == pytest.approx(0.5)

    def test_sessions_without_data_excluded_from_denominator(self):
        from health import _compute_decision_durability_rate
        # 3 sessions with data (validated=2/3), plus 2 empty sessions
        sessions = [
            {"retrospectives_total": 1, "retrospectives_validated": 1},
            {"retrospectives_total": 1, "retrospectives_validated": 1},
            {"retrospectives_total": 1, "retrospectives_validated": 0},
            {"retrospectives_total": 0},
            {},
        ]
        rate = _compute_decision_durability_rate(sessions)
        # round(2/3, 2) == 0.67
        assert rate == pytest.approx(2 / 3, abs=0.01)


# ---------------------------------------------------------------------------
# 4. Autonomy depth score
# ---------------------------------------------------------------------------

class TestAutonomyDepthScore:

    def test_no_depth_data_returns_zero(self):
        from health import _compute_autonomy_depth_score
        sessions = [{}] * 5
        assert _compute_autonomy_depth_score(sessions) == pytest.approx(0.0)

    def test_surface_level_below_working(self):
        from health import _compute_autonomy_depth_score
        # developer_caught must be set for the session to contribute weight
        surface_sessions = [
            {"developer_caught": ["nfr_check"], "autonomy_depth": {"nfr_check": "SURFACE"}}
        ] * 6
        working_sessions = [
            {"developer_caught": ["nfr_check"], "autonomy_depth": {"nfr_check": "WORKING"}}
        ] * 6
        assert _compute_autonomy_depth_score(surface_sessions) < _compute_autonomy_depth_score(working_sessions)

    def test_deep_equals_full_weight(self):
        from health import _compute_autonomy_depth_score
        # DEEP weight=1.0, ceiling=1.5 (ELITE) → normalized score = 1.0/1.5 ≈ 0.667
        sessions = [
            {"developer_caught": ["nfr_check"], "autonomy_depth": {"nfr_check": "DEEP"}}
        ] * 6
        score = _compute_autonomy_depth_score(sessions)
        assert score == pytest.approx(1.0 / 1.5, rel=1e-3)

    def test_elite_gives_bonus_above_deep(self):
        from health import _compute_autonomy_depth_score
        deep_sessions = [
            {"developer_caught": ["nfr_check"], "autonomy_depth": {"nfr_check": "DEEP"}}
        ] * 6
        elite_sessions = [
            {"developer_caught": ["nfr_check"], "autonomy_depth": {"nfr_check": "ELITE"}}
        ] * 6
        assert _compute_autonomy_depth_score(elite_sessions) > _compute_autonomy_depth_score(deep_sessions)

    def test_elite_score_bounded_at_one(self):
        from health import _compute_autonomy_depth_score
        sessions = [
            {"developer_caught": ["nfr_check", "challenge"], "autonomy_depth": {"nfr_check": "ELITE", "challenge": "ELITE"}}
        ] * 10
        score = _compute_autonomy_depth_score(sessions)
        assert score <= 1.0

    def test_backward_compat_developer_caught_without_depth(self):
        """Sessions with developer_caught but no autonomy_depth get WORKING weight."""
        from health import _compute_autonomy_depth_score
        sessions = [{"developer_caught": "nfr_check", "autonomy_depth": {}}] * 5
        working_sessions = [{"autonomy_depth": {"nfr_check": "WORKING"}}] * 5
        assert _compute_autonomy_depth_score(sessions) == pytest.approx(
            _compute_autonomy_depth_score(working_sessions), rel=0.05
        )


# ---------------------------------------------------------------------------
# 5. Contract compliance rate
# ---------------------------------------------------------------------------

class TestContractComplianceRate:

    def test_no_data_returns_one(self):
        from health import _compute_contract_compliance_rate
        sessions = [{}] * 5
        assert _compute_contract_compliance_rate(sessions) == pytest.approx(1.0)

    def test_all_clean_returns_one(self):
        from health import _compute_contract_compliance_rate
        sessions = [{"contract_violations": []}] * 10
        assert _compute_contract_compliance_rate(sessions) == pytest.approx(1.0)

    def test_all_violated_returns_zero(self):
        from health import _compute_contract_compliance_rate
        sessions = [{"contract_violations": ["ruff skipped"]}] * 10
        assert _compute_contract_compliance_rate(sessions) == pytest.approx(0.0)

    def test_half_violated_returns_half(self):
        from health import _compute_contract_compliance_rate
        sessions = (
            [{"contract_violations": []}] * 5
            + [{"contract_violations": ["ruff skipped"]}] * 5
        )
        assert _compute_contract_compliance_rate(sessions) == pytest.approx(0.5)

    def test_looks_at_last_20_sessions_only(self):
        from health import _compute_contract_compliance_rate
        # 25 sessions: first 5 violated, last 20 all clean
        old_violations = [{"contract_violations": ["skip"]}] * 5
        recent_clean = [{"contract_violations": []}] * 20
        sessions = old_violations + recent_clean
        assert _compute_contract_compliance_rate(sessions) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 6. org_score ordering: better growth signals → higher score
# ---------------------------------------------------------------------------

class TestOrgScoreGrowthSignals:

    def _make_sessions(self, n: int, **kwargs) -> list[str]:
        return [_base_block(**kwargs)] * n

    def test_deep_autonomy_scores_higher_than_surface(self, claude_root):
        from health import _score_org
        deep_audit = "\n".join(self._make_sessions(
            8, autonomy_depth="nfr_check=DEEP", developer_caught="nfr_check"
        ))
        surface_audit = "\n".join(self._make_sessions(
            8, autonomy_depth="nfr_check=SURFACE", developer_caught="nfr_check"
        ))
        (claude_root / "audit" / "2026-01.md").write_text(deep_audit)
        deep_score = _score_org([deep_audit])
        (claude_root / "audit" / "2026-01.md").write_text(surface_audit)
        surface_score = _score_org([surface_audit])
        assert deep_score > surface_score

    def test_no_violations_scores_higher_than_with_violations(self, claude_root):
        from health import _score_org
        clean_audit = "\n".join(self._make_sessions(6))
        violated_audit = "\n".join(self._make_sessions(
            6, contract_violations=["ruff skipped"]
        ))
        clean_score = _score_org([clean_audit])
        violated_score = _score_org([violated_audit])
        assert clean_score > violated_score


# ---------------------------------------------------------------------------
# 7. Skill rubric drift sentinels
# ---------------------------------------------------------------------------

YOUK_ROOT = Path(__file__).parent.parent

_DEPTH_LEVELS = ["SURFACE", "WORKING", "DEEP", "ELITE"]


class TestSkillRubricDriftSentinels:

    def _check_skill_has_rubric(self, skill_name: str) -> None:
        skill_path = YOUK_ROOT / "skills" / skill_name / "SKILL.md"
        assert skill_path.exists(), f"{skill_name}/SKILL.md not found at {skill_path}"
        content = skill_path.read_text()
        for level in _DEPTH_LEVELS:
            assert level in content, (
                f"Autonomy depth level '{level}' missing from {skill_name}/SKILL.md. "
                "Rubric may have been removed or renamed."
            )
        assert "Autonomy Depth Rubric" in content, (
            f"'Autonomy Depth Rubric' section header missing from {skill_name}/SKILL.md"
        )

    def test_nfr_check_has_depth_rubric(self):
        self._check_skill_has_rubric("nfr-check")

    def test_challenge_has_depth_rubric(self):
        self._check_skill_has_rubric("challenge")

    def test_adversary_loop_has_depth_rubric(self):
        self._check_skill_has_rubric("adversary-loop")


# ---------------------------------------------------------------------------
# 8 + 9. Guardrails: --no-verify blocked, normal commit not blocked
# ---------------------------------------------------------------------------

class TestNoVerifyGuardrail:

    def test_blocks_commit_no_verify(self):
        from guardrails import HardRuleViolation, check_destructive_command
        with pytest.raises(HardRuleViolation, match="no-destructive-without-confirm"):
            check_destructive_command("git commit --no-verify -m 'skip hooks'")

    def test_blocks_commit_no_verify_short_flag(self):
        from guardrails import HardRuleViolation, check_destructive_command
        with pytest.raises(HardRuleViolation):
            check_destructive_command("git commit -m 'msg' --no-verify")

    def test_normal_commit_not_blocked(self):
        from guardrails import check_destructive_command
        # Should not raise — normal commit is not destructive
        check_destructive_command("git commit -m 'feat: add thing'")

    def test_commit_with_message_not_blocked(self):
        from guardrails import check_destructive_command
        check_destructive_command('git commit -m "fix: lint errors"')

    def test_existing_patterns_still_blocked(self):
        """Regression: adding --no-verify pattern must not break existing patterns."""
        from guardrails import HardRuleViolation, check_destructive_command
        with pytest.raises(HardRuleViolation):
            check_destructive_command("git reset --hard HEAD")
        with pytest.raises(HardRuleViolation):
            check_destructive_command("rm -rf node_modules")


# ---------------------------------------------------------------------------
# 10. generate_precommit_hook.py
# ---------------------------------------------------------------------------

class TestGeneratePrecommitHook:

    def test_hook_contains_ruff(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        hook = generate_hook(tmp_path / "nonexistent_contracts.md")
        assert "ruff check servers/" in hook

    def test_hook_contains_pytest(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        hook = generate_hook(tmp_path / "nonexistent_contracts.md")
        assert "pytest" in hook

    def test_hook_has_bash_shebang(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        hook = generate_hook(tmp_path / "nonexistent_contracts.md")
        assert hook.startswith("#!/bin/bash")

    def test_hook_has_blocked_message(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        hook = generate_hook(tmp_path / "nonexistent_contracts.md")
        assert "youk BLOCKED" in hook

    def test_extracts_action_contract_from_contracts_md(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        contracts = tmp_path / "contracts.md"
        contracts.write_text("- always run mycheck --strict before committing\n")
        hook = generate_hook(contracts)
        assert "mycheck --strict" in hook

    def test_no_duplicate_commands_from_contracts(self, tmp_path):
        sys.path.insert(0, str(YOUK_ROOT / "scripts"))
        from generate_precommit_hook import generate_hook
        contracts = tmp_path / "contracts.md"
        contracts.write_text(
            "- always run ruff check servers/ before committing\n"
            "- always run ruff check servers/ before commit\n"
        )
        hook = generate_hook(contracts)
        # Deduplication: ruff appears once in the command + once in the error message
        # (and once more in the command block itself). Count the || { exit 1 } blocks.
        assert hook.count("youk BLOCKED") == 1
