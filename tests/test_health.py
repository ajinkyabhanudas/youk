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
