"""Tests for FILE_CREATE/REFERENCE_ADD target resolution in health.py.

Two real, confirmed defects (2026-09-19), found while investigating why
apply_proposal appeared broken for the entire FILE_CREATE change_type and
appeared to silently no-op on a REFERENCE_ADD:

1. FILE_CREATE checked proposal.target (as given) against absolute
   container-internal roots (/youk, /claude/skills). Every real generated
   FILE_CREATE proposal uses a relative target (e.g. "cross-project.md"),
   and any external caller only knows a host-absolute path — neither form
   ever satisfies that check, so every real proposal was rejected as
   "outside permitted write roots."

2. A successful write's returned target_file is the container-internal path
   (health.py runs inside the youk-core Docker container). A caller running
   outside the container — e.g. Claude Code on the host — cannot resolve
   that path, so a real, successful write was indistinguishable from a
   silent no-op. Confirmed: a REFERENCE_ADD write from an earlier session
   landed correctly on disk at the host-mapped path, but the tool's own
   returned path did not exist anywhere the caller could look.
"""
from __future__ import annotations

from pathlib import Path

from models import Proposal


def _file_create_proposal(target: str, content: str = "hello") -> Proposal:
    return Proposal(
        id="PENDING-FC-TEST",
        target=target,
        change_description="test",
        reason="test",
        before="",
        after="",
        status="PENDING",
        proposed_date="2026-09-19",
        change_type="FILE_CREATE",
        target_section="",
        content=content,
    )


def _reference_add_proposal(skill: str, section_file: str, content: str = "note") -> Proposal:
    return Proposal(
        id="PENDING-RA-TEST",
        target=skill,
        change_description="test",
        reason="test",
        before="",
        after="",
        status="PENDING",
        proposed_date="2026-09-19",
        change_type="REFERENCE_ADD",
        target_section=section_file,
        content=content,
    )


class TestResolveWriteTarget:
    def test_relative_target_resolves_under_youk_root(self, youk_root, claude_root):
        import health
        resolved = health._resolve_write_target("knowledge/cross-project.md")
        assert resolved == (youk_root / "knowledge" / "cross-project.md").resolve()

    def test_host_absolute_path_under_dot_claude_youk_translates(self, youk_root, claude_root):
        import health
        raw = f"/Users/someone/.claude/youk/knowledge/x.md"
        resolved = health._resolve_write_target(raw)
        assert resolved == (youk_root / "knowledge" / "x.md").resolve()

    def test_host_absolute_path_under_dot_claude_skills_translates(self, youk_root, claude_root):
        import health
        raw = "/Users/someone/.claude/skills/some-skill/references/x.md"
        resolved = health._resolve_write_target(raw)
        assert resolved == (claude_root / "skills" / "some-skill" / "references" / "x.md").resolve()

    def test_container_absolute_path_used_as_is(self, youk_root, claude_root):
        import health
        raw = str(youk_root / "knowledge" / "y.md")
        resolved = health._resolve_write_target(raw)
        assert resolved == (youk_root / "knowledge" / "y.md").resolve()

    def test_genuinely_external_target_returns_none(self, youk_root, claude_root):
        import health
        resolved = health._resolve_write_target("/Users/someone/Desktop/other-project/f.md")
        assert resolved is None

    def test_traversal_escape_returns_none(self, youk_root, claude_root):
        import health
        resolved = health._resolve_write_target("../../../etc/passwd")
        assert resolved is None


class TestHostRelativePath:
    def test_youk_root_path_prefixed_with_youk(self, youk_root, claude_root):
        import health
        p = youk_root / "knowledge" / "x.md"
        assert health._host_relative_path(p) == "youk/knowledge/x.md"

    def test_claude_root_path_has_claude_prefix_stripped(self, youk_root, claude_root):
        import health
        p = claude_root / "skills" / "foo" / "references" / "bar.md"
        assert health._host_relative_path(p) == "skills/foo/references/bar.md"


class TestExecuteProposalFileCreate:
    def test_relative_target_now_succeeds(self, youk_root, claude_root):
        import health
        proposal = _file_create_proposal("knowledge/new-note.md", content="real content")
        result = health._execute_proposal(proposal)
        assert result["applied"] is True
        written = youk_root / "knowledge" / "new-note.md"
        assert written.exists()
        assert written.read_text() == "real content"
        assert result["target_file_relative"] == "youk/knowledge/new-note.md"

    def test_external_target_still_blocked(self, youk_root, claude_root):
        import health
        proposal = _file_create_proposal("/Users/someone/Desktop/other-project/f.md")
        result = health._execute_proposal(proposal)
        assert result["applied"] is False
        assert "outside" in result["error"] or "does not resolve" in result["error"]


class TestExecuteProposalReferenceAdd:
    def test_reference_add_writes_and_reports_verifiable_path(self, youk_root, claude_root):
        import health
        proposal = _reference_add_proposal("some-skill", "notes.md", content="the note")
        result = health._execute_proposal(proposal)
        assert result["applied"] is True
        expected = claude_root / "skills" / "some-skill" / "references" / "notes.md"
        assert expected.exists()
        assert expected.read_text() == "the note"
        assert result["target_file_relative"] == "skills/some-skill/references/notes.md"
        # The relative path is directly checkable against the fixture's own root,
        # closing the exact gap that made a real write look like a no-op.
        assert (claude_root / result["target_file_relative"]).exists()
