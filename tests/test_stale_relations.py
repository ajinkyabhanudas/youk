"""Graph-driven staleness — find_stale_relations walks file_relations + file_index
freshness to flag derived files whose source changed more recently.

This replaces the 13-entry hand-maintained doc-map.yaml staleness list with the full
indexed link graph. The bug it fixes: a source file (README, a SKILL.md) is edited but
its derived docs (STATS.md, PHILOSOPHY.md, etc.) are not — and nothing noticed, because
those files were never in the hand-list.
"""
from __future__ import annotations

import sqlite3

from file_index import find_stale_relations


def _seed(db, files, relations):
    """files: list of (project, path, last_indexed). relations: (project, from, to, type)."""
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE file_index (
        project_slug TEXT, file_path TEXT, summary TEXT, file_hash TEXT,
        last_indexed TEXT, symbols TEXT, imports TEXT, headings TEXT,
        PRIMARY KEY (project_slug, file_path))""")
    conn.execute("""CREATE TABLE file_relations (
        from_project TEXT, from_path TEXT, to_path TEXT, rel_type TEXT, weight REAL)""")
    for proj, path, ts in files:
        conn.execute(
            "INSERT INTO file_index (project_slug, file_path, last_indexed) VALUES (?,?,?)",
            (proj, path, ts),
        )
    for proj, frm, to, rtype in relations:
        conn.execute(
            "INSERT INTO file_relations (from_project, from_path, to_path, rel_type, weight) VALUES (?,?,?,?,1.0)",
            (proj, frm, to, rtype),
        )
    conn.commit()
    conn.close()


def test_flags_stale_derived_when_source_newer(tmp_path):
    db = tmp_path / "idx.db"
    _seed(
        db,
        files=[
            ("youk", "README.md", "2026-08-06T16:00:00"),      # source, newer
            ("youk", "STATS.md", "2026-07-27T23:45:53"),        # derived, older -> STALE
        ],
        relations=[("youk", "README.md", "STATS.md", "doc_link")],
    )
    result = find_stale_relations(project_slug="youk", db_path=db)
    assert result["stale_count"] == 1
    assert result["stale"][0]["to_path"] == "STATS.md"
    assert result["stale"][0]["from_path"] == "README.md"


def test_not_stale_when_derived_newer(tmp_path):
    db = tmp_path / "idx.db"
    _seed(
        db,
        files=[
            ("youk", "README.md", "2026-07-01T00:00:00"),      # source, older
            ("youk", "STATS.md", "2026-08-06T00:00:00"),        # derived, newer -> fresh
        ],
        relations=[("youk", "README.md", "STATS.md", "doc_link")],
    )
    result = find_stale_relations(project_slug="youk", db_path=db)
    assert result["stale_count"] == 0


def test_skips_relation_with_unindexed_endpoint(tmp_path):
    """A relation to a file that isn't indexed can't be compared — skipped, not crashed."""
    db = tmp_path / "idx.db"
    _seed(
        db,
        files=[("youk", "README.md", "2026-08-06T00:00:00")],   # only source indexed
        relations=[("youk", "README.md", "GHOST.md", "doc_link")],
    )
    result = find_stale_relations(project_slug="youk", db_path=db)
    assert result["stale_count"] == 0  # GHOST.md not indexed -> not comparable


def test_covers_many_files_not_a_handlist(tmp_path):
    """The whole point: coverage scales with the link graph, not a hand-maintained list."""
    db = tmp_path / "idx.db"
    files = [("youk", "src.md", "2026-08-06T00:00:00")]
    relations = []
    for i in range(10):
        files.append(("youk", f"derived{i}.md", "2026-07-01T00:00:00"))
        relations.append(("youk", "src.md", f"derived{i}.md", "doc_link"))
    _seed(db, files, relations)
    result = find_stale_relations(project_slug="youk", db_path=db)
    assert result["checked"] == 10
    assert result["stale_count"] == 10  # all 10 derived are older than the source


def test_project_scoped(tmp_path):
    db = tmp_path / "idx.db"
    _seed(
        db,
        files=[
            ("youk", "a.md", "2026-08-06T00:00:00"),
            ("youk", "b.md", "2026-07-01T00:00:00"),
            ("canopy", "c.md", "2026-08-06T00:00:00"),
            ("canopy", "d.md", "2026-07-01T00:00:00"),
        ],
        relations=[
            ("youk", "a.md", "b.md", "doc_link"),
            ("canopy", "c.md", "d.md", "doc_link"),
        ],
    )
    youk_only = find_stale_relations(project_slug="youk", db_path=db)
    assert youk_only["stale_count"] == 1
    assert all(s["project_slug"] == "youk" for s in youk_only["stale"])
