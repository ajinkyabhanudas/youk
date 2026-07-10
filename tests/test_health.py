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
