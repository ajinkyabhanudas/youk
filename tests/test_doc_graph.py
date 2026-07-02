"""Tests for doc_graph.py — concept coherence checking."""
from __future__ import annotations
import time
from pathlib import Path
import pytest


@pytest.fixture
def tmp_youk(tmp_path):
    """Minimal youk tree with docs/doc-map.yaml."""
    (tmp_path / "docs").mkdir()
    return tmp_path


@pytest.fixture
def tmp_claude(tmp_path):
    """Simulated ~/.claude root."""
    claude = tmp_path / "claude"
    claude.mkdir()
    return claude


def _write_concepts(youk_root: Path, concepts: list[dict]) -> None:
    import yaml
    dm = {"concepts": concepts}
    (youk_root / "docs" / "doc-map.yaml").write_text(yaml.dump(dm))


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
    def _make_pair(self, tmp_youk, tmp_claude, concept: str, authority_path: str, derived_paths: list[str], authority_older: bool):
        """Create authority + derived files with controlled mtimes."""
        from doc_graph import _resolve
        auth = _resolve(authority_path, tmp_youk, tmp_claude)
        auth.parent.mkdir(parents=True, exist_ok=True)
        auth.write_text("authority content")

        for d in derived_paths:
            dp = _resolve(d, tmp_youk, tmp_claude)
            dp.parent.mkdir(parents=True, exist_ok=True)
            dp.write_text("derived content")

        if authority_older:
            # Authority is older (derived is newer) → no staleness
            import os
            now = time.time()
            os.utime(auth, (now - 100, now - 100))
            for d in derived_paths:
                dp = _resolve(d, tmp_youk, tmp_claude)
                os.utime(dp, (now, now))
        else:
            # Authority is newer → derived is stale
            import os
            now = time.time()
            for d in derived_paths:
                dp = _resolve(d, tmp_youk, tmp_claude)
                os.utime(dp, (now - 100, now - 100))
            os.utime(auth, (now, now))

        return [{
            "concept": concept,
            "authority": authority_path,
            "derived_in": derived_paths,
            "description": "test",
        }]

    def test_authority_newer_returns_stale(self, tmp_youk, tmp_claude):
        """Authority updated after derived → derived is stale."""
        from doc_graph import check_concept_staleness
        concepts = self._make_pair(
            tmp_youk, tmp_claude, "c1",
            "README.md", ["docs/guide.md"],
            authority_older=False,
        )
        stale = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(stale) == 1
        assert "docs/guide.md" in stale[0]["stale_in"]

    def test_derived_newer_no_stale(self, tmp_youk, tmp_claude):
        """Derived updated after authority → nothing stale."""
        from doc_graph import check_concept_staleness
        concepts = self._make_pair(
            tmp_youk, tmp_claude, "c2",
            "README.md", ["docs/guide.md"],
            authority_older=True,
        )
        stale = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert stale == []

    def test_missing_authority_skipped(self, tmp_youk, tmp_claude):
        """Missing authority file → concept skipped gracefully."""
        from doc_graph import check_concept_staleness
        concepts = [{"concept": "c3", "authority": "no-such-file.md", "derived_in": [], "description": ""}]
        stale = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert stale == []

    def test_missing_derived_skipped(self, tmp_youk, tmp_claude):
        """Missing derived file → that derived entry skipped gracefully."""
        from doc_graph import check_concept_staleness
        auth = tmp_youk / "auth.md"
        auth.write_text("x")
        concepts = [{"concept": "c4", "authority": "auth.md", "derived_in": ["no-such-derived.md"], "description": ""}]
        stale = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        # Authority exists, derived missing → skip derived → no stale result
        assert stale == []

    def test_claude_root_path_resolved(self, tmp_youk, tmp_claude):
        """~/.claude/ prefix resolves to claude_root."""
        from doc_graph import check_concept_staleness
        import os
        auth = tmp_youk / "PRD.md"
        auth.write_text("x")
        claude_file = tmp_claude / "CLAUDE.md"
        claude_file.write_text("y")
        now = time.time()
        os.utime(auth, (now, now))
        os.utime(claude_file, (now - 200, now - 200))
        concepts = [{
            "concept": "c5",
            "authority": "PRD.md",
            "derived_in": ["~/.claude/CLAUDE.md"],
            "description": "",
        }]
        stale = check_concept_staleness(concepts, tmp_youk, tmp_claude)
        assert len(stale) == 1
        assert "~/.claude/CLAUDE.md" in stale[0]["stale_in"]

    def test_no_concepts_returns_empty(self, tmp_youk, tmp_claude):
        from doc_graph import check_concept_staleness
        assert check_concept_staleness([], tmp_youk, tmp_claude) == []


class TestFormatStalenessWarnings:
    def test_formats_warning_string(self):
        from doc_graph import format_staleness_warnings
        stale = [{"concept": "north_star", "authority": "PRD.md", "stale_in": ["README.md"], "description": "x"}]
        warnings = format_staleness_warnings(stale)
        assert len(warnings) == 1
        assert "north_star" in warnings[0]
        assert "README.md" in warnings[0]

    def test_cap_limits_output(self):
        from doc_graph import format_staleness_warnings
        stale = [
            {"concept": f"c{i}", "authority": f"auth{i}.md", "stale_in": [f"d{i}.md"], "description": ""}
            for i in range(5)
        ]
        warnings = format_staleness_warnings(stale, cap=2)
        assert len(warnings) == 2

    def test_empty_stale_returns_empty(self):
        from doc_graph import format_staleness_warnings
        assert format_staleness_warnings([]) == []
