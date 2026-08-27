"""Tests for skill link drift detection and missing-skill name normalization.

Both guard real failures found in session 93:
  - `intake` and `coverage-tree` were committed to the repo but had no runtime
    symlink, so CLAUDE.md routed to skills that could not load. Nothing detected it.
  - detect_skill_gaps reported 8 of 17 "missing skills" that were MCP tool names or
    underscore spellings of existing skills, and recommended generate_skill() for them.
"""
from __future__ import annotations

from pathlib import Path

from skill_link_check import check_skill_links


def _make_tree(root: Path, skills: list[str]) -> Path:
    d = root / "skills"
    d.mkdir(parents=True, exist_ok=True)
    for s in skills:
        (d / s).mkdir(exist_ok=True)
    return d


class TestUnlinkedDetection:
    def test_repo_skill_missing_from_runtime_is_unlinked(self, tmp_path):
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify", "intake", "coverage-tree"])
        _make_tree(claude, ["verify"])
        r = check_skill_links(youk, claude)
        assert r["unlinked"] == ["coverage-tree", "intake"]
        assert r["healthy"] is False

    def test_message_names_the_skills_and_the_remedy(self, tmp_path):
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify", "intake"])
        _make_tree(claude, ["verify"])
        msg = check_skill_links(youk, claude)["message"]
        assert "intake" in msg
        assert "install.sh" in msg

    def test_fully_linked_tree_is_healthy(self, tmp_path):
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify", "intake"])
        _make_tree(claude, ["verify", "intake"])
        r = check_skill_links(youk, claude)
        assert r["unlinked"] == []
        assert r["healthy"] is True
        assert r["message"] == ""


class TestOrphanDetection:
    def test_runtime_only_skill_is_orphaned(self, tmp_path):
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify"])
        _make_tree(claude, ["verify", "citation-resolver"])
        r = check_skill_links(youk, claude)
        assert r["orphaned"] == ["citation-resolver"]

    def test_orphans_alone_do_not_fail_health(self, tmp_path):
        """An orphan works locally. Only an unlinked skill breaks a route."""
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify"])
        _make_tree(claude, ["verify", "citation-resolver"])
        r = check_skill_links(youk, claude)
        assert r["healthy"] is True
        assert "not version controlled" in r["message"]


class TestDegradesSafely:
    def test_missing_runtime_tree_is_not_drift(self, tmp_path):
        """Running straight from the repo is a valid dev setup, not drift."""
        youk = tmp_path / "youk"
        _make_tree(youk, ["verify"])
        r = check_skill_links(youk, tmp_path / "nonexistent")
        assert r["healthy"] is True
        assert r["unlinked"] == []

    def test_both_missing_returns_healthy(self, tmp_path):
        r = check_skill_links(tmp_path / "a", tmp_path / "b")
        assert r["healthy"] is True

    def test_symlinked_entries_count_as_present(self, tmp_path):
        """Runtime skills are symlinks, so is_dir() alone must not be the test."""
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        repo_dir = _make_tree(youk, ["verify"])
        runtime_dir = claude / "skills"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "verify").symlink_to(repo_dir / "verify")
        r = check_skill_links(youk, claude)
        assert r["unlinked"] == []
        assert r["runtime_count"] == 1

    def test_broken_symlink_still_counts_as_linked(self, tmp_path):
        """A dangling symlink is a different failure; do not report it as unlinked."""
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        _make_tree(youk, ["verify"])
        runtime_dir = claude / "skills"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "verify").symlink_to(tmp_path / "gone")
        assert check_skill_links(youk, claude)["unlinked"] == []

    def test_top_level_md_files_are_not_skills(self, tmp_path):
        """install.sh also links SKILL-REGISTRY.md and friends. Those are docs."""
        youk, claude = tmp_path / "youk", tmp_path / "claude"
        repo_dir = _make_tree(youk, ["verify"])
        (repo_dir / "SKILL-REGISTRY.md").write_text("# registry")
        runtime_dir = claude / "skills"
        runtime_dir.mkdir(parents=True)
        (runtime_dir / "verify").symlink_to(repo_dir / "verify")
        (runtime_dir / "FOUNDER-GUIDE.md").write_text("# guide")
        r = check_skill_links(youk, claude)
        assert r["unlinked"] == [], "a .md file was counted as a missing skill"
        assert r["orphaned"] == [], "a .md file was counted as an orphan skill"


class TestMissingSkillNameNormalization:
    def test_underscore_spelling_matches_hyphen_skill(self):
        from skill_gen import _normalize_skill_name
        assert _normalize_skill_name("nfr_check") == _normalize_skill_name("nfr-check")

    def test_case_is_folded(self):
        from skill_gen import _normalize_skill_name
        assert _normalize_skill_name("Dev_Loop") == _normalize_skill_name("dev-loop")

    def test_mcp_tool_names_are_excluded(self):
        from skill_gen import _MCP_TOOL_NAMES, _normalize_skill_name
        for tool in ("route_task", "self_heal", "optimize_intent", "assess_skill"):
            assert _normalize_skill_name(tool) in _MCP_TOOL_NAMES

    def test_real_skill_names_are_not_in_the_tool_denylist(self):
        """Guards against the denylist growing to swallow genuine skills."""
        from skill_gen import _MCP_TOOL_NAMES, _normalize_skill_name
        for skill in ("verify", "challenge", "dev-loop", "code-review", "intake"):
            assert _normalize_skill_name(skill) not in _MCP_TOOL_NAMES
