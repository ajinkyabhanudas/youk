"""Tests for CAP-8: SKILL_EDIT diff payload + R10 metric surfaces.

Covers:
  8a — diff-in-payload: apply_proposal SKILL_EDIT returns diff_preview with +/- lines
  8a — diff-in-audit: audit file contains ```diff block after apply
  8b — R10 format in health.py _generate_findings (n/d label)
  8b — R10 format in session.py _compute_dashboard_summary (n/d label)
  8b — R10 format in export_stats.py _render output (n/d label)
  8b — export_stats reconciliation table: appears when skill_denom != close_total
  GATE-E3 — no-score invariant: computed org_score equal with-vs-without recent review
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import pytest

YOUK_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(YOUK_ROOT / "servers" / "core" / "src"))
sys.path.insert(0, str(YOUK_ROOT / "servers" / "shared"))
sys.path.insert(0, str(YOUK_ROOT / "scripts"))


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def skill_root(tmp_path):
    """Fake CLAUDE_ROOT with a minimal SKILL.md."""
    croot = tmp_path / "claude"
    skill_dir = croot / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# test-skill\n\n## Existing Section\n\nOriginal content here.\n\n## Another Section\n\nOther content.\n"
    )
    (croot / "audit").mkdir(parents=True)
    return croot


def _make_proposal(**kwargs):
    """Build a Proposal with required fields, overridable via kwargs."""
    from models import Proposal
    defaults = dict(
        id="test-001",
        target="test-skill",
        change_description="test change",
        reason="test",
        before="",
        after="",
        status="PENDING",
        proposed_date="2026-07-18",
        change_type="SKILL_EDIT",
        target_section="New Section",
        content="This is the new section content.\nWith multiple lines.\n",
    )
    defaults.update(kwargs)
    return Proposal(**defaults)


@pytest.fixture
def proposal_obj():
    """Minimal Proposal object for SKILL_EDIT."""
    return _make_proposal()


# ── 8a: diff-in-payload ─────────────────────────────────────────────────────────

class TestDiffInPayload:
    def test_skill_edit_returns_diff_preview_key(self, skill_root, proposal_obj, monkeypatch):
        """apply_proposal SKILL_EDIT returns a diff_preview key in the result."""
        import health as h
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        result = h._execute_proposal(proposal_obj)
        assert result.get("applied") is True, f"Apply failed: {result}"
        assert "diff_preview" in result, "diff_preview key missing from SKILL_EDIT result"

    def test_diff_preview_contains_plus_lines(self, skill_root, proposal_obj, monkeypatch):
        """diff_preview contains + lines showing the new content."""
        import health as h
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        result = h._execute_proposal(proposal_obj)
        diff = result["diff_preview"]
        assert "+" in diff, "diff_preview has no + lines"
        assert "new section content" in diff.lower() or "New Section" in diff, (
            "diff_preview does not contain the new content"
        )

    def test_diff_preview_contains_minus_or_context_lines(self, skill_root, monkeypatch):
        """diff_preview for a section replacement contains - lines showing removed content."""
        import health as h
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        p = _make_proposal(
            id="test-002",
            target_section="Existing Section",
            content="Replacement content.\n",
        )
        result = h._execute_proposal(p)
        assert result.get("applied") is True, f"Apply failed: {result}"
        diff = result["diff_preview"]
        # After replacing existing section, diff must show context or removed lines
        assert any(line.startswith("-") or line.startswith(" ") for line in diff.splitlines()), (
            "diff_preview has no - or context lines on section replacement"
        )

    def test_diff_lines_total_reported(self, skill_root, proposal_obj, monkeypatch):
        """apply_proposal returns diff_lines_total count."""
        import health as h
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        result = h._execute_proposal(proposal_obj)
        assert "diff_lines_total" in result
        assert result["diff_lines_total"] > 0

    def test_non_skill_edit_has_no_diff_preview(self, tmp_path, monkeypatch):
        """FILE_CREATE result does not have diff_preview (diff only for SKILL_EDIT)."""
        import health as h
        croot = tmp_path / "claude"
        youk_root = tmp_path / "youk"
        skill_dir = croot / "skills" / "new-skill" / "references"
        skill_dir.mkdir(parents=True)
        youk_root.mkdir(parents=True)
        monkeypatch.setattr(h, "CLAUDE_ROOT", croot)
        monkeypatch.setattr(h, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(h, "_ALLOWED_WRITE_ROOTS", [youk_root, croot / "skills"])

        target_path = croot / "skills" / "new-skill" / "references" / "test.md"
        p = _make_proposal(
            id="test-003",
            change_type="FILE_CREATE",
            target=str(target_path),
            target_section="",
            content="New file content.\n",
        )
        result = h._execute_proposal(p)
        assert result.get("applied") is True, f"FILE_CREATE failed: {result}"
        assert "diff_preview" not in result, "diff_preview should not appear on FILE_CREATE"


# ── 8a: diff-in-audit ───────────────────────────────────────────────────────────

class TestDiffInAudit:
    def test_audit_file_contains_diff_block(self, skill_root, proposal_obj, monkeypatch):
        """After SKILL_EDIT apply, audit file contains ```diff block."""
        import health as h
        from datetime import datetime
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        month = datetime.utcnow().strftime("%Y-%m")
        audit_file = skill_root / "audit" / f"{month}.md"
        audit_file.write_text("# audit\n\n")

        h._execute_proposal(proposal_obj)

        content = audit_file.read_text()
        assert "```diff" in content, "Audit file missing ```diff block after SKILL_EDIT"

    def test_audit_diff_contains_skill_patch_header(self, skill_root, proposal_obj, monkeypatch):
        """Audit entry starts with SkillPatch: line followed by the diff block."""
        import health as h
        from datetime import datetime
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)

        month = datetime.utcnow().strftime("%Y-%m")
        audit_file = skill_root / "audit" / f"{month}.md"
        audit_file.write_text("# audit\n\n")

        h._execute_proposal(proposal_obj)

        content = audit_file.read_text()
        assert "SkillPatch: test-skill" in content
        # The diff block must follow the SkillPatch line
        patch_idx = content.index("SkillPatch: test-skill")
        diff_idx = content.index("```diff")
        assert diff_idx > patch_idx, "```diff block must appear after SkillPatch: line"

    def test_audit_skipped_when_no_audit_file(self, skill_root, proposal_obj, monkeypatch):
        """If no audit file exists, apply still succeeds (audit write failure is non-blocking)."""
        import health as h
        monkeypatch.setattr(h, "CLAUDE_ROOT", skill_root)
        monkeypatch.setattr(h, "YOUK_ROOT", skill_root)
        # No audit file created — should not raise
        result = h._execute_proposal(proposal_obj)
        assert result.get("applied") is True


# ── 8b: R10 in health.py _generate_findings ────────────────────────────────────

_R10_PATTERN = re.compile(r"\d+%\s+\(\d+/\d+")  # matches "42% (n/d" or "42% (n/d label)"


class TestR10HealthFindings:
    def _make_sessions_block(self, n_sessions: int, with_capability: bool = True, with_developer_caught: bool = True) -> list[str]:
        """Build minimal audit text blocks for _parse_audit_sessions."""
        blocks = []
        for i in range(n_sessions):
            skills_line = "Skills: code-review, learn" if with_capability else "Skills: none"
            caught_line = "DeveloperCaught: nfr_check" if with_developer_caught else ""
            block = (
                f"### Session — 2026-01-{i+1:02d}\n"
                f"Project: test-project\n"
                f"{skills_line}\n"
                f"Commits: yes\n"
                f"CloseCluster: yes\n"
                f"Outcome: WORKED\n"
                f"OutcomeResult: WORKED\n"
                + (f"{caught_line}\n" if caught_line else "")
            )
            blocks.append(block)
        return blocks

    def test_autonomy_finding_has_r10_nd_label(self):
        """Developer autonomy finding includes (n/d tracked sessions) format."""
        import health as h

        audit_texts = self._make_sessions_block(8, with_capability=True, with_developer_caught=True)
        sessions = h._parse_audit_sessions(audit_texts)
        findings = h._generate_findings(audit_texts, score=7.0)

        autonomy_findings = [f for f in findings if "autonomy" in f.lower()]
        assert autonomy_findings, "No autonomy finding generated"
        finding = autonomy_findings[0]
        assert _R10_PATTERN.search(finding), (
            f"Autonomy finding lacks R10 (n/d) label: {finding!r}"
        )

    def test_outcome_signal_rate_finding_has_r10_label(self):
        """Outcome signal rate finding includes [R10] label with n/d denominator."""
        import health as h

        audit_texts = self._make_sessions_block(12, with_capability=True)
        findings = h._generate_findings(audit_texts, score=7.0)

        outcome_findings = [f for f in findings if "Outcome signal rate" in f]
        assert outcome_findings, "No outcome signal rate finding generated"
        finding = outcome_findings[0]
        assert "[R10]" in finding, f"Outcome signal rate missing [R10] tag: {finding!r}"
        assert _R10_PATTERN.search(finding), f"Missing n/d label: {finding!r}"


# ── 8b: R10 in session.py dashboard ────────────────────────────────────────────

class TestR10SessionDashboard:
    def _build_audit_dir(self, tmp_path, n_sessions: int, done_count: int) -> Path:
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        lines = []
        for i in range(n_sessions):
            close = "yes" if i < done_count else "no"
            lines.append(
                f"### Session — 2026-01-{i+1:02d}\n"
                f"Project: test\n"
                f"Skills: code-review\n"
                f"CloseCluster: {close}\n"
                f"Commits: yes\n"
            )
        (audit_dir / "2026-01.md").write_text("\n".join(lines))
        return audit_dir

    def test_skills_rate_has_r10_nd_label(self, tmp_path, monkeypatch):
        """_compute_dashboard_summary skill rate segment includes (n/d sessions) R10 label."""
        import session as s
        monkeypatch.setattr(s, "YOUK_ROOT", tmp_path)

        audit_dir = self._build_audit_dir(tmp_path, n_sessions=6, done_count=3)
        summary = s._compute_dashboard_summary(audit_dir, pending_proposals=0)

        assert "skills:" in summary
        skill_segment = [p for p in summary.split("  ·  ") if "skills:" in p][0]
        assert _R10_PATTERN.search(skill_segment), (
            f"Skill rate segment lacks R10 (n/d) label: {skill_segment!r}"
        )

    def test_done_rate_has_r10_nd_label(self, tmp_path, monkeypatch):
        """/done rate segment includes (n/d sessions) R10 label."""
        import session as s
        monkeypatch.setattr(s, "YOUK_ROOT", tmp_path)

        audit_dir = self._build_audit_dir(tmp_path, n_sessions=6, done_count=4)
        summary = s._compute_dashboard_summary(audit_dir, pending_proposals=0)

        assert "/done:" in summary
        done_segment = [p for p in summary.split("  ·  ") if "/done:" in p][0]
        assert _R10_PATTERN.search(done_segment), (
            f"/done rate segment lacks R10 (n/d) label: {done_segment!r}"
        )


# ── 8b: R10 in export_stats.py _render ─────────────────────────────────────────

class TestR10ExportStats:
    def _make_sessions(self, n: int, with_skill: bool = True, close_rate: float = 0.5) -> list:
        """Build SessionRecord list for _render."""
        from export_stats import SessionRecord
        records = []
        for i in range(n):
            has_close = i < int(n * close_rate)
            skills = ["code-review"] if with_skill else []
            records.append(SessionRecord(
                date=f"2026-01-{(i % 28) + 1:02d}",
                has_commits=True,
                has_close_cluster=has_close,
                skills=skills,
            ))
        return records

    def test_skill_rate_has_r10_label(self):
        """export_stats _render skill invocation rate includes (n/d real-work sessions)."""
        from export_stats import _render
        sessions = self._make_sessions(20, with_skill=True, close_rate=0.6)
        output = _render(sessions, metrics=[])
        assert "real-work sessions" in output, "Skill rate R10 label 'real-work sessions' missing"
        assert _R10_PATTERN.search(output), "Skill rate lacks (n/d) format in export_stats"

    def test_close_rate_has_r10_label(self):
        """export_stats _render close rate includes (n/d all sessions)."""
        from export_stats import _render
        sessions = self._make_sessions(20, close_rate=0.5)
        output = _render(sessions, metrics=[])
        assert "all sessions" in output, "Close rate R10 label 'all sessions' missing"

    def test_autonomy_rate_has_r10_label(self, tmp_path):
        """export_stats _render developer autonomy includes (n/d gate-eligible sessions)."""
        from export_stats import _render, SessionRecord
        # Build audit dir with DeveloperCaught entries
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        lines = []
        for i in range(20):
            lines.append(
                f"### Session — 2026-01-{(i % 28) + 1:02d}\n"
                f"Skills: code-review\n"
                f"Commits: yes\n"
                + ("DeveloperCaught: nfr_check\n" if i % 2 == 0 else "")
            )
        (audit_dir / "2026-01.md").write_text("\n".join(lines))
        sessions = self._make_sessions(20)
        output = _render(sessions, metrics=[], audit_dir=audit_dir)
        assert "gate-eligible sessions" in output, (
            "Autonomy rate R10 label 'gate-eligible sessions' missing in export_stats"
        )


# ── 8b: export reconciliation table ────────────────────────────────────────────

class TestExportReconciliationTable:
    def test_reconciliation_table_appears_when_denominators_differ(self):
        """Reconciliation table appears when skill_denom != close_total."""
        from export_stats import _render, SessionRecord
        # skill_denom = sessions with real work; close_total = all sessions
        # Add 3 idle sessions (no commits, no skills) so denominators diverge
        sessions = []
        for i in range(12):
            has_work = i < 9  # 9 real-work, 3 idle
            sessions.append(SessionRecord(
                date=f"2026-01-{i+1:02d}",
                has_commits=has_work,
                has_close_cluster=(i < 6),
                skills=["code-review"] if has_work else [],
            ))
        output = _render(sessions, metrics=[])
        assert "denominator reconciliation" in output, (
            "Reconciliation table missing when skill_denom != close_total"
        )
        assert "real-work sessions" in output
        assert "all recorded sessions" in output

    def test_no_reconciliation_table_when_denominators_equal(self):
        """Reconciliation table absent when both rates share the same denominator."""
        from export_stats import _render, SessionRecord
        # All sessions have real work — skill_denom == close_total
        sessions = [
            SessionRecord(
                date=f"2026-01-{i+1:02d}",
                has_commits=True,
                has_close_cluster=(i % 2 == 0),
                skills=["code-review"],
            )
            for i in range(12)
        ]
        output = _render(sessions, metrics=[])
        assert "denominator reconciliation" not in output, (
            "Reconciliation table should not appear when denominators match"
        )

    def test_reconciliation_table_format(self):
        """Reconciliation table is a valid markdown table with header and data rows."""
        from export_stats import _render, SessionRecord
        sessions = []
        for i in range(15):
            has_work = i < 10
            sessions.append(SessionRecord(
                date=f"2026-01-{i+1:02d}",
                has_commits=has_work,
                has_close_cluster=(i < 8),
                skills=["code-review"] if has_work else [],
            ))
        output = _render(sessions, metrics=[])
        assert "| metric" in output
        assert "| skill invocation rate" in output
        assert "| session close rate" in output


# ── GATE E3: no-score invariant (org_score equality) ───────────────────────────

class TestOrgScoreInvariantStrong:
    """GATE E3 strengthened invariant: org_score computed identically
    whether or not a recent external review exists."""

    def _build_health_input(self, tmp_path):
        """Build minimal health.py state: audit logs, metrics, proposals."""
        youk_root = tmp_path / "youk"
        claude_root = tmp_path / "claude"
        (youk_root / "state" / "relay").mkdir(parents=True)
        (youk_root / "knowledge" / "proposals").mkdir(parents=True)
        (youk_root / "knowledge" / "audit").mkdir(parents=True)
        (youk_root / "state").mkdir(parents=True, exist_ok=True)
        (claude_root / "audit").mkdir(parents=True)
        audit_dir = claude_root / "audit"
        lines = []
        for i in range(10):
            lines.append(
                f"### Session — 2026-01-{i+1:02d}\n"
                f"Project: test\n"
                f"Skills: code-review, learn\n"
                f"DeveloperCaught: nfr_check\n"
                f"Commits: yes\n"
                f"CloseCluster: yes\n"
                f"Outcome: WORKED\n"
                f"OutcomeResult: WORKED\n"
            )
        (audit_dir / "2026-01.md").write_text("\n".join(lines))
        return youk_root, claude_root

    def test_org_score_identical_without_and_with_review(self, tmp_path, monkeypatch):
        """org_score from _score_org must be identical regardless of whether
        state/relay/REVIEW-* dirs exist.  This is the Goodhart-invariant test."""
        import health as h

        youk_root, claude_root = self._build_health_input(tmp_path)
        monkeypatch.setattr(h, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(h, "CLAUDE_ROOT", claude_root)
        monkeypatch.setattr(h, "AUDIT_DIR", claude_root / "audit")
        monkeypatch.setattr(h, "PROPOSALS_FILE", youk_root / "knowledge" / "proposals" / "PENDING.md")

        audit_texts = [f.read_text() for f in sorted((claude_root / "audit").glob("*.md"))]

        # Score WITHOUT any review dir
        score_no_review = h._score_org(audit_texts)

        # Create a recent review dir to simulate "just reviewed"
        (youk_root / "state" / "relay" / "REVIEW-2026-07-18").mkdir(parents=True, exist_ok=True)

        # Score WITH review dir — must be identical (YOUK_ROOT patched, so _score_org would
        # see it if it ever read state/relay/; it must not)
        score_with_review = h._score_org(audit_texts)

        assert score_no_review == score_with_review, (
            f"org_score changed based on review presence: "
            f"without={score_no_review}, with={score_with_review}. "
            "External review must not influence org_score computation."
        )

    def test_score_org_signature_excludes_relay_dir(self, tmp_path, monkeypatch):
        """_score_org produces the same value whether relay dir exists or not."""
        import health as h

        youk_root, claude_root = self._build_health_input(tmp_path)
        monkeypatch.setattr(h, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(h, "CLAUDE_ROOT", claude_root)
        monkeypatch.setattr(h, "AUDIT_DIR", claude_root / "audit")
        monkeypatch.setattr(h, "PROPOSALS_FILE", youk_root / "knowledge" / "proposals" / "PENDING.md")

        audit_texts = [f.read_text() for f in sorted((claude_root / "audit").glob("*.md"))]

        # Score with relay dir present
        (youk_root / "state" / "relay" / "REVIEW-2026-07-01").mkdir(parents=True, exist_ok=True)
        score_relay_present = h._score_org(audit_texts)

        # Remove relay dir entirely
        import shutil
        shutil.rmtree(youk_root / "state" / "relay")
        (youk_root / "state" / "relay").mkdir(parents=True)  # recreate empty

        score_relay_absent = h._score_org(audit_texts)

        assert score_relay_present == score_relay_absent, (
            f"_score_org value differed: present={score_relay_present}, absent={score_relay_absent}"
        )
