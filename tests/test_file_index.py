"""Unit tests for file_index.py — shared SQLite file index with BM25 retrieval.

All tests use tmp_path-scoped DB files so they never touch knowledge/shared-index.db.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
for _p in [str(_REPO / "servers" / "shared"), str(_REPO / "servers" / "core" / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import file_index as FI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> Path:
    """Create a minimal project tree for indexing."""
    proj = tmp_path / "myproject"
    proj.mkdir()
    (proj / "main.py").write_text(
        "import os\nimport sys\ndef main():\n    pass\nclass App:\n    pass\n"
    )
    (proj / "utils.py").write_text(
        "from main import App\ndef helper():\n    return 42\n"
    )
    (proj / "README.md").write_text("# My Project\n\n## Overview\n\nA test project.\n")
    sub = proj / "sub"
    sub.mkdir()
    (sub / "service.py").write_text(
        "import main\nclass Service:\n    pass\n"
    )
    return proj


# ---------------------------------------------------------------------------
# index_project
# ---------------------------------------------------------------------------

class TestIndexProject:

    def test_indexes_python_files(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        r = FI.index_project(proj, "myproject", db_path=db)
        assert r["indexed"] >= 3  # main.py, utils.py, sub/service.py
        assert r["project_slug"] == "myproject"
        assert r["total_files"] >= 3

    def test_indexes_markdown_files(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        r = FI.index_project(proj, "myproject", db_path=db)
        assert r["indexed"] >= 4  # 3 .py + 1 .md

    def test_idempotent_second_call_skips_all(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)
        r2 = FI.index_project(proj, "myproject", db_path=db)
        # Second call: all files unchanged → all skipped
        assert r2["indexed"] == 0
        assert r2["skipped"] == r2["total_files"]

    def test_force_reindexes_all(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)
        r2 = FI.index_project(proj, "myproject", force=True, db_path=db)
        assert r2["indexed"] >= 3

    def test_missing_project_dir(self, tmp_path):
        db = tmp_path / "idx.db"
        r = FI.index_project(tmp_path / "does_not_exist", "slug", db_path=db)
        assert "error" in r
        assert r["indexed"] == 0

    def test_two_projects_no_collision(self, tmp_path):
        # Both projects have main.py — composite key keeps them separate
        p1 = tmp_path / "proj1"
        p2 = tmp_path / "proj2"
        p1.mkdir(); p2.mkdir()
        (p1 / "main.py").write_text("def foo(): pass\n")
        (p2 / "main.py").write_text("def bar(): pass\n")
        db = tmp_path / "idx.db"
        FI.index_project(p1, "proj1", db_path=db)
        FI.index_project(p2, "proj2", db_path=db)

        r1 = FI.find_relevant("foo", project_slug="proj1", db_path=db)
        r2 = FI.find_relevant("bar", project_slug="proj2", db_path=db)

        proj1_paths = {x["file_path"] for x in r1["results"] if x["project_slug"] == "proj1"}
        proj2_paths = {x["file_path"] for x in r2["results"] if x["project_slug"] == "proj2"}
        assert "main.py" in proj1_paths
        assert "main.py" in proj2_paths

    def test_skips_node_modules(self, tmp_path):
        proj = tmp_path / "jsproject"
        proj.mkdir()
        (proj / "index.ts").write_text("export function hello() {}")
        nm = proj / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};")
        db = tmp_path / "idx.db"
        r = FI.index_project(proj, "jsproject", db_path=db)
        assert r["indexed"] == 1  # only index.ts, not node_modules content

    def test_skips_large_files(self, tmp_path):
        proj = tmp_path / "bigproject"
        proj.mkdir()
        (proj / "big.py").write_bytes(b"x = 1\n" * 50000)  # > 256KB
        (proj / "small.py").write_text("def ok(): pass\n")
        db = tmp_path / "idx.db"
        r = FI.index_project(proj, "bigproject", db_path=db)
        assert r["indexed"] == 1  # only small.py


# ---------------------------------------------------------------------------
# find_relevant
# ---------------------------------------------------------------------------

class TestFindRelevant:

    def _seed(self, tmp_path: Path) -> Path:
        db = tmp_path / "idx.db"
        proj = _make_project(tmp_path)
        FI.index_project(proj, "myproject", db_path=db)
        return db

    def test_finds_symbol_by_name(self, tmp_path):
        db = self._seed(tmp_path)
        r = FI.find_relevant("App", db_path=db)
        assert r["total"] >= 1
        assert any("main.py" in x["file_path"] for x in r["results"])

    def test_finds_heading_in_markdown(self, tmp_path):
        db = self._seed(tmp_path)
        r = FI.find_relevant("Overview", db_path=db)
        assert r["total"] >= 1
        assert any("README" in x["file_path"] for x in r["results"])

    def test_empty_query_returns_empty(self, tmp_path):
        db = self._seed(tmp_path)
        r = FI.find_relevant("", db_path=db)
        assert r["results"] == []

    def test_project_slug_filter_boosts_current_project(self, tmp_path):
        # Two projects; current-project results come first
        p1 = tmp_path / "proj1"; p1.mkdir()
        p2 = tmp_path / "proj2"; p2.mkdir()
        (p1 / "router.py").write_text("def route(): pass\n")
        (p2 / "router.py").write_text("def route(): pass\n")
        db = tmp_path / "idx.db"
        FI.index_project(p1, "proj1", db_path=db)
        FI.index_project(p2, "proj2", db_path=db)

        r = FI.find_relevant("route", project_slug="proj1", db_path=db)
        # proj1 results must appear before proj2 results
        slugs = [x["project_slug"] for x in r["results"]]
        if "proj1" in slugs and "proj2" in slugs:
            assert slugs.index("proj1") < slugs.index("proj2")

    def test_cross_project_search_when_no_slug(self, tmp_path):
        p1 = tmp_path / "proj1"; p1.mkdir()
        p2 = tmp_path / "proj2"; p2.mkdir()
        (p1 / "a.py").write_text("def unique_func_proj1(): pass\n")
        (p2 / "b.py").write_text("def unique_func_proj2(): pass\n")
        db = tmp_path / "idx.db"
        FI.index_project(p1, "proj1", db_path=db)
        FI.index_project(p2, "proj2", db_path=db)

        r = FI.find_relevant("unique_func", db_path=db)
        slugs = {x["project_slug"] for x in r["results"]}
        assert "proj1" in slugs
        assert "proj2" in slugs

    def test_limit_respected(self, tmp_path):
        proj = tmp_path / "proj"; proj.mkdir()
        for i in range(20):
            (proj / f"mod{i}.py").write_text(f"def func{i}(): pass\n")
        db = tmp_path / "idx.db"
        FI.index_project(proj, "proj", db_path=db)
        r = FI.find_relevant("func", project_slug="proj", limit=5, db_path=db)
        assert len(r["results"]) <= 5

    def test_absent_db_returns_empty(self, tmp_path):
        db = tmp_path / "nonexistent.db"
        r = FI.find_relevant("anything", db_path=db)
        # Empty or error — never crashes
        assert "results" in r


# ---------------------------------------------------------------------------
# find_affected
# ---------------------------------------------------------------------------

class TestFindAffected:

    def test_finds_importer(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)

        # utils.py imports "main"; sub/service.py imports "main"
        r = FI.find_affected("main.py", "myproject", db_path=db)
        file_paths = {x["file_path"] for x in r["affected"]}
        assert "utils.py" in file_paths or "sub/service.py" in file_paths

    def test_excludes_source_file_from_results(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)

        r = FI.find_affected("main.py", "myproject", db_path=db)
        paths = {x["file_path"] for x in r["affected"]}
        assert "main.py" not in paths

    def test_returns_module_stem(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)

        r = FI.find_affected("servers/core/src/session.py", "myproject", db_path=db)
        assert r["module_stem"] == "session"

    def test_no_importers_returns_empty(self, tmp_path):
        proj = tmp_path / "proj"; proj.mkdir()
        (proj / "standalone.py").write_text("def lone(): pass\n")
        db = tmp_path / "idx.db"
        FI.index_project(proj, "proj", db_path=db)

        r = FI.find_affected("standalone.py", "proj", db_path=db)
        assert r["affected"] == []
        assert r["affected_count"] == 0


# ---------------------------------------------------------------------------
# get_index_stats
# ---------------------------------------------------------------------------

class TestGetIndexStats:

    def test_absent_db(self, tmp_path):
        db = tmp_path / "nope.db"
        r = FI.get_index_stats(db_path=db)
        assert r["status"] == "absent"
        assert r["total_files"] == 0

    def test_stats_after_index(self, tmp_path):
        proj = _make_project(tmp_path)
        db = tmp_path / "idx.db"
        FI.index_project(proj, "myproject", db_path=db)
        r = FI.get_index_stats(db_path=db)
        assert r["status"] == "healthy"
        assert r["total_files"] >= 4
        slugs = [p["project_slug"] for p in r["projects"]]
        assert "myproject" in slugs

    def test_per_project_filter(self, tmp_path):
        p1 = tmp_path / "p1"; p1.mkdir()
        p2 = tmp_path / "p2"; p2.mkdir()
        (p1 / "a.py").write_text("x = 1\n")
        (p2 / "b.py").write_text("y = 2\n")
        (p2 / "c.py").write_text("z = 3\n")
        db = tmp_path / "idx.db"
        FI.index_project(p1, "p1", db_path=db)
        FI.index_project(p2, "p2", db_path=db)

        r = FI.get_index_stats(project_slug="p2", db_path=db)
        assert len(r["projects"]) == 1
        assert r["projects"][0]["file_count"] == 2


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

class TestExtractionHelpers:

    def test_extract_python_symbols(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("def foo(): pass\nclass Bar: pass\nasync def baz(): pass\n")
        _, symbols, _, _ = FI._extract_semantic_units(f)
        assert "foo" in symbols
        assert "Bar" in symbols
        assert "baz" in symbols

    def test_extract_python_imports(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("import os\nfrom pathlib import Path\nimport json\n")
        _, _, imports, _ = FI._extract_semantic_units(f)
        assert "os" in imports
        assert "pathlib" in imports
        assert "json" in imports

    def test_extract_markdown_headings(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\n## Section One\n\n### Sub\n\nBody text.\n")
        _, _, _, headings = FI._extract_semantic_units(f)
        assert "Title" in headings
        assert "Section One" in headings

    def test_extract_typescript_symbols(self, tmp_path):
        f = tmp_path / "comp.ts"
        f.write_text(
            "export function greet() {}\nexport class MyService {}\nexport const MAX = 10;\n"
        )
        _, symbols, _, _ = FI._extract_semantic_units(f)
        assert "greet" in symbols
        assert "MyService" in symbols

    def test_handles_invalid_python_gracefully(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def broken(\n  # unclosed\n")
        summary, symbols, imports, headings = FI._extract_semantic_units(f)
        # No crash — returns whatever regex could find
        assert isinstance(symbols, str)

    def test_file_hash_stable(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x = 1\n")
        h1 = FI._file_hash(f)
        h2 = FI._file_hash(f)
        assert h1 == h2
        assert len(h1) == 16

    def test_file_hash_changes_on_content_change(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x = 1\n")
        h1 = FI._file_hash(f)
        f.write_text("x = 2\n")
        h2 = FI._file_hash(f)
        assert h1 != h2
