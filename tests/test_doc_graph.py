"""Tests for doc_graph.py — four-check concept coherence."""
from __future__ import annotations
import time
import os
from pathlib import Path
import pytest
import yaml


@pytest.fixture
def tmp_youk(tmp_path):
    """Minimal youk tree with docs/ directory."""
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def tmp_claude(tmp_path):
    """Simulated ~/.claude root."""
    claude = tmp_path / "claude"
    claude.mkdir()
    return claude


def _write_doc_map(youk_root: Path, data: dict) -> None:
    (youk_root / "docs" / "doc-map.yaml").write_text(yaml.dump(data))


def _write_concepts(youk_root: Path, concepts: list[dict]) -> None:
    _write_doc_map(youk_root, {"concepts": concepts})


def _touch(path: Path, mtime_offset: float = 0) -> Path:
    """Create file and set its mtime to now + offset."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("content")
    now = time.time()
    os.utime(path, (now + mtime_offset, now + mtime_offset))
    return path


class TestLoadConceptGraph:
    def test_returns_empty_when_no_file(self, tmp_youk):
        from doc_graph import load_concept_graph
        assert load_concept_graph(tmp_youk) == []

    def test_returns_empty_when_no_concepts_key(self, tmp_youk):
        (tmp_youk / "docs" / "doc-map.yaml").write_text("mcp_tools: {}")
        from doc_graph import load_concept_graph
        assert load_concept_graph(tmp_youk) == []

    def test_returns_concepts_list(self, tmp_youk):
        _write_concepts(tmp_youk, [
            {"concept": "north_star", "authority": "PRD.md", "derived_in": ["README.md"]},
        ])
        from doc_graph import load_concept_graph
        concepts = load_concept_graph(tmp_youk)
        assert len(concepts) == 1
        assert concepts[0]["concept"] == "north_star"


class TestCheckConceptStaleness:
    """Tests for timestamp drift check (Check 1)."""

    def test_authority_newer_returns_stale(self, tmp_youk, tmp_claude):
        auth = _touch(tmp_youk / "README.md", mtime_offset=-100)
        derived = _touch(tmp_youk / "docs" / "guide.md", mtime_offset=-200)
        # Make authority newer than derived
        os.utime(auth, (time.time(), time.time()))

        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c1", "authority": "README.md", "derived_in": ["docs/guide.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(result["stale"]) == 1
        assert "docs/guide.md" in result["stale"][0]["stale_in"]

    def test_derived_newer_no_stale(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "README.md", mtime_offset=-200)
        _touch(tmp_youk / "docs" / "guide.md", mtime_offset=0)

        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c2", "authority": "README.md", "derived_in": ["docs/guide.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["stale"] == []

    def test_no_concepts_returns_empty_dict(self, tmp_youk, tmp_claude):
        from doc_graph import check_concept_staleness
        result = check_concept_staleness([], tmp_youk, tmp_claude)
        assert result == {"stale": [], "broken": [], "orphaned": [], "semantic": []}

    def test_claude_root_path_resolved(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "PRD.md", mtime_offset=0)
        _touch(tmp_claude / "CLAUDE.md", mtime_offset=-200)

        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c5", "authority": "PRD.md", "derived_in": ["~/.claude/CLAUDE.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(result["stale"]) == 1
        assert "~/.claude/CLAUDE.md" in result["stale"][0]["stale_in"]


class TestBrokenLinks:
    """Tests for Check 2: derived file listed but not on disk."""

    def test_missing_derived_returns_broken(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md")
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "auth.md", "derived_in": ["docs/missing.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(result["broken"]) == 1
        assert "docs/missing.md" in result["broken"][0]["missing_derived"]

    def test_broken_not_counted_as_stale(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md")
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "auth.md", "derived_in": ["docs/gone.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["stale"] == []
        assert len(result["broken"]) == 1

    def test_existing_derived_not_flagged_as_broken(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md", mtime_offset=-200)
        _touch(tmp_youk / "docs" / "guide.md", mtime_offset=0)
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "auth.md", "derived_in": ["docs/guide.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["broken"] == []


class TestOrphanedConcepts:
    """Tests for Check 3: authority file listed but not on disk."""

    def test_missing_authority_returns_orphaned(self, tmp_youk, tmp_claude):
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "no-such-file.md", "derived_in": [], "description": "x"}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(result["orphaned"]) == 1
        assert result["orphaned"][0]["concept"] == "c"
        assert result["orphaned"][0]["authority"] == "no-such-file.md"

    def test_orphaned_not_in_stale_or_broken(self, tmp_youk, tmp_claude):
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "ghost.md", "derived_in": ["docs/x.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["stale"] == []
        assert result["broken"] == []
        assert len(result["orphaned"]) == 1

    def test_existing_authority_not_orphaned(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "PRD.md")
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "PRD.md", "derived_in": [], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["orphaned"] == []


class TestInvariantMatch:
    """Tests for Check 4: invariant string must appear in all derived files."""

    def test_invariant_absent_returns_semantic(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md")
        derived = tmp_youk / "docs" / "guide.md"
        derived.parent.mkdir(parents=True, exist_ok=True)
        derived.write_text("This file does not contain the required token.")

        from doc_graph import check_concept_staleness
        concepts = [{
            "concept": "c",
            "authority": "auth.md",
            "derived_in": ["docs/guide.md"],
            "invariant": "capability_skill_rate",
            "description": "",
        }]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(result["semantic"]) == 1
        assert result["semantic"][0]["invariant"] == "capability_skill_rate"
        assert "docs/guide.md" in result["semantic"][0]["missing_in"]

    def test_invariant_present_no_semantic_flag(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md")
        derived = tmp_youk / "docs" / "guide.md"
        derived.parent.mkdir(parents=True, exist_ok=True)
        derived.write_text("The capability_skill_rate is the primary org_score driver.")

        from doc_graph import check_concept_staleness
        concepts = [{
            "concept": "c",
            "authority": "auth.md",
            "derived_in": ["docs/guide.md"],
            "invariant": "capability_skill_rate",
            "description": "",
        }]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["semantic"] == []

    def test_no_invariant_field_skips_check(self, tmp_youk, tmp_claude):
        _touch(tmp_youk / "auth.md", mtime_offset=-200)
        derived = tmp_youk / "docs" / "guide.md"
        derived.parent.mkdir(parents=True, exist_ok=True)
        derived.write_text("anything at all")
        os.utime(derived, (time.time(), time.time()))

        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c", "authority": "auth.md", "derived_in": ["docs/guide.md"], "description": ""}]
        result = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert result["semantic"] == []


class TestFindUntrackedDocs:
    """Tests for untracked docs scanner."""

    def test_untracked_doc_returned(self, tmp_youk):
        (tmp_youk / "docs" / "orphan.md").write_text("not in map")
        _write_doc_map(tmp_youk, {"concepts": []})
        from doc_graph import load_doc_map, find_untracked_docs
        doc_map = load_doc_map(tmp_youk)
        untracked = find_untracked_docs(tmp_youk, doc_map)
        assert "docs/orphan.md" in untracked

    def test_referenced_doc_not_flagged(self, tmp_youk):
        (tmp_youk / "docs" / "guide.md").write_text("referenced")
        _write_doc_map(tmp_youk, {
            "concepts": [{"concept": "c", "authority": "auth.md", "derived_in": ["docs/guide.md"]}]
        })
        from doc_graph import load_doc_map, find_untracked_docs
        doc_map = load_doc_map(tmp_youk)
        untracked = find_untracked_docs(tmp_youk, doc_map)
        assert "docs/guide.md" not in untracked

    def test_empty_docs_dir_returns_empty(self, tmp_youk):
        _write_doc_map(tmp_youk, {})
        from doc_graph import load_doc_map, find_untracked_docs
        doc_map = load_doc_map(tmp_youk)
        assert find_untracked_docs(tmp_youk, doc_map) == []

    def test_mcp_tool_ref_counts_as_tracked(self, tmp_youk):
        (tmp_youk / "docs" / "guide.md").write_text("ref'd via mcp tool")
        _write_doc_map(tmp_youk, {
            "mcp_tools": {"youk-core": [{"tool": "session_start", "refs": ["docs/guide.md"]}]}
        })
        from doc_graph import load_doc_map, find_untracked_docs
        doc_map = load_doc_map(tmp_youk)
        untracked = find_untracked_docs(tmp_youk, doc_map)
        assert "docs/guide.md" not in untracked

    def test_nonexistent_docs_dir_returns_empty(self, tmp_path):
        from doc_graph import find_untracked_docs
        assert find_untracked_docs(tmp_path / "no-such-dir", {}) == []


class TestFormatStalenessWarnings:
    """Formatting layer — handles both legacy list and new dict result."""

    def test_formats_stale_warning(self):
        from doc_graph import format_staleness_warnings
        result = {"stale": [{"concept": "north_star", "authority": "PRD.md", "stale_in": ["README.md"], "description": "x"}],
                  "broken": [], "orphaned": [], "semantic": []}
        warnings = format_staleness_warnings(result)
        assert any("north_star" in w for w in warnings)

    def test_formats_broken_link_as_error(self):
        from doc_graph import format_staleness_warnings
        result = {"stale": [], "broken": [{"concept": "c", "authority": "a.md", "missing_derived": ["docs/gone.md"]}],
                  "orphaned": [], "semantic": []}
        warnings = format_staleness_warnings(result)
        assert any("ERROR" in w and "gone.md" in w for w in warnings)

    def test_formats_orphaned_as_error(self):
        from doc_graph import format_staleness_warnings
        result = {"stale": [], "broken": [], "orphaned": [{"concept": "c", "authority": "ghost.md", "description": ""}],
                  "semantic": []}
        warnings = format_staleness_warnings(result)
        assert any("ERROR" in w and "ghost.md" in w for w in warnings)

    def test_formats_semantic_drift(self):
        from doc_graph import format_staleness_warnings
        result = {"stale": [], "broken": [], "orphaned": [],
                  "semantic": [{"concept": "c", "authority": "a.md", "invariant": "my_token", "missing_in": ["docs/x.md"]}]}
        warnings = format_staleness_warnings(result)
        assert any("SEMANTIC" in w and "my_token" in w for w in warnings)

    def test_legacy_list_input_still_works(self):
        from doc_graph import format_staleness_warnings
        stale = [{"concept": "c", "authority": "a.md", "stale_in": ["docs/x.md"], "description": ""}]
        warnings = format_staleness_warnings(stale)
        assert len(warnings) == 1

    def test_cap_limits_total_output(self):
        from doc_graph import format_staleness_warnings
        result = {
            "stale": [{"concept": f"c{i}", "authority": "a.md", "stale_in": [f"d{i}.md"], "description": ""} for i in range(5)],
            "broken": [], "orphaned": [], "semantic": [],
        }
        warnings = format_staleness_warnings(result, cap=2)
        assert len(warnings) == 2

    def test_empty_result_returns_empty(self):
        from doc_graph import format_staleness_warnings
        assert format_staleness_warnings({"stale": [], "broken": [], "orphaned": [], "semantic": []}) == []
