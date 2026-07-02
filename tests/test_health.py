"""Tests for health.py — proposal filtering, 0-contracts finding, self-heal signals."""
from __future__ import annotations
from pathlib import Path
import pytest


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
        from health import _generate_findings, _parse_audit_sessions, _score_org
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
        skip_findings = [f for f in findings if "skipped" in f.lower() or "cluster" in f.lower()]
        assert skip_findings, f"Expected skip-rate finding. Got: {findings}"

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

    def test_zero_close_cluster_caps_score(self):
        """No /done usage means close_rate=0 — even with good capability skills, score stays low."""
        score = self._score([
            {"skills": "code-review", "close_cluster": False},
            {"skills": "learn", "close_cluster": False},
        ])
        # close_rate=0 means: 5.0 + 0*2.0 + 1.0*1.0 = 6.0 at best (with full capability rate)
        assert score <= 6.0

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
        """3+ consecutive sessions without /done caps org_score at 6.5."""
        score = self._score([
            {"skills": "code-review", "close_cluster": True},   # one good session
            {"skills": "code-review", "close_cluster": False},  # then 3 consecutive skips
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": False},
        ])
        assert score <= 6.5

    def test_discipline_gate_not_applied_below_threshold(self):
        """2 consecutive /done skips does NOT trigger the gate."""
        score = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": False},
        ])
        # close_rate=0.5, capability=1.0 → 5.0 + 1.0 + 1.0 = 7.0; gate not triggered
        assert score > 6.5

    def test_discipline_gate_unlocked_when_recent_done(self):
        """Gate does NOT apply if the most recent session used /done."""
        # 3 good sessions + 2 skips + 1 good at end → consecutive_skips=0, gate lifts
        # close_rate=4/6=0.67, capability=1.0 → 5.0+1.33+1.0=7.33 > 6.5
        score = self._score([
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": True},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": False},
            {"skills": "code-review", "close_cluster": True},  # most recent: gate lifts
        ])
        assert score > 6.5


class TestGenerateFindingsDisciplineGate:
    def _run(self, claude_root, youk_root, sessions: list[dict]) -> list[str]:
        blocks = []
        for i, s in enumerate(sessions):
            close = "yes" if s.get("close_cluster") else "no"
            blocks.append(
                f"### Session — 2026-07-0{i+1} 10:00 UTC\n"
                f"Skills: code-review\nCloseCluster: {close}\nCommits: yes\n"
            )
        audit = "\n".join(blocks)
        (claude_root / "audit" / "2026-07.md").write_text(audit)
        from health import _generate_findings, _score_org
        score = _score_org([audit])
        return _generate_findings([audit], score)

    def test_discipline_gate_finding_when_3_consecutive_skips(self, youk_root, claude_root):
        findings = self._run(claude_root, youk_root, [
            {"close_cluster": True},
            {"close_cluster": False},
            {"close_cluster": False},
            {"close_cluster": False},
        ])
        gate_findings = [f for f in findings if "discipline gate" in f.lower()]
        assert gate_findings, f"Expected discipline gate finding. Got: {findings}"

    def test_no_discipline_gate_finding_when_recent_done(self, youk_root, claude_root):
        findings = self._run(claude_root, youk_root, [
            {"close_cluster": False},
            {"close_cluster": False},
            {"close_cluster": False},
            {"close_cluster": True},  # most recent: gate lifts
        ])
        gate_findings = [f for f in findings if "discipline gate" in f.lower()]
        assert not gate_findings, f"Unexpected gate finding: {gate_findings}"
