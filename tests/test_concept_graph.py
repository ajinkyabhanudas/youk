"""Tests for ADR-007 concept graph — concepts + concept_edges in shared-index.db.

All functions imported directly from concept_graph.py (no MCP dependency).
Each test uses a tmp_path-scoped db_path so tests are fully isolated.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from concept_graph import (
    _connect,
    _clean_label,
    extract_concepts,
    write_concepts,
    query_concept_graph,
    get_concept_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> Path:
    """Return a fresh db_path with schema applied."""
    db = tmp_path / "shared-index.db"
    conn = _connect(db)
    conn.close()
    return db


def _row_count(db: Path, table: str) -> int:
    conn = sqlite3.connect(str(db))
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    conn.close()
    return n


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_concepts_table_exists(self, tmp_path):
        db = _make_db(tmp_path)
        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "concepts" in tables

    def test_concept_edges_table_exists(self, tmp_path):
        db = _make_db(tmp_path)
        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "concept_edges" in tables

    def test_concepts_unique_constraint(self, tmp_path):
        db = _make_db(tmp_path)
        conn = _connect(db)
        conn.execute(
            "INSERT INTO concepts (label, type, project_slug, session_n, created_at, summary) "
            "VALUES ('auth', 'concept', 'youk', 1, '2026-07-28T00:00:00', '')"
        )
        conn.commit()
        # Second insert same triple must be ignored, not error
        conn.execute(
            "INSERT OR IGNORE INTO concepts (label, type, project_slug, session_n, created_at, summary) "
            "VALUES ('auth', 'concept', 'youk', 1, '2026-07-28T00:00:00', '')"
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
        conn.close()
        assert n == 1


# ---------------------------------------------------------------------------
# _clean_label
# ---------------------------------------------------------------------------

class TestCleanLabel:
    def test_strips_special_chars(self):
        assert _clean_label("auth → JWT (token)") == "auth  JWT token"

    def test_truncates_at_60(self):
        assert len(_clean_label("x" * 100)) == 60

    def test_empty_returns_empty(self):
        assert _clean_label("") == ""

    def test_only_special_chars_returns_empty(self):
        assert _clean_label("!@#$%") == ""


# ---------------------------------------------------------------------------
# extract_concepts
# ---------------------------------------------------------------------------

class TestExtractConcepts:
    def test_patterns_produce_pattern_type(self):
        concepts = extract_concepts(["BM25 retrieval"], [], "youk", 1)
        assert any(c["type"] == "pattern" for c in concepts)

    def test_domain_produces_domain_type(self):
        concepts = extract_concepts([], ["Dreyfus stages"], "youk", 1)
        assert any(c["type"] == "domain" for c in concepts)

    def test_deduplication_within_call(self):
        concepts = extract_concepts(["auth gate", "auth gate", "auth gate"], [], "youk", 1)
        labels = [c["label"] for c in concepts]
        assert labels.count("auth gate") == 1

    def test_empty_inputs_return_empty(self):
        assert extract_concepts([], [], "youk", 1) == []

    def test_project_slug_propagated(self):
        concepts = extract_concepts(["ZPD probe"], [], "canopy", 5)
        assert all(c["project_slug"] == "canopy" for c in concepts)

    def test_session_n_propagated(self):
        concepts = extract_concepts(["concept graph"], [], "youk", 42)
        assert all(c["session_n"] == 42 for c in concepts)

    def test_blank_strings_excluded(self):
        concepts = extract_concepts(["", "   ", "real pattern"], [], "youk", 1)
        labels = [c["label"] for c in concepts]
        assert "" not in labels
        assert "real pattern" in labels

    def test_created_at_is_set(self):
        concepts = extract_concepts(["something"], [], "youk", 1)
        assert concepts[0]["created_at"]


# ---------------------------------------------------------------------------
# write_concepts
# ---------------------------------------------------------------------------

class TestWriteConcepts:
    def test_writes_concepts_to_db(self, tmp_path):
        db = _make_db(tmp_path)
        concepts = extract_concepts(["BM25 retrieval", "session state"], [], "youk", 1)
        result = write_concepts(concepts, "youk", 1, db_path=db)
        assert result["written"] == 2
        assert _row_count(db, "concepts") == 2

    def test_idempotent_second_write(self, tmp_path):
        db = _make_db(tmp_path)
        concepts = extract_concepts(["auth gate"], [], "youk", 1)
        write_concepts(concepts, "youk", 1, db_path=db)
        result = write_concepts(concepts, "youk", 1, db_path=db)
        assert result["written"] == 0  # all skipped as duplicates
        assert _row_count(db, "concepts") == 1

    def test_cooccurrence_edges_created(self, tmp_path):
        db = _make_db(tmp_path)
        # Two patterns in same session → one edge
        concepts = extract_concepts(["auth gate", "nfr check"], [], "youk", 1)
        result = write_concepts(concepts, "youk", 1, db_path=db)
        assert result["edges_written"] >= 1
        assert _row_count(db, "concept_edges") >= 1

    def test_no_edges_for_single_concept(self, tmp_path):
        db = _make_db(tmp_path)
        concepts = extract_concepts(["only one"], [], "youk", 1)
        result = write_concepts(concepts, "youk", 1, db_path=db)
        assert result["edges_written"] == 0

    def test_empty_concepts_returns_zeros(self, tmp_path):
        db = _make_db(tmp_path)
        result = write_concepts([], "youk", 1, db_path=db)
        assert result["written"] == 0
        assert result["edges_written"] == 0

    def test_returns_project_slug(self, tmp_path):
        db = _make_db(tmp_path)
        result = write_concepts([], "canopy", 1, db_path=db)
        assert result["project_slug"] == "canopy"

    def test_cross_session_same_label_stored_separately(self, tmp_path):
        db = _make_db(tmp_path)
        c1 = extract_concepts(["auth gate"], [], "youk", 1)
        c2 = extract_concepts(["auth gate"], [], "youk", 2)
        write_concepts(c1, "youk", 1, db_path=db)
        write_concepts(c2, "youk", 2, db_path=db)
        assert _row_count(db, "concepts") == 2


# ---------------------------------------------------------------------------
# query_concept_graph
# ---------------------------------------------------------------------------

class TestQueryConceptGraph:
    def _seed(self, tmp_path: Path) -> Path:
        db = _make_db(tmp_path)
        c_youk = extract_concepts(["BM25 retrieval", "session state"], ["Dreyfus stages"], "youk", 1)
        c_canopy = extract_concepts(["RAG pipeline", "medical accuracy"], [], "canopy", 2)
        write_concepts(c_youk, "youk", 1, db_path=db)
        write_concepts(c_canopy, "canopy", 2, db_path=db)
        return db

    def test_direct_match_returned(self, tmp_path):
        db = self._seed(tmp_path)
        result = query_concept_graph("BM25", db_path=db)
        labels = [c["label"] for c in result["concepts"]]
        assert any("BM25" in l for l in labels)

    def test_project_slug_filter(self, tmp_path):
        db = self._seed(tmp_path)
        result = query_concept_graph("a", project_slug="canopy", db_path=db)
        assert all(c["project_slug"] == "canopy" for c in result["concepts"])

    def test_no_filter_returns_cross_project(self, tmp_path):
        db = self._seed(tmp_path)
        result = query_concept_graph("a", db_path=db)
        slugs = {c["project_slug"] for c in result["concepts"]}
        assert len(slugs) >= 2

    def test_empty_query_returns_empty(self, tmp_path):
        db = self._seed(tmp_path)
        result = query_concept_graph("", db_path=db)
        assert result["concepts"] == []

    def test_absent_db_returns_gracefully(self, tmp_path):
        result = query_concept_graph("auth", db_path=tmp_path / "nonexistent.db")
        assert result["concepts"] == []
        assert "note" in result

    def test_neighbor_returned_via_edge(self, tmp_path):
        db = _make_db(tmp_path)
        # Two patterns → co-occurrence edge; query one, neighbor should appear
        concepts = extract_concepts(["alpha concept", "beta concept"], [], "youk", 1)
        write_concepts(concepts, "youk", 1, db_path=db)
        result = query_concept_graph("alpha", db_path=db)
        labels = [c["label"] for c in result["concepts"]]
        # beta should appear as neighbor
        assert any("beta" in l for l in labels)

    def test_total_field_set(self, tmp_path):
        db = self._seed(tmp_path)
        result = query_concept_graph("a", db_path=db)
        assert "total" in result
        assert result["total"] >= 0


# ---------------------------------------------------------------------------
# get_concept_stats
# ---------------------------------------------------------------------------

class TestGetConceptStats:
    def test_absent_db_returns_absent(self, tmp_path):
        result = get_concept_stats(db_path=tmp_path / "none.db")
        assert result["status"] == "absent"

    def test_counts_per_project(self, tmp_path):
        db = _make_db(tmp_path)
        c = extract_concepts(["x", "y", "z"], [], "youk", 1)
        write_concepts(c, "youk", 1, db_path=db)
        result = get_concept_stats(project_slug="youk", db_path=db)
        assert result["total_concepts"] == 3
        assert result["projects"][0]["concept_count"] == 3

    def test_total_edges_counted(self, tmp_path):
        db = _make_db(tmp_path)
        c = extract_concepts(["a", "b", "c"], [], "youk", 1)
        write_concepts(c, "youk", 1, db_path=db)
        result = get_concept_stats(db_path=db)
        # 3 same-type concepts → 3 edges (a-b, a-c, b-c)
        assert result["total_edges"] == 3

    def test_cross_project_totals(self, tmp_path):
        db = _make_db(tmp_path)
        write_concepts(extract_concepts(["p1"], [], "youk", 1), "youk", 1, db_path=db)
        write_concepts(extract_concepts(["p2"], [], "canopy", 1), "canopy", 1, db_path=db)
        result = get_concept_stats(db_path=db)
        assert result["total_concepts"] == 2
        assert len(result["projects"]) == 2
