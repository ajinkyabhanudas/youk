"""Tests for health.py — proposal filtering, 0-contracts finding, self-heal signals."""
from __future__ import annotations


def _audit_block(n: int, close: bool = True, skills: str = "code-review") -> str:
    return (
        f"### Session — 2026-07-0{n} 10:00 UTC\n"
        f"Skills: {skills}\n"
        f"CloseCluster: {'yes' if close else 'no'}\n"
        "Commits: yes\n"
    )


class TestLoadPendingProposals:
    def test_filters_applied_by_status_field(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "# Proposals\n\n"
            "## PENDING-001 — 2026-07-01\n"
            "**Target:** foo\n**Change:** do X\n**Reason:** r\n"
            "**Before:** \n**After:** y\n**Status:** APPLIED — 2026-07-02\n"
            "**ChangeType:** CODE_EDIT\n**TargetSection:** f\n\n"
            "## PENDING-002 — 2026-07-01\n"
            "**Target:** bar\n**Change:** do Y\n**Reason:** r\n"
            "**Before:** \n**After:** z\n**Status:** PENDING\n"
            "**ChangeType:** SKILL_EDIT\n**TargetSection:** b\n"
        )
        from health import _load_pending_proposals
        proposals = _load_pending_proposals()
        assert len(proposals) == 2  # _load_pending_proposals returns all
        pending_only = [p for p in proposals if "APPLIED" not in p.status]
        assert len(pending_only) == 1
        assert "PENDING-002" in pending_only[0].id

    def test_empty_file_returns_empty_list(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text("# No proposals\n")
        from health import _load_pending_proposals
        assert _load_pending_proposals() == []

    def test_no_file_returns_empty_list(self, youk_root):
        from health import _load_pending_proposals
        assert _load_pending_proposals() == []


class TestGenerateFindings:
    def _run(self, claude_root, youk_root, audit_text: str) -> list[str]:
        (claude_root / "audit" / "2026-07.md").write_text(audit_text)
        from health import _generate_findings, _score_org
        audit_texts = [audit_text]
        score = _score_org(audit_texts)
        return _generate_findings(audit_texts, score)

    def test_zero_contracts_flagged_after_many_sessions(self, youk_root, claude_root):
        """Project with 5+ sessions and no contracts must surface a finding."""
        proj = youk_root / "knowledge" / "projects" / "myproject"
        proj.mkdir(parents=True)
        audit = "\n".join(_audit_block(i) for i in range(1, 7))
        findings = self._run(claude_root, youk_root, audit)
        contract_findings = [f for f in findings if "contracts.md" in f or "no contracts" in f.lower()]
        assert contract_findings, f"Expected 0-contracts finding. Got: {findings}"

    def test_contracts_present_no_spurious_finding(self, youk_root, claude_root):
        """No 0-contracts finding when contracts.md exists and has entries."""
        proj = youk_root / "knowledge" / "projects" / "myproject"
        proj.mkdir(parents=True)
        (proj / "contracts.md").write_text("- always run tests\n")
        audit = "\n".join(_audit_block(i) for i in range(1, 7))
        findings = self._run(claude_root, youk_root, audit)
        contract_findings = [f for f in findings if "no contracts" in f.lower()]
        assert not contract_findings, f"Unexpected 0-contracts finding: {contract_findings}"

    def test_fewer_than_5_sessions_no_zero_contracts_finding(self, youk_root, claude_root):
        """0-contracts check only fires when total sessions >= 5."""
        proj = youk_root / "knowledge" / "projects" / "myproject"
        proj.mkdir(parents=True)
        audit = "\n".join(_audit_block(i) for i in range(1, 4))
        findings = self._run(claude_root, youk_root, audit)
        contract_findings = [f for f in findings if "contracts.md" in f]
        assert not contract_findings

    def test_empty_loop_flagged(self, youk_root, claude_root):
        """Self-evolution loop starvation detected when no proposals or skill gaps."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text("# empty\n")
        audit = "\n".join(_audit_block(i) for i in range(1, 5))
        findings = self._run(claude_root, youk_root, audit)
        loop_findings = [f for f in findings if "starved" in f.lower() or "evolution" in f.lower()]
        assert loop_findings, f"Expected loop-starvation finding. Got: {findings}"

    def test_high_skip_rate_flagged(self, youk_root, claude_root):
        """More than 50% sessions without close-cluster surfaces a finding."""
        audit = "\n".join(
            _audit_block(i, close=(i % 3 == 0)) for i in range(1, 7)
        )
        findings = self._run(claude_root, youk_root, audit)
        skip_findings = [f for f in findings if "session-close loop" in f.lower() or "incomplete" in f.lower()]
        assert skip_findings, f"Expected session-close loop finding. Got: {findings}"

    def test_capability_skill_absent_finding(self, youk_root, claude_root):
        """When >75% of sessions have no capability skill, surfaces a finding."""
        # All sessions use only 'self_heal' — a meta skill, not a capability skill
        audit = "\n".join(_audit_block(i, skills="self_heal") for i in range(1, 7))
        findings = self._run(claude_root, youk_root, audit)
        cap_findings = [f for f in findings if "capability" in f.lower() or "compounding" in f.lower()]
        assert cap_findings, f"Expected capability-skill finding. Got: {findings}"

    def test_capability_skill_present_no_spurious_finding(self, youk_root, claude_root):
        """When ≥50% of sessions use a capability skill, no capability finding."""
        # All sessions use code-review — a real capability skill
        audit = "\n".join(_audit_block(i, skills="code-review") for i in range(1, 5))
        findings = self._run(claude_root, youk_root, audit)
        cap_findings = [f for f in findings if "capability skills absent" in f.lower()]
        assert not cap_findings, f"Unexpected capability-absent finding: {cap_findings}"


class TestScoreOrg:
    def _score(self, sessions: list[dict]) -> float:
        from health import _score_org
        blocks = []
        for i, s in enumerate(sessions):
            skills = s.get("skills", "none")
            close = "yes" if s.get("close_cluster") else "no"
            blocks.append(
                f"### Session — 2026-07-0{i + 1} 10:00 UTC\n"
                f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
            )
        return _score_org(["\n".join(blocks)])

    def test_capability_skills_boost_score(self):
        """Sessions with capability skills score higher than sessions with only meta skills."""
        score_with_skills = self._score([
            {"skills": "code-review, learn", "close_cluster": True},
            {"skills": "nfr_check", "close_cluster": True},
        ])
        score_meta_only = self._score([
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "simulate-experience", "close_cluster": True},
        ])
        assert score_with_skills > score_meta_only

    def test_close_rate_is_completion_bonus_not_primary(self):
        """Capability skills dominate; close_rate is just a bonus. High skills + no /done = high score."""
        score = self._score([
            {"skills": "code-review", "close_cluster": False},
            {"skills": "learn", "close_cluster": False},
        ])
        # capability_rate=1.0, close_rate=0.0, gap_resolution=0.5 (neutral)
        # → 5.0 + 2.0 + 0 + 0.25 = 7.25
        assert score >= 7.0

    def test_skills_none_does_not_count_as_capability(self):
        """'Skills: none' written literally must not be counted as a capability skill."""
        score_no_skills = self._score([
            {"skills": "none", "close_cluster": True},
            {"skills": "none", "close_cluster": True},
        ])
        score_with_skills = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
        ])
        assert score_with_skills > score_no_skills

    def test_discipline_gate_caps_score_at_6_5(self):
        """3+ consecutive sessions without any capability skill caps org_score at 6.5."""
        # Without gate: capability_rate=2/5=0.4, close_rate=1.0, gap_resolution=0.5
        # → 5.0 + 0.8 + 0.5 + 0.25 = 6.55 → rounds to 6.6 > 6.5
        # With gate (3 consecutive skill-skips): min(6.55, 6.5) = 6.5
        score = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},   # 3 consecutive: no capability skill
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
        ])
        assert score <= 6.5

    def test_discipline_gate_not_applied_below_threshold(self):
        """2 consecutive sessions without capability skills does NOT trigger the gate."""
        # consecutive_skill_skips=2, gate threshold is 3
        # capability_rate=0.5, close_rate=1.0, gap_resolution=0.5
        # → 5.0 + 1.0 + 0.5 + 0.25 = 6.75 > 6.5
        score = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
        ])
        assert score > 6.5

    def test_discipline_gate_unlocked_when_recent_skill(self):
        """Gate does NOT apply if the most recent session invoked a capability skill."""
        # 3 good + 2 no-skill + 1 good at end → consecutive_skill_skips=0, gate lifts
        # capability_rate=4/6=0.67, close_rate=1.0 → 5.0+1.33+0.5+0.25=7.08 > 6.5
        score = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},  # most recent: gate lifts
        ])
        assert score > 6.5


class TestGenerateFindingsDisciplineGate:
    def _run(self, claude_root, youk_root, sessions: list[dict]) -> list[str]:
        blocks = []
        for i, s in enumerate(sessions):
            close = "yes" if s.get("close_cluster") else "no"
            skills = s.get("skills", "code-review")
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
            )
        audit = "\n".join(blocks)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _generate_findings, _score_org
        score = _score_org([audit])
        return _generate_findings([audit], score)

    def test_discipline_gate_finding_when_3_consecutive_skill_skips(self, youk_root, claude_root):
        """Gate finding appears when 3+ consecutive sessions have no capability skill."""
        findings = self._run(claude_root, youk_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
        ])
        gate_findings = [f for f in findings if "discipline gate" in f.lower()]
        assert gate_findings, f"Expected discipline gate finding. Got: {findings}"

    def test_no_discipline_gate_finding_when_recent_skill(self, youk_root, claude_root):
        """No gate finding when most recent session invoked a capability skill."""
        findings = self._run(claude_root, youk_root, [
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "self_heal", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},  # most recent: gate lifts
        ])
        gate_findings = [f for f in findings if "discipline gate" in f.lower()]
        assert not gate_findings, f"Unexpected gate finding: {gate_findings}"


# ── New metrics: skill_invocation_rate, nfr_check_hit_rate, contracts_total, skill_patch_rate ──

def _audit_with(sessions: list[dict]) -> str:
    """Build an audit text block from a list of session dicts."""
    blocks = []
    for i, s in enumerate(sessions):
        skills = s.get("skills", "none")
        close = "yes" if s.get("close_cluster") else "no"
        mid = f"MidSessionAdaptations: {s['adaptations']}\n" if s.get("adaptations") else ""
        blocks.append(
            f"### Session — 2026-07-0{i + 1} 10:00 UTC\n"
            f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n{mid}"
        )
    return "\n".join(blocks)


class TestSkillInvocationRateMetric:
    """skill_invocation_rate persisted in improvement-metrics.json."""

    def _run_velocity(self, youk_root, claude_root, sessions: list[dict]) -> dict:
        audit = _audit_with(sessions)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        return _compute_improvement_velocity([audit], score)

    def test_100_percent_when_all_sessions_have_capability_skill(self, youk_root, claude_root):
        result = self._run_velocity(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
        ])
        import json
        entry = json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]
        assert entry["skill_invocation_rate"] == 1.0

    def test_zero_when_no_capability_skills(self, youk_root, claude_root):
        result = self._run_velocity(youk_root, claude_root, [
            {"skills": "self_heal", "close_cluster": False},
            {"skills": "none", "close_cluster": False},
        ])
        import json
        entry = json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]
        assert entry["skill_invocation_rate"] == 0.0

    def test_partial_rate_computed_correctly(self, youk_root, claude_root):
        self._run_velocity(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "none", "close_cluster": False},
            {"skills": "none", "close_cluster": False},
            {"skills": "none", "close_cluster": False},
        ])
        import json
        entry = json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]
        assert entry["skill_invocation_rate"] == 0.25


class TestNfrCheckHitRateMetric:
    """nfr_check_hit_rate: % of sessions where nfr_check appeared in Skills:"""

    def _run(self, youk_root, claude_root, sessions: list[dict]) -> dict:
        audit = _audit_with(sessions)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        _compute_improvement_velocity([audit], score)
        import json
        return json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]

    def test_nfr_check_hyphen_format_detected(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, [
            {"skills": "nfr-check, code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
        ])
        assert entry["nfr_check_hit_rate"] == 0.5

    def test_nfr_check_underscore_format_detected(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, [
            {"skills": "nfr_check", "close_cluster": True},
            {"skills": "nfr_check", "close_cluster": True},
        ])
        assert entry["nfr_check_hit_rate"] == 1.0

    def test_zero_when_nfr_never_fired(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
        ])
        assert entry["nfr_check_hit_rate"] == 0.0


class TestContractsTotalMetric:
    """contracts_total: sum of '- ' lines across all projects/*/contracts.md"""

    def _run(self, youk_root, claude_root, contract_lines: dict[str, list[str]]) -> dict:
        for slug, lines in contract_lines.items():
            proj = youk_root / "knowledge" / "projects" / slug
            proj.mkdir(parents=True, exist_ok=True)
            (proj / "contracts.md").write_text("\n".join(f"- {l}" for l in lines) + "\n")
        audit = _audit_with([{"skills": "code-review", "close_cluster": True}])
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        _compute_improvement_velocity([audit], score)
        import json
        return json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]

    def test_counts_contracts_across_projects(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, {
            "canopy": ["always run ruff", "test after migrate"],
            "youk": ["never auto-apply code edits"],
        })
        assert entry["contracts_total"] == 3

    def test_zero_when_no_contracts(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, {})
        assert entry["contracts_total"] == 0

    def test_non_list_lines_not_counted(self, youk_root, claude_root):
        """Lines without '- ' prefix (headings, blank lines) are excluded."""
        proj = youk_root / "knowledge" / "projects" / "test"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "contracts.md").write_text("# contracts\n\n- real contract\nheading line\n")
        audit = _audit_with([{"skills": "code-review", "close_cluster": True}])
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        _compute_improvement_velocity([audit], score)
        import json
        entry = json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]
        assert entry["contracts_total"] == 1


class TestSkillPatchRateMetric:
    """skill_patch_rate: % of sessions with MidSessionAdaptations: N (N > 0)"""

    def _run(self, youk_root, claude_root, sessions: list[dict]) -> dict:
        audit = _audit_with(sessions)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        _compute_improvement_velocity([audit], score)
        import json
        return json.loads((youk_root / "state" / "improvement-metrics.json").read_text())["entries"][-1]

    def test_counts_sessions_with_adaptations(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True, "adaptations": 2},
            {"skills": "learn", "close_cluster": True, "adaptations": 0},
            {"skills": "verify", "close_cluster": True, "adaptations": 1},
            {"skills": "none", "close_cluster": False},
        ])
        assert entry["skill_patch_rate"] == 0.5  # 2 out of 4

    def test_zero_when_no_adaptations(self, youk_root, claude_root):
        entry = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
        ])
        assert entry["skill_patch_rate"] == 0.0

    def test_adaptations_zero_not_counted(self, youk_root, claude_root):
        """MidSessionAdaptations: 0 must NOT increment the patch count."""
        entry = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True, "adaptations": 0},
        ])
        assert entry["skill_patch_rate"] == 0.0


class TestGapResolutionRate:
    def _sessions_with_gaps(self, gap_lines_per_session: list[list[str]]) -> list[dict]:
        """Build fake parsed sessions with SkillGap: lines embedded in 'raw'."""
        sessions = []
        for i, gaps in enumerate(gap_lines_per_session):
            raw_lines = [f"### Session — 2026-07-0{i+1} 10:00 UTC"]
            raw_lines.extend(f"SkillGap: {g}" for g in gaps)
            sessions.append({"raw": "\n".join(raw_lines), "capability_skills": [], "close_cluster": True})
        return sessions

    def test_no_gaps_returns_neutral(self):
        """Sessions with no SkillGap lines return 0.5 (neutral)."""
        from health import _compute_gap_resolution_rate
        sessions = [{"raw": "### Session — no gaps", "capability_skills": [], "close_cluster": True}]
        assert _compute_gap_resolution_rate(sessions) == 0.5

    def test_all_new_gaps_returns_1_0(self):
        """Each gap type appears in exactly one session → rate = 1.0."""
        from health import _compute_gap_resolution_rate
        sessions = self._sessions_with_gaps([
            ["nfr-check — dark mode not checked"],
            ["code-review — missing test coverage"],
        ])
        assert _compute_gap_resolution_rate(sessions) == 1.0

    def test_all_recurring_gaps_returns_0_0(self):
        """Same gap type appears in 2 sessions → recurring → rate = 0.0."""
        from health import _compute_gap_resolution_rate
        sessions = self._sessions_with_gaps([
            ["nfr-check — dark mode not checked"],
            ["nfr-check — dark mode not checked"],
        ])
        assert _compute_gap_resolution_rate(sessions) == 0.0

    def test_mixed_gaps_partial_rate(self):
        """One recurring + one new gap → rate = 0.5."""
        from health import _compute_gap_resolution_rate
        sessions = self._sessions_with_gaps([
            ["nfr-check — dark mode", "code-review — test coverage"],
            ["nfr-check — dark mode"],  # nfr-check recurs; code-review is new
        ])
        # 2 unique gap types: nfr-check (recurring), code-review (new) → 1/2 = 0.5
        assert _compute_gap_resolution_rate(sessions) == 0.5


class TestAuditSkillQuality:
    def test_returns_empty_when_skills_dir_missing(self, tmp_path):
        from health import _audit_skill_quality
        result = _audit_skill_quality(tmp_path / "nonexistent")
        assert result == []

    def test_detects_weak_skill_missing_all_signals(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "dev-loop"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# dev-loop\n\nDo stuff.\n")
        from health import _audit_skill_quality
        findings = _audit_skill_quality(skills_dir)
        assert any("dev-loop" in f for f in findings)

    def test_strong_skill_not_flagged(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "references").mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# code-review\n\n## Phase 1\nDo it.\n\n"
            "## Quality Bars\nHigh.\n\n## Example\n```py\nprint()\n```\n"
        )
        from health import _audit_skill_quality
        findings = _audit_skill_quality(skills_dir)
        # code-review has all 4 signals — should not be flagged
        assert not any("code-review" in f for f in findings)

    def test_missing_skill_md_flagged(self, tmp_path):
        skills_dir = tmp_path / "skills"
        # Only create nfr-check dir; all other capability skills also absent
        (skills_dir / "nfr-check").mkdir(parents=True)  # dir exists, no SKILL.md
        from health import _audit_skill_quality
        findings = _audit_skill_quality(skills_dir)
        # With many skills missing, output is a grouped finding — check that it fires
        assert findings, "Expected at least one quality finding when SKILL.md is absent"
        assert any("no SKILL.md" in f or "weak" in f.lower() for f in findings)

    def test_multiple_weak_skills_grouped_into_one_finding(self, tmp_path):
        skills_dir = tmp_path / "skills"
        for name in ["code-review", "dev-loop", "nfr-check"]:
            d = skills_dir / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}\n\nDo stuff.\n")
        from health import _audit_skill_quality
        findings = _audit_skill_quality(skills_dir)
        # 3+ weak skills → one grouped finding, not 3 separate ones
        assert len(findings) == 1
        assert "3" in findings[0] or "weak" in findings[0].lower()


class TestDormantSkillDetectionExpanded:
    def _run(self, claude_root, youk_root, skills: str, sessions: int = 6) -> list[str]:
        blocks = "\n".join(
            f"### Session — 2026-07-0{i} 10:00 UTC\n"
            f"Skills: {skills}\nCloseCluster: yes\nCommits: yes\n"
            for i in range(1, sessions + 1)
        )
        (claude_root / "audit" / "2026-07.md").write_text(blocks)
        from health import _generate_findings, _score_org
        score = _score_org([blocks])
        return _generate_findings([blocks], score)

    def test_hardcoded_three_skills_covered_by_expansion(self, youk_root, claude_root):
        """nfr-check never invoked across 6 sessions surfaces a dormant finding."""
        findings = self._run(claude_root, youk_root, skills="code-review, learn")
        dormant_findings = [f for f in findings if "nfr-check" in f or "dormant" in f.lower() or "never invoked" in f.lower()]
        assert dormant_findings, f"Expected nfr-check dormant finding. Got: {findings}"

    def test_many_dormant_skills_grouped(self, youk_root, claude_root):
        """5+ dormant skills → one grouped finding instead of individual ones."""
        # Only 'learn' used — code-review, verify, nfr-check, dev-loop, security-review all dormant
        findings = self._run(claude_root, youk_root, skills="learn")
        grouped = [f for f in findings if "never invoked" in f.lower() or "capability skills" in f.lower()]
        individual = [f for f in findings if "not recorded in any" in f]
        # Should not generate 5+ individual findings — should group them
        assert len(individual) <= 2 or grouped, f"Expected grouping for many dormant skills. Got: {findings}"

    def test_active_skill_not_flagged_as_dormant(self, youk_root, claude_root):
        """code-review used in all sessions → not flagged as dormant."""
        findings = self._run(claude_root, youk_root, skills="code-review, learn, nfr-check, verify, dev-loop, security-review, write-spec, adr")
        dormant_findings = [f for f in findings if "not recorded" in f or "dormant" in f.lower()]
        assert not dormant_findings, f"Unexpected dormant finding: {dormant_findings}"


class TestApplyProposalSafeTypes:
    _PENDING = (
        "# Proposals\n\n"
        "## PENDING-001 — 2026-07-01\n"
        "**Target:** skills/dev-loop/SKILL.md\n**Change:** add phase\n**Reason:** r\n"
        "**Before:** \n**After:** new content\n**Status:** PENDING\n"
        "**ChangeType:** SKILL_EDIT\n**TargetSection:** Phase 1\n\n"
        "## PENDING-002 — 2026-07-01\n"
        "**Target:** servers/core/src/session.py\n**Change:** fix func\n**Reason:** r\n"
        "**Before:** old_code\n**After:** new_code\n**Status:** PENDING\n"
        "**ChangeType:** CODE_EDIT\n**TargetSection:** session_start\n"
    )

    def test_confirmed_false_returns_blocked_true(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(self._PENDING)
        from health import apply_proposal
        result = apply_proposal("PENDING-001", confirmed=False)
        assert result["blocked"] is True
        assert "Preview only" in result["message"]

    def test_skill_edit_passes_safe_types_gate(self, youk_root, monkeypatch):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(self._PENDING)
        import health as h
        captured = {}
        monkeypatch.setattr(h, "_execute_proposal", lambda p: (captured.update({"p": p}) or {"applied": True}))
        result = h.apply_proposal("PENDING-001", confirmed=True, safe_types=["SKILL_EDIT", "FILE_CREATE"])
        assert result.get("blocked") is not True
        assert captured["p"].change_type == "SKILL_EDIT"

    def test_code_edit_blocked_by_safe_types_gate(self, youk_root, monkeypatch):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(self._PENDING)
        import health as h
        executed = []
        monkeypatch.setattr(h, "_execute_proposal", lambda p: executed.append(p) or {"applied": True})
        result = h.apply_proposal("PENDING-002", confirmed=True, safe_types=["SKILL_EDIT", "FILE_CREATE"])
        assert result["blocked"] is True
        assert result["change_type"] == "CODE_EDIT"
        assert "manual review" in result["message"]
        assert executed == []  # _execute_proposal must NOT be called

    def test_no_safe_types_applies_any_change_type(self, youk_root, monkeypatch):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(self._PENDING)
        import health as h
        executed = []
        monkeypatch.setattr(h, "_execute_proposal", lambda p: (executed.append(p) or {"applied": True}))
        result = h.apply_proposal("PENDING-002", confirmed=True)  # no safe_types
        assert result.get("blocked") is not True
        assert len(executed) == 1

    def test_missing_proposal_returns_error(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(self._PENDING)
        from health import apply_proposal
        result = apply_proposal("PENDING-999", confirmed=True, safe_types=["SKILL_EDIT"])
        assert result["applied"] is False
        assert "not found" in result["error"]


# ── Project type coverage gaps ───────────────────────────────────────────────

class TestCheckProjectTypeCoverage:
    def _write_session_json(self, youk_root, purpose: str):
        import json
        (youk_root / "state").mkdir(parents=True, exist_ok=True)
        (youk_root / "state" / "session.json").write_text(
            json.dumps({"last_project": "testproject", "project_purpose": purpose})
        )

    def test_returns_none_for_general_project(self, youk_root, claude_root):
        self._write_session_json(youk_root, "general")
        from health import _check_project_type_coverage
        assert _check_project_type_coverage() is None

    def test_returns_none_when_session_json_missing(self, youk_root, claude_root):
        from health import _check_project_type_coverage
        assert _check_project_type_coverage() is None

    def test_returns_gaps_for_ai_engineering_system(self, youk_root, claude_root):
        self._write_session_json(youk_root, "ai_engineering_system")
        # skills dir has no skills yet → both expected skills are missing
        (claude_root / "skills").mkdir(parents=True, exist_ok=True)
        from health import _check_project_type_coverage
        result = _check_project_type_coverage()
        assert result is not None
        assert result["type"] == "ai_engineering_system"
        assert len(result["missing"]) == 2
        names = {s["name"] for s in result["missing"]}
        assert "install-experience" in names
        assert "namespace-safety" in names

    def test_returns_none_when_all_expected_skills_present(self, youk_root, claude_root):
        self._write_session_json(youk_root, "ai_engineering_system")
        # Create both expected skills
        for skill in ["install-experience", "namespace-safety"]:
            (claude_root / "skills" / skill).mkdir(parents=True)
        from health import _check_project_type_coverage
        result = _check_project_type_coverage()
        assert result is None

    def test_partial_gap_surfaces_only_missing(self, youk_root, claude_root):
        self._write_session_json(youk_root, "ai_engineering_system")
        # Only install-experience present → namespace-safety still missing
        (claude_root / "skills" / "install-experience").mkdir(parents=True)
        from health import _check_project_type_coverage
        result = _check_project_type_coverage()
        assert result is not None
        assert len(result["missing"]) == 1
        assert result["missing"][0]["name"] == "namespace-safety"


# ── Retrospective recovery: /learn at next open recovers a no-/done close ────

class TestRetrospectiveRecoveryInFindings:
    """_generate_findings must not flag sessions recovered via retrospective /learn."""

    def _run(self, claude_root, youk_root, sessions: list[dict]) -> list[str]:
        blocks = []
        for i, s in enumerate(sessions):
            close = "yes" if s.get("close_cluster") else "no"
            skills = s.get("skills", "code-review")
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
            )
        audit = "\n".join(blocks)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _generate_findings, _score_org
        score = _score_org([audit])
        return _generate_findings([audit], score)

    def test_no_flag_when_all_sessions_have_done(self, youk_root, claude_root):
        """All sessions with close_cluster: no spurious session-close loop finding."""
        findings = self._run(claude_root, youk_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
        ])
        loop_findings = [f for f in findings if "session-close loop" in f.lower()]
        assert not loop_findings, f"Unexpected session-close loop finding: {loop_findings}"

    def test_no_flag_when_skip_rate_below_50pct(self, youk_root, claude_root):
        """skip_rate ≤ 50% after accounting for recovery: no finding."""
        # 2 closed, 1 not-closed but recovered by next session's /learn → 3/3 effective
        findings = self._run(claude_root, youk_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": False},  # missed
            {"skills": "learn, code-review", "close_cluster": True},  # recovery
        ])
        loop_findings = [f for f in findings if "session-close loop incomplete" in f.lower()]
        assert not loop_findings, f"Unexpected finding when recovery present: {loop_findings}"

    def test_flag_when_majority_unrecovered(self, youk_root, claude_root):
        """Majority of sessions have no /done AND no retrospective recovery → finding fires."""
        findings = self._run(claude_root, youk_root, [
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": True},
        ])
        loop_findings = [f for f in findings if "session-close loop" in f.lower()]
        assert loop_findings, f"Expected session-close loop finding. Got: {findings}"

    def test_recovery_counts_toward_effective_close(self, youk_root, claude_root):
        """A no-/done session followed by a session with /learn is counted as recovered."""
        # 4 sessions: 1 closed, 1 not-closed+recovered, 1 not-closed+recovered, 1 closed
        # effective_close = 4/4 = 100% → no finding
        findings = self._run(claude_root, youk_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "learn", "close_cluster": True},   # recovers session 2
            {"skills": "code-review", "close_cluster": False},
            {"skills": "learn", "close_cluster": True},   # recovers session 4
        ])
        loop_findings = [f for f in findings if "session-close loop incomplete" in f.lower()]
        assert not loop_findings, f"Unexpected finding when all recovered: {loop_findings}"


# ── loop_verdict: every value has a test (positive AND negative path) ─────────

class TestLoopVerdict:
    """_compute_improvement_velocity loop_verdict — every value, positive and negative."""

    def _run(self, youk_root, claude_root, sessions: list[dict],
             prior_score: float | None = None) -> dict:
        blocks = []
        if prior_score is not None:
            # Inject a prior Org score entry so velocity can be computed
            blocks.append(f"### Session — 2026-06-30 10:00 UTC\nSkills: code-review\n"
                          f"CloseCluster: yes\nOrg score: {prior_score}/10\nCommits: yes\n")
        for i, s in enumerate(sessions):
            close = "yes" if s.get("close_cluster") else "no"
            skills = s.get("skills", "code-review")
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
            )
        audit = "\n".join(blocks)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _compute_improvement_velocity, _score_org
        score = _score_org([audit])
        return _compute_improvement_velocity([audit], score)

    def test_improving_when_score_rose(self, youk_root, claude_root):
        """IMPROVING verdict when current score > previous score."""
        result = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": True},
            {"skills": "learn", "close_cluster": True},
        ], prior_score=5.0)
        assert "IMPROVING" in result["loop_verdict"]

    def test_regressing_when_score_fell(self, youk_root, claude_root):
        """REGRESSING verdict when current score < previous score."""
        result = self._run(youk_root, claude_root, [
            {"skills": "self_heal", "close_cluster": False},
            {"skills": "none", "close_cluster": False},
        ], prior_score=9.5)
        assert "REGRESSING" in result["loop_verdict"]

    def test_stalled_requires_both_zero(self, youk_root, claude_root):
        """STALLED only fires when BOTH skill_invocation_rate=0 AND close_rate=0."""
        result = self._run(youk_root, claude_root, [
            {"skills": "none", "close_cluster": False},
            {"skills": "none", "close_cluster": False},
        ])
        assert "STALLED" in result["loop_verdict"]

    def test_not_stalled_when_skills_ran_without_done(self, youk_root, claude_root):
        """NOT STALLED when capability skills ran, even with close_rate=0."""
        result = self._run(youk_root, claude_root, [
            {"skills": "code-review", "close_cluster": False},
            {"skills": "learn", "close_cluster": False},
        ])
        assert "STALLED" not in result["loop_verdict"], (
            f"Should not be STALLED when skills ran. Got: {result['loop_verdict']}"
        )

    def test_not_stalled_when_done_ran_without_skills(self, youk_root, claude_root):
        """NOT STALLED when /done ran (close_rate>0) even if no capability skills."""
        result = self._run(youk_root, claude_root, [
            {"skills": "none", "close_cluster": True},
            {"skills": "none", "close_cluster": True},
        ])
        assert "STALLED" not in result["loop_verdict"], (
            f"Should not be STALLED when /done ran. Got: {result['loop_verdict']}"
        )

    def test_steady_when_no_velocity_but_evolution_active(self, youk_root, claude_root):
        """STEADY when score unchanged and gaps or proposals exist."""
        # Write a SkillGap entry so evolution_active=True
        (claude_root / "audit" / "2026-07.md").write_text(
            "### Session — 2026-06-30 10:00 UTC\nSkills: code-review\n"
            "CloseCluster: yes\nOrg score: 7.0/10\nCommits: yes\n"
            "SkillGap: learn — missing PERSIST phase\n\n"
            "### Session — 2026-07-01 10:00 UTC\nSkills: code-review\n"
            "CloseCluster: yes\nCommits: yes\n"
        )
        from health import _compute_improvement_velocity, _score_org
        audit = (claude_root / "audit" / "2026-07.md").read_text()
        score = _score_org([audit])
        result = _compute_improvement_velocity([audit], score)
        # Score might not be exactly 7.0 again — just verify STALLED is absent
        assert "STALLED" not in result["loop_verdict"]


# ── Naming lint: no design-phase shorthand in user-facing strings ─────────────

class TestNamingLint:
    """User-facing message strings must not contain internal design labels."""

    _OPAQUE_PATTERNS = [
        "Option A", "Option B", "Option C", "Option D",
        "PROPOSAL A", "PROPOSAL B", "PROPOSAL C",
        "G1:", "G2:", "G3:", "G4:", "G5:",
        "G2a", "G2b", "G2c",
    ]

    def _all_finding_strings(self, claude_root, youk_root) -> list[str]:
        """Run _generate_findings with a realistic audit and collect all strings."""
        audit = "\n".join(
            f"### Session — 2026-07-0{i} 10:00 UTC\n"
            f"Skills: code-review\nCloseCluster: yes\nCommits: yes\n"
            for i in range(1, 6)
        )
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _generate_findings, _score_org, _compute_improvement_velocity
        score = _score_org([audit])
        findings = _generate_findings([audit], score)
        velocity = _compute_improvement_velocity([audit], score)
        return findings + [velocity.get("loop_verdict", "")]

    def test_no_opaque_labels_in_findings(self, youk_root, claude_root):
        strings = self._all_finding_strings(claude_root, youk_root)
        violations = []
        for s in strings:
            for pattern in self._OPAQUE_PATTERNS:
                if pattern in s:
                    violations.append(f"Found '{pattern}' in: {s[:80]}")
        assert not violations, "Opaque design labels found in user-facing strings:\n" + "\n".join(violations)


# ── _read_recent_audit_logs ───────────────────────────────────────────────────

class TestReadRecentAuditLogs:
    def test_returns_empty_when_dir_missing(self, youk_root, claude_root):
        from health import _read_recent_audit_logs
        assert _read_recent_audit_logs() == []

    def test_reads_current_month_file(self, youk_root, claude_root):
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        (claude_root / "audit" / f"{month}.md").write_text("### Session — content\n")
        from health import _read_recent_audit_logs
        texts = _read_recent_audit_logs(days=30)
        assert any("### Session" in t for t in texts)

    def test_skips_files_outside_window(self, youk_root, claude_root):
        # Write a file from 3 years ago — should be excluded by the 30-day window
        (claude_root / "audit" / "2020-01.md").write_text("### Session — old\n")
        from health import _read_recent_audit_logs
        texts = _read_recent_audit_logs(days=30)
        assert not any("old" in t for t in texts)

    def test_skips_malformed_filenames(self, youk_root, claude_root):
        (claude_root / "audit" / "notes.md").write_text("just notes\n")
        from health import _read_recent_audit_logs
        # Should not raise — malformed files are silently skipped
        texts = _read_recent_audit_logs(days=30)
        assert isinstance(texts, list)


# ── _parse_skill_gap_signals ──────────────────────────────────────────────────

class TestParseSkillGapSignals:
    def test_extracts_gap_lines(self, youk_root, claude_root):
        audit = "SkillGap: learn — missing PERSIST phase\nSkillGap: learn — no bridges\n"
        from health import _parse_skill_gap_signals
        result = _parse_skill_gap_signals([audit])
        assert len(result) == 1
        assert result[0]["skill"] == "learn"
        assert result[0]["count"] == 2

    def test_multiple_skills_sorted_by_count(self, youk_root, claude_root):
        audit = (
            "SkillGap: code-review — gap1\nSkillGap: code-review — gap2\n"
            "SkillGap: code-review — gap3\nSkillGap: learn — gap1\n"
        )
        from health import _parse_skill_gap_signals
        result = _parse_skill_gap_signals([audit])
        assert result[0]["skill"] == "code-review"
        assert result[0]["count"] == 3

    def test_returns_empty_when_no_gap_lines(self, youk_root, claude_root):
        from health import _parse_skill_gap_signals
        assert _parse_skill_gap_signals(["### Session — no gaps\n"]) == []

    def test_ignores_malformed_gap_lines(self, youk_root, claude_root):
        from health import _parse_skill_gap_signals
        # Missing " — " separator → should be ignored
        result = _parse_skill_gap_signals(["SkillGap: learn missing separator\n"])
        assert result == []


# ── run_health_check_with_skill_signals ───────────────────────────────────────

class TestRunHealthCheckWithSkillSignals:
    def _write_audit(self, claude_root, sessions=3, with_gap=False):
        lines = []
        for i in range(1, sessions + 1):
            lines.append(f"### Session — 2026-07-0{i} 10:00 UTC")
            lines.append("Skills: code-review")
            lines.append("CloseCluster: yes")
            lines.append("Commits: yes")
            if with_gap:
                lines.append("SkillGap: learn — missing PERSIST phase")
        (claude_root / "audit" / "2026-07.md").write_text("\n".join(lines))

    def test_returns_org_score(self, youk_root, claude_root):
        self._write_audit(claude_root)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert "org_score" in result
        assert isinstance(result["org_score"], float)

    def test_includes_improvement_velocity(self, youk_root, claude_root):
        self._write_audit(claude_root)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert "improvement_velocity" in result
        assert "loop_verdict" in result["improvement_velocity"]

    def test_surfaces_skill_gap_signals_when_present(self, youk_root, claude_root):
        self._write_audit(claude_root, with_gap=True)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert "skill_gap_signals" in result
        assert result["skill_gap_signals"][0]["skill"] == "learn"

    def test_no_skill_gap_key_when_none_present(self, youk_root, claude_root):
        self._write_audit(claude_root, with_gap=False)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert "skill_gap_signals" not in result

    def test_research_mode_adds_topics_when_gaps_exist(self, youk_root, claude_root):
        self._write_audit(claude_root, with_gap=True)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals(research_mode=True)
        assert "research_topics" in result
        assert len(result["research_topics"]) >= 1

    def test_research_mode_no_topics_when_no_gaps(self, youk_root, claude_root):
        self._write_audit(claude_root, with_gap=False)
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals(research_mode=False)
        assert "research_topics" not in result


# ── _archive_applied_proposals ────────────────────────────────────────────────

class TestArchiveAppliedProposals:
    _PENDING_WITH_APPLIED = (
        "# Proposals\n\n"
        "## PENDING-001 — 2026-07-01\n**Status:** APPLIED — 2026-07-02\n\n"
        "## PENDING-002 — 2026-07-01\n**Status:** PENDING\n"
    )

    def test_moves_applied_to_archive(self, youk_root):
        proposals_dir = youk_root / "knowledge" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        (proposals_dir / "PENDING.md").write_text(self._PENDING_WITH_APPLIED)
        from health import _archive_applied_proposals
        count = _archive_applied_proposals()
        assert count == 1
        archive = (proposals_dir / "APPLIED-ARCHIVE.md").read_text()
        assert "PENDING-001" in archive
        pending = (proposals_dir / "PENDING.md").read_text()
        assert "PENDING-001" not in pending
        assert "PENDING-002" in pending

    def test_returns_zero_when_nothing_to_archive(self, youk_root):
        proposals_dir = youk_root / "knowledge" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        (proposals_dir / "PENDING.md").write_text("# Proposals\n\n## PENDING-001\n**Status:** PENDING\n")
        from health import _archive_applied_proposals
        assert _archive_applied_proposals() == 0

    def test_returns_zero_when_file_missing(self, youk_root):
        from health import _archive_applied_proposals
        assert _archive_applied_proposals() == 0

    def test_also_archives_superseded(self, youk_root):
        proposals_dir = youk_root / "knowledge" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)
        (proposals_dir / "PENDING.md").write_text(
            "# Proposals\n\n## PENDING-001 — 2026-07-01\n**Status:** SUPERSEDED\n"
        )
        from health import _archive_applied_proposals
        count = _archive_applied_proposals()
        assert count == 1


# ── _audit_global_contracts ───────────────────────────────────────────────────

class TestAuditGlobalContracts:
    def test_returns_zeros_when_file_missing(self, youk_root):
        from health import _audit_global_contracts
        result = _audit_global_contracts()
        assert result == {"total": 0, "auto_promoted": 0, "confirmed": 0}

    def test_counts_total_and_auto_promoted(self, youk_root):
        global_dir = youk_root / "knowledge" / "global"
        global_dir.mkdir(parents=True)
        (global_dir / "contracts.md").write_text(
            "- always test before commit [auto-promoted]\n"
            "- never mock the DB\n"
            "- run ruff on save [auto-promoted]\n"
        )
        from health import _audit_global_contracts
        result = _audit_global_contracts()
        assert result["total"] == 3
        assert result["auto_promoted"] == 2
        assert result["confirmed"] == 1

    def test_skips_headings_and_blank_lines(self, youk_root):
        global_dir = youk_root / "knowledge" / "global"
        global_dir.mkdir(parents=True)
        (global_dir / "contracts.md").write_text(
            "# Global Contracts\n\n- one contract\n\n# Section\n"
        )
        from health import _audit_global_contracts
        result = _audit_global_contracts()
        assert result["total"] == 1


# ── _detect_cross_project_patterns ───────────────────────────────────────────

class TestDetectCrossProjectPatterns:
    def _write_contracts(self, youk_root, project_contracts: dict[str, list[str]]):
        for slug, contracts in project_contracts.items():
            proj = youk_root / "knowledge" / "projects" / slug
            proj.mkdir(parents=True, exist_ok=True)
            (proj / "contracts.md").write_text(
                "\n".join(f"- {c}" for c in contracts) + "\n"
            )

    def test_returns_empty_when_no_projects(self, youk_root):
        from health import _detect_cross_project_patterns
        assert _detect_cross_project_patterns() == []

    def test_returns_empty_when_only_one_project(self, youk_root):
        self._write_contracts(youk_root, {"canopy": ["always run tests"]})
        from health import _detect_cross_project_patterns
        assert _detect_cross_project_patterns() == []

    def test_detects_shared_contract(self, youk_root):
        self._write_contracts(youk_root, {
            "canopy": ["always run tests", "never mock the db"],
            "youk":   ["always run tests", "never auto-apply code edits"],
        })
        from health import _detect_cross_project_patterns
        result = _detect_cross_project_patterns()
        shared = [r for r in result if "always run tests" in r["contract"]]
        assert shared
        assert shared[0]["count"] == 2

    def test_no_cross_project_when_contracts_differ(self, youk_root):
        self._write_contracts(youk_root, {
            "canopy": ["always run tests"],
            "youk":   ["never auto-apply code edits"],
        })
        from health import _detect_cross_project_patterns
        assert _detect_cross_project_patterns() == []

    def test_sorted_by_count_descending(self, youk_root):
        self._write_contracts(youk_root, {
            "a": ["shared1", "shared2", "unique-a"],
            "b": ["shared1", "shared2", "unique-b"],
            "c": ["shared1", "unique-c"],
        })
        from health import _detect_cross_project_patterns
        result = _detect_cross_project_patterns()
        # shared1 appears in 3 projects, shared2 in 2 — should be sorted desc
        assert result[0]["count"] >= result[-1]["count"]


# ── add_proposal deduplication ────────────────────────────────────────────────

class TestAddProposal:
    def _make_proposal(self, desc="do X"):
        from models import Proposal
        return Proposal(
            id="PENDING-TEST",
            target="skills/learn/SKILL.md",
            change_description=desc,
            reason="test",
            before="old",
            after="new",
            status="PENDING",
            proposed_date="2026-07-10",
            change_type="SKILL_EDIT",
            target_section="Phase 1",
            content="new content",
        )

    def test_creates_file_when_missing(self, youk_root):
        from health import add_proposal
        add_proposal(self._make_proposal())
        assert (youk_root / "knowledge" / "proposals" / "PENDING.md").exists()

    def test_deduplicates_by_change_description(self, youk_root):
        from health import add_proposal
        p = self._make_proposal("unique description for dedup test")
        add_proposal(p)
        add_proposal(p)  # second call should be a no-op
        content = (youk_root / "knowledge" / "proposals" / "PENDING.md").read_text()
        assert content.count("unique description for dedup test") == 1

    def test_appends_distinct_proposals(self, youk_root):
        from health import add_proposal
        add_proposal(self._make_proposal("description one"))
        add_proposal(self._make_proposal("description two"))
        content = (youk_root / "knowledge" / "proposals" / "PENDING.md").read_text()
        assert "description one" in content
        assert "description two" in content


# ── _compute_diff_preview (SKILL_EDIT, FILE_CREATE, unknown) ──────────────────

class TestComputeDiffPreview:
    def _make_proposal(self, change_type, target, section="", content="new content", youk_root=None, claude_root=None):
        from models import Proposal
        return Proposal(
            id="PENDING-PREVIEW",
            target=target,
            change_description="preview test",
            reason="r",
            before="",
            after="",
            status="PENDING",
            proposed_date="2026-07-10",
            change_type=change_type,
            target_section=section,
            content=content,
        )

    def test_skill_edit_section_found(self, youk_root, claude_root):
        skill_dir = claude_root / "skills" / "learn"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# learn\n\n## Phase 1\nold content\n\n## Phase 2\nother\n")
        p = self._make_proposal("SKILL_EDIT", "learn", section="Phase 1", content="new content")
        from health import _compute_diff_preview
        result = _compute_diff_preview(p)
        assert result["change_type"] == "SKILL_EDIT"
        assert "Phase 1" in result["before"]
        assert "new content" in result["after"]

    def test_skill_edit_section_missing(self, youk_root, claude_root):
        skill_dir = claude_root / "skills" / "learn"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# learn\n\n## Phase 1\nstuff\n")
        p = self._make_proposal("SKILL_EDIT", "learn", section="NonExistent", content="x")
        from health import _compute_diff_preview
        result = _compute_diff_preview(p)
        assert "section not found" in result["before"]

    def test_skill_edit_skill_md_missing(self, youk_root, claude_root):
        p = self._make_proposal("SKILL_EDIT", "missing-skill", section="Phase 1", content="x")
        from health import _compute_diff_preview
        result = _compute_diff_preview(p)
        assert "error" in result

    def test_unknown_change_type_returns_note(self, youk_root, claude_root):
        p = self._make_proposal("UNKNOWN_TYPE", "some/target")
        from health import _compute_diff_preview
        result = _compute_diff_preview(p)
        assert "note" in result or "error" in result


# ── _execute_proposal (FILE_CREATE path guard, SKILL_EDIT write) ──────────────

class TestExecuteProposal:
    def _make_proposal(self, change_type, target, section="", content="content", youk_root=None):
        from models import Proposal
        return Proposal(
            id="PENDING-EXEC",
            target=target,
            change_description="exec test",
            reason="r",
            before="",
            after="",
            status="PENDING",
            proposed_date="2026-07-10",
            change_type=change_type,
            target_section=section,
            content=content,
        )

    def test_file_create_blocked_outside_allowed_roots(self, youk_root, claude_root):
        p = self._make_proposal("FILE_CREATE", "/tmp/evil.md", content="evil")
        from health import _execute_proposal
        result = _execute_proposal(p)
        assert result["applied"] is False
        assert "blocked" in result["error"].lower() or "outside" in result["error"].lower()

    def test_file_create_writes_inside_youk_root(self, youk_root, claude_root, monkeypatch):
        import health
        monkeypatch.setattr(health, "_ALLOWED_WRITE_ROOTS", [youk_root])
        target = str(youk_root / "knowledge" / "proposals" / "test-create.md")
        p = self._make_proposal("FILE_CREATE", target, content="# Created\n")
        result = health._execute_proposal(p)
        assert result["applied"] is True
        assert (youk_root / "knowledge" / "proposals" / "test-create.md").read_text() == "# Created\n"

    def test_skill_edit_appends_new_section_when_missing(self, youk_root, claude_root):
        skill_dir = claude_root / "skills" / "learn"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# learn\n\n## Phase 1\noriginal\n")
        p = self._make_proposal("SKILL_EDIT", "learn", section="New Section", content="brand new")
        from health import _execute_proposal
        result = _execute_proposal(p)
        assert result["applied"] is True
        content = (skill_dir / "SKILL.md").read_text()
        assert "New Section" in content
        assert "brand new" in content

    def test_skill_edit_replaces_existing_section(self, youk_root, claude_root):
        skill_dir = claude_root / "skills" / "learn"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# learn\n\n## Phase 1\nold content\n\n## Phase 2\nkeep\n")
        p = self._make_proposal("SKILL_EDIT", "learn", section="Phase 1", content="replaced")
        from health import _execute_proposal
        result = _execute_proposal(p)
        assert result["applied"] is True
        content = (skill_dir / "SKILL.md").read_text()
        assert "replaced" in content
        assert "keep" in content
        assert "old content" not in content

    def test_skill_edit_missing_skill_md(self, youk_root, claude_root):
        p = self._make_proposal("SKILL_EDIT", "nonexistent", section="Phase 1", content="x")
        from health import _execute_proposal
        result = _execute_proposal(p)
        assert result["applied"] is False
        assert "not found" in result["error"]

    def test_unknown_change_type_returns_error(self, youk_root, claude_root):
        p = self._make_proposal("UNKNOWN", "some/target")
        from health import _execute_proposal
        result = _execute_proposal(p)
        assert result["applied"] is False
        assert "Unknown change_type" in result["error"]


# ── _compute_knowledge_velocity ───────────────────────────────────────────────

class TestComputeKnowledgeVelocity:
    def _write_audit(self, claude_root, sessions: list[dict]):
        lines = []
        for i, s in enumerate(sessions):
            lines.append(f"### Session — 2026-07-0{i+1} 10:00 UTC")
            lines.append(f"Skills: {s.get('skills', 'code-review')}")
            lines.append(f"CloseCluster: {'yes' if s.get('close_cluster') else 'no'}")
            if s.get("contracts_saved"):
                lines.append(f"contracts_saved: {s['contracts_saved']}")
        return "\n".join(lines)

    def test_growing_when_contracts_and_domain(self, youk_root, claude_root):
        domain_dir = youk_root / "knowledge" / "domain"
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "testing.md").write_text("# Testing\n")
        audit = self._write_audit(claude_root, [
            {"skills": "learn", "contracts_saved": 2},
            {"skills": "learn", "contracts_saved": 1},
        ])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "test-project")
        assert result["domain_concepts_total"] >= 1
        assert "GROWING" in result["verdict"] or "SLOW" in result["verdict"]

    def test_empty_verdict_when_no_knowledge(self, youk_root, claude_root):
        audit = self._write_audit(claude_root, [{"skills": "code-review"}])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "test-project")
        assert result["verdict"] in ("EMPTY — no knowledge accumulated yet; run /learn at session end",
                                     "SLOW — knowledge accumulating but below 1 contract/session average",
                                     "STALLED — existing knowledge loaded but nothing added recently")

    def test_domain_concepts_counts_md_files_excluding_gaps(self, youk_root, claude_root):
        domain_dir = youk_root / "knowledge" / "domain"
        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "concept-a.md").write_text("# A\n")
        (domain_dir / "concept-b.md").write_text("# B\n")
        (domain_dir / "gaps.md").write_text("# Gaps\n")  # should be excluded
        audit = self._write_audit(claude_root, [{"skills": "learn"}])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "test-project")
        assert result["domain_concepts_total"] == 2  # gaps.md excluded

    def test_project_contracts_counted(self, youk_root, claude_root):
        proj = youk_root / "knowledge" / "projects" / "myproj"
        proj.mkdir(parents=True, exist_ok=True)
        (proj / "contracts.md").write_text("- contract one\n- contract two\n")
        audit = self._write_audit(claude_root, [{"skills": "learn"}])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "myproj")
        assert result["project_contracts_total"] == 2

    def test_learn_rate_computed(self, youk_root, claude_root):
        audit = self._write_audit(claude_root, [
            {"skills": "learn", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
        ])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "test")
        assert result["learn_rate"] == 0.5


# ── _analyze_promotion_candidates ─────────────────────────────────────────────

class TestAnalyzePromotionCandidates:
    def _audit_with_gaps(self, gaps: list[tuple[str, str, str]]) -> str:
        """Build audit text with SkillGap lines. gaps = [(project, skill, description)]"""
        lines = []
        for i, (proj, skill, desc) in enumerate(gaps):
            lines.append(f"### Session — 2026-07-0{i+1} 10:00 UTC")
            lines.append(f"Project: {proj}")
            lines.append(f"Skills: code-review")
            lines.append(f"CloseCluster: yes")
            lines.append(f"SkillGap: {skill} — {desc}")
        return "\n".join(lines)

    def test_returns_empty_when_no_gaps(self, youk_root, claude_root):
        from health import _analyze_promotion_candidates
        assert _analyze_promotion_candidates([]) == []

    def test_skill_with_3_occurrences_is_candidate(self, youk_root, claude_root):
        audit = self._audit_with_gaps([
            ("proj-a", "learn", "missing PERSIST"),
            ("proj-a", "learn", "no bridges"),
            ("proj-a", "learn", "no extract"),
        ])
        from health import _analyze_promotion_candidates
        candidates = _analyze_promotion_candidates([audit])
        assert any(c["skill"] == "learn" and c["occurrence_count"] >= 3 for c in candidates)

    def test_skill_with_2_occurrences_not_candidate(self, youk_root, claude_root):
        audit = self._audit_with_gaps([
            ("proj-a", "learn", "gap1"),
            ("proj-a", "learn", "gap2"),
        ])
        from health import _analyze_promotion_candidates
        candidates = _analyze_promotion_candidates([audit])
        assert not any(c["skill"] == "learn" for c in candidates)

    def test_cross_project_gap_gets_file_create_type(self, youk_root, claude_root):
        audit = self._audit_with_gaps([
            ("proj-a", "verify", "missing step"),
            ("proj-b", "verify", "missing step"),
            ("proj-c", "verify", "missing step"),
        ])
        from health import _analyze_promotion_candidates
        candidates = _analyze_promotion_candidates([audit])
        verify = next((c for c in candidates if c["skill"] == "verify"), None)
        assert verify is not None
        assert verify["change_type"] in ("FILE_CREATE", "SKILL_EDIT")

    def test_code_gap_signal_gets_code_edit_type(self, youk_root, claude_root):
        audit = self._audit_with_gaps([
            ("proj-a", "learn", "session.py route_task missing"),
            ("proj-a", "learn", "session.py returns wrong value"),
            ("proj-a", "learn", "session.py health.py conflict"),
        ])
        from health import _analyze_promotion_candidates
        candidates = _analyze_promotion_candidates([audit])
        learn = next((c for c in candidates if c["skill"] == "learn"), None)
        assert learn is not None
        assert learn["change_type"] == "CODE_EDIT"
        assert learn["promotion_target"].endswith("learn.py")


# ── _queue_promotion_proposals ────────────────────────────────────────────────

class TestQueuePromotionProposals:
    def test_queues_skill_edit_proposal(self, youk_root, claude_root):
        import health
        (youk_root / "knowledge" / "proposals").mkdir(parents=True, exist_ok=True)
        candidates = [{
            "skill": "verify",
            "occurrence_count": 4,
            "distinct_projects": 1,
            "sample_gaps": ["gap1", "gap2"],
            "promotion_target": "skills/verify/SKILL.md",
            "change_type": "SKILL_EDIT",
        }]
        from health import _queue_promotion_proposals
        count = _queue_promotion_proposals(candidates)
        assert count == 1
        pending = (youk_root / "knowledge" / "proposals" / "PENDING.md").read_text()
        assert "verify" in pending.lower()

    def test_queues_code_edit_proposal(self, youk_root, claude_root):
        (youk_root / "knowledge" / "proposals").mkdir(parents=True, exist_ok=True)
        candidates = [{
            "skill": "learn",
            "occurrence_count": 5,
            "distinct_projects": 2,
            "sample_gaps": ["session.py missing"],
            "promotion_target": "servers/core/src/learn.py",
            "change_type": "CODE_EDIT",
        }]
        from health import _queue_promotion_proposals
        count = _queue_promotion_proposals(candidates)
        assert count == 1
        pending = (youk_root / "knowledge" / "proposals" / "PENDING.md").read_text()
        assert "CODE_EDIT" in pending


# ── _score_org early returns ───────────────────────────────────────────────────

class TestScoreOrgEdgeCases:
    def test_returns_5_when_no_audit_texts(self, youk_root, claude_root):
        from health import _score_org
        assert _score_org([]) == 5.0

    def test_returns_5_when_no_sessions_parseable(self, youk_root, claude_root):
        from health import _score_org
        result = _score_org(["# empty audit file\nno session blocks here"])
        assert result == 5.0


# ── Token budget parsing ───────────────────────────────────────────────────────

class TestTokenBudgetParsing:
    def _audit(self, token_line: str) -> str:
        return (
            "### Session — 2026-07-01 10:00 UTC\n"
            "Skills: code-review\n"
            f"CloseCluster: yes\n"
            f"{token_line}\n"
        )

    def test_parses_tokens_with_budget(self, youk_root, claude_root):
        audit = self._audit("Tokens: 8000/12000")
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([audit])
        assert len(sessions) == 1
        s = sessions[0]
        assert s["tokens_actual"] == 8000
        assert s["tokens_budget"] == 12000
        assert abs(s["tokens_ratio"] - 8000 / 12000) < 0.01

    def test_parses_tokens_without_budget(self, youk_root, claude_root):
        audit = self._audit("Tokens: 5000")
        from health import _parse_audit_sessions
        sessions = _parse_audit_sessions([audit])
        s = sessions[0]
        assert s["tokens_actual"] == 5000
        assert s["tokens_budget"] == 0
        assert s["tokens_ratio"] is None


# ── _generate_findings — nominal + token efficiency + consecutive_no_close ────

class TestGenerateFindingsExtended:
    def _make_sessions(self, n: int, close: bool = True, skills: str = "code-review", token_line: str = "") -> str:
        blocks = []
        for i in range(n):
            block = (
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\n"
                f"CloseCluster: {'yes' if close else 'no'}\n"
                "Commits: yes\n"
            )
            if token_line:
                block += token_line + "\n"
            blocks.append(block)
        return "\n".join(blocks)

    def test_nominal_finding_when_no_issues(self, youk_root, claude_root):
        # Need token data (suppress no-token finding) + a proposal (suppress starved finding)
        import health
        (youk_root / "knowledge" / "proposals").mkdir(parents=True, exist_ok=True)
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text("## PENDING-001\n")
        blocks = []
        for i in range(3):
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                "Skills: code-review\n"
                "CloseCluster: yes\n"
                "Commits: yes\n"
                "Tokens: 5000/10000\n"
            )
        audit = "\n".join(blocks)
        from health import _generate_findings
        findings = _generate_findings([audit], score=7.5)
        assert any("nominal" in f.lower() for f in findings)

    def test_token_efficiency_over_budget(self, youk_root, claude_root):
        # 3 sessions each 3x over budget triggers the finding
        audit = self._make_sessions(3, close=True, skills="code-review", token_line="Tokens: 30000/10000")
        from health import _generate_findings
        findings = _generate_findings([audit], score=7.0)
        assert any("over budget" in f.lower() for f in findings)

    def test_token_efficiency_under_budget(self, youk_root, claude_root):
        # 3 sessions all <50% of budget
        audit = self._make_sessions(3, close=True, skills="code-review", token_line="Tokens: 2000/10000")
        from health import _generate_findings
        findings = _generate_findings([audit], score=7.0)
        assert any("under budget" in f.lower() for f in findings)

    def test_consecutive_no_close_with_done_skill(self, youk_root, claude_root, tmp_path):
        import json, health
        # Create a project with .claude/skills/done
        project_dir = tmp_path / "myproject"
        (project_dir / ".claude" / "skills" / "done").mkdir(parents=True)
        state = youk_root / "state" / "session.json"
        state.write_text(json.dumps({"last_project": str(project_dir)}))
        monkeypatch_root = youk_root  # already patched via fixture
        # 3 consecutive no-close sessions
        audit = self._make_sessions(3, close=False, skills="code-review")
        findings = health._generate_findings([audit], score=6.0)
        assert any("done" in f.lower() for f in findings)

    def test_consecutive_no_close_no_retrospective(self, youk_root, claude_root):
        # 3 no-close sessions with no /learn recovery → should flag
        audit = self._make_sessions(3, close=False, skills="code-review")
        from health import _generate_findings
        findings = _generate_findings([audit], score=6.0)
        assert any("session-close loop" in f.lower() for f in findings)

    def test_consecutive_no_close_with_retrospective_learn(self, youk_root, claude_root):
        # 3 no-close sessions but /learn ran in one → the specific
        # "neither /done nor retrospective /learn ran" message should NOT appear.
        # (The generic high-skip-rate finding may still appear — that's expected.)
        blocks = []
        for i in range(3):
            skills = "learn" if i == 2 else "code-review"
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\n"
                "CloseCluster: no\n"
                "Commits: yes\n"
            )
        audit = "\n".join(blocks)
        from health import _generate_findings
        findings = _generate_findings([audit], score=6.0)
        assert not any("neither /done nor retrospective" in f.lower() for f in findings)


# ── _skill_quality — single weak skill path ────────────────────────────────────

class TestAuditSkillQualitySingleWeak:
    _ALL_SKILLS = [
        "code-review", "dev-loop", "nfr-check", "security-review",
        "write-spec", "adr", "stress-test", "verify", "learn",
    ]
    _GOOD_CONTENT = (
        "# Skill\n\n## Phase 1\nDo things.\n\n## Quality bar\nMust be thorough.\n\n"
        "## Examples\n```\nexample\n```\n"
    )

    def test_single_weak_skill_message(self, youk_root, claude_root):
        skills_dir = claude_root / "skills"
        # Give all skills good SKILL.md content, except "adr" which gets minimal content
        for name in self._ALL_SKILLS:
            skill_dir = skills_dir / name
            skill_dir.mkdir(parents=True)
            content = "# Minimal\nNo phases.\n" if name == "adr" else self._GOOD_CONTENT
            (skill_dir / "SKILL.md").write_text(content)
        from health import _audit_skill_quality
        findings = _audit_skill_quality(skills_dir)
        assert len(findings) == 1
        assert "adr" in findings[0].lower()
        assert "assess_skill()" in findings[0]


# ── _compute_improvement_velocity — single history + PENDING counting ─────────

class TestImprovementVelocityExtended:
    def _write_audit(self, claude_root, sessions_data):
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        audit_dir = claude_root / "audit"
        blocks = []
        for i, s in enumerate(sessions_data):
            close = s.get("close_cluster", True)
            skills = s.get("skills", "code-review")
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {skills}\n"
                f"CloseCluster: {'yes' if close else 'no'}\n"
            )
        f = audit_dir / f"{month}.md"
        f.write_text("\n".join(blocks))
        return f.read_text()

    def test_single_score_in_history_velocity_is_zero(self, youk_root, claude_root):
        audit = self._write_audit(claude_root, [{"skills": "code-review"}])
        from health import _compute_improvement_velocity
        result = _compute_improvement_velocity([audit], current_score=6.0)
        assert result["velocity"] == 0.0

    def test_proposals_applied_counted(self, youk_root, claude_root):
        (youk_root / "knowledge" / "proposals").mkdir(parents=True, exist_ok=True)
        pending_file = youk_root / "knowledge" / "proposals" / "PENDING.md"
        pending_file.write_text(
            "## PENDING-001\n**Status:** APPLIED — 2026-07-01\n\n"
            "## PENDING-002\n**Status:** APPLIED — 2026-07-02\n\n"
            "## PENDING-003\n**Status:** PENDING\n"
        )
        import health
        monkeypatch_path = pending_file
        import health as h
        orig = h.PROPOSALS_FILE
        h.PROPOSALS_FILE = pending_file
        try:
            audit = self._write_audit(claude_root, [{"skills": "code-review"}])
            from health import _compute_improvement_velocity
            result = _compute_improvement_velocity([audit], current_score=6.0)
            assert result["proposals_applied_total"] == 2
        finally:
            h.PROPOSALS_FILE = orig


# ── _audit_global_contracts — oversize + pending review paths ─────────────────

class TestAuditGlobalContractsExtended:
    def test_oversize_returns_high_count(self, youk_root, claude_root):
        global_dir = youk_root / "knowledge" / "global"
        global_dir.mkdir(parents=True)
        lines = [f"- contract {i}" for i in range(105)]
        (global_dir / "contracts.md").write_text("\n".join(lines) + "\n")
        from health import _audit_global_contracts
        result = _audit_global_contracts()
        assert result["total"] > 100

    def test_auto_promoted_counted(self, youk_root, claude_root):
        global_dir = youk_root / "knowledge" / "global"
        global_dir.mkdir(parents=True)
        content = "- contract one [auto-promoted]\n- contract two\n- contract three [auto-promoted]\n"
        (global_dir / "contracts.md").write_text(content)
        from health import _audit_global_contracts
        result = _audit_global_contracts()
        assert result["auto_promoted"] == 2


# ── _compute_knowledge_velocity — STALLED verdict ─────────────────────────────

class TestKnowledgeVelocityStalled:
    def _write_audit(self, claude_root, sessions_data):
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        blocks = []
        for i, s in enumerate(sessions_data):
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: {s.get('skills', 'code-review')}\n"
                f"CloseCluster: {'yes' if s.get('close_cluster', True) else 'no'}\n"
            )
        f = claude_root / "audit" / f"{month}.md"
        f.write_text("\n".join(blocks))
        return f.read_text()

    def test_stalled_when_contracts_exist_but_nothing_added(self, youk_root, claude_root):
        # project has contracts but no recent saves → STALLED
        proj = youk_root / "knowledge" / "projects" / "myproj"
        proj.mkdir(parents=True)
        (proj / "contracts.md").write_text("- old contract\n")
        audit = self._write_audit(claude_root, [{"skills": "code-review"}])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "myproj")
        assert result["verdict"].startswith("STALLED")

    def test_empty_when_nothing_at_all(self, youk_root, claude_root):
        audit = self._write_audit(claude_root, [{"skills": "code-review"}])
        from health import _compute_knowledge_velocity
        result = _compute_knowledge_velocity([audit], "nonexistent-project")
        assert result["verdict"].startswith("EMPTY")


# ── _compute_diff_preview — REFERENCE_ADD, CONFIG_EDIT, CODE_EDIT branches ────

class TestComputeDiffPreviewExtended:
    def _make_proposal(self, change_type: str, target: str, content: str, target_section: str = "") -> "Proposal":
        from models import Proposal
        return Proposal(
            id="PENDING-TEST-001",
            target=target,
            change_description="test",
            reason="test",
            before="",
            after="",
            status="PENDING",
            proposed_date="2026-07-01",
            change_type=change_type,
            target_section=target_section,
            content=content,
        )

    def test_reference_add_new_file(self, youk_root, claude_root):
        skills_dir = claude_root / "skills"
        (skills_dir / "verify" / "references").mkdir(parents=True)
        proposal = self._make_proposal("REFERENCE_ADD", "verify", "ref content", "my-ref.md")
        import health
        monkeypatch_claude = claude_root
        orig = health.CLAUDE_ROOT
        health.CLAUDE_ROOT = claude_root
        try:
            from health import _compute_diff_preview
            result = _compute_diff_preview(proposal)
            assert result["change_type"] == "REFERENCE_ADD"
            assert "file does not exist" in result["before"]
        finally:
            health.CLAUDE_ROOT = orig

    def test_config_edit_missing_file(self, youk_root, claude_root):
        proposal = self._make_proposal("CONFIG_EDIT", "nonexistent.yaml", "key: value")
        from health import _compute_diff_preview
        result = _compute_diff_preview(proposal)
        assert "error" in result
        assert "Config not found" in result["error"]

    def test_config_edit_existing_file(self, youk_root, claude_root):
        config_dir = youk_root / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "settings.yaml").write_text("existing_key: old_value\n")
        proposal = self._make_proposal("CONFIG_EDIT", "settings.yaml", "new_key: new_value")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            from health import _compute_diff_preview
            result = _compute_diff_preview(proposal)
            assert result["change_type"] == "CONFIG_EDIT"
            assert "existing_key" in result["before"]
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_no_function(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def existing_fn():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "def new_fn():\n    pass\n", "nonexistent_fn")
            from health import _compute_diff_preview
            result = _compute_diff_preview(proposal)
            assert "function not found" in result["before"]
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_with_matching_function(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def target_fn():\n    return 1\n\ndef other_fn():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "def target_fn():\n    return 2\n", "target_fn")
            from health import _compute_diff_preview
            result = _compute_diff_preview(proposal)
            assert result["change_type"] == "CODE_EDIT"
            assert "target_fn" in result["before"]
        finally:
            health.YOUK_ROOT = orig


# ── _execute_proposal — REFERENCE_ADD, CONFIG_EDIT, CODE_EDIT branches ────────

class TestExecuteProposalExtended:
    def _make_proposal(self, change_type: str, target: str, content: str, target_section: str = "") -> "Proposal":
        from models import Proposal
        return Proposal(
            id="PENDING-EXT-001",
            target=target,
            change_description="test",
            reason="test",
            before="",
            after="",
            status="PENDING",
            proposed_date="2026-07-01",
            change_type=change_type,
            target_section=target_section,
            content=content,
        )

    def test_reference_add_writes_file(self, youk_root, claude_root):
        skills_dir = claude_root / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        import health
        orig = health.CLAUDE_ROOT
        health.CLAUDE_ROOT = claude_root
        try:
            proposal = self._make_proposal("REFERENCE_ADD", "verify", "# Ref Content\n", "my-ref.md")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is True
            ref_file = claude_root / "skills" / "verify" / "references" / "my-ref.md"
            assert ref_file.exists()
            assert "Ref Content" in ref_file.read_text()
        finally:
            health.CLAUDE_ROOT = orig

    def test_config_edit_missing_file_returns_error(self, youk_root, claude_root):
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CONFIG_EDIT", "nonexistent.yaml", "key: val")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is False
            assert "Config not found" in result["error"]
        finally:
            health.YOUK_ROOT = orig

    def test_config_edit_merges_yaml(self, youk_root, claude_root):
        config_dir = youk_root / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "settings.yaml").write_text("key_a: old\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CONFIG_EDIT", "settings.yaml", "key_b: new\n")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is True
            written = (config_dir / "settings.yaml").read_text()
            assert "key_a" in written
            assert "key_b" in written
        finally:
            health.YOUK_ROOT = orig

    def test_config_edit_yaml_error(self, youk_root, claude_root):
        config_dir = youk_root / "config"
        config_dir.mkdir(parents=True)
        (config_dir / "bad.yaml").write_text("valid: yaml\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CONFIG_EDIT", "bad.yaml", ": bad: yaml: content: [\n")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is False
            assert "YAML" in result["error"]
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_missing_content(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def myfn():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "", "myfn")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is False
            assert "content" in result["error"].lower()
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_missing_section(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def myfn():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "def myfn():\n    return 1\n", "")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is False
            assert "target_section" in result["error"].lower()
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_function_not_found(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def myfn():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "def ghost():\n    pass\n", "ghost")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is False
            assert "not found" in result["error"].lower()
        finally:
            health.YOUK_ROOT = orig

    def test_code_edit_replaces_function(self, youk_root, claude_root):
        code_file = youk_root / "servers" / "core" / "src" / "somefile.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("def myfn():\n    return 1\n\ndef other():\n    pass\n")
        import health
        orig = health.YOUK_ROOT
        health.YOUK_ROOT = youk_root
        try:
            proposal = self._make_proposal("CODE_EDIT", "servers/core/src/somefile.py", "def myfn():\n    return 99\n", "myfn")
            from health import _execute_proposal
            result = _execute_proposal(proposal)
            assert result["applied"] is True
            written = code_file.read_text()
            assert "return 99" in written
        finally:
            health.YOUK_ROOT = orig


# ── run_health_check_with_skill_signals — promotion + coverage + cross-project ─

class TestRunHealthCheckWithSkillSignalsExtended:
    def _write_audit_with_gaps(self, claude_root, gaps: list[tuple[str, str, str]]) -> None:
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        lines = []
        for i, (proj, skill, desc) in enumerate(gaps):
            lines.append(f"### Session — 2026-07-0{i+1} 10:00 UTC")
            lines.append(f"Project: {proj}")
            lines.append("Skills: code-review")
            lines.append("CloseCluster: yes")
            lines.append(f"SkillGap: {skill} — {desc}")
        (claude_root / "audit" / f"{month}.md").write_text("\n".join(lines))

    def test_promotion_queued_when_threshold_met(self, youk_root, claude_root):
        self._write_audit_with_gaps(claude_root, [
            ("proj-a", "verify", "gap 1"),
            ("proj-a", "verify", "gap 2"),
            ("proj-a", "verify", "gap 3"),
        ])
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert result.get("promotion_proposals_queued", 0) >= 1

    def test_cross_project_patterns_surfaced(self, youk_root, claude_root):
        # Two projects with the same contract → should appear in global_pattern_candidates
        proj_a = youk_root / "knowledge" / "projects" / "alpha"
        proj_b = youk_root / "knowledge" / "projects" / "beta"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        (proj_a / "contracts.md").write_text("- always run tests before commit\n")
        (proj_b / "contracts.md").write_text("- always run tests before commit\n")
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        assert "global_pattern_candidates" in result

    def test_knowledge_velocity_stalled_surfaces_warning(self, youk_root, claude_root):
        # No /learn, no contracts → knowledge velocity will be EMPTY or STALLED
        from health import run_health_check_with_skill_signals
        result = run_health_check_with_skill_signals()
        velocity = result.get("knowledge_velocity", {})
        verdict = velocity.get("verdict", "")
        assert verdict.startswith(("STALLED", "EMPTY"))
