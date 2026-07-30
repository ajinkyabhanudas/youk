"""Concept graph — cross-session semantic memory in shared-index.db.

Schema (additive — never modifies existing tables):
    concepts      : (id, label, type, project_slug, session_n, created_at, summary)
    concept_edges : (from_id, to_id, edge_type, weight, source_session)

Population:
    extract_concepts(patterns, domain_knowledge, project_slug, session_n) → concept dicts
    write_concepts(concepts, edges, db_path) → {"written": int, "edges_written": int}

Query:
    query_concept_graph(query, project_slug=None, limit=5, db_path) → top-N concepts
    by label substring match, extended with direct neighbors via edge traversal.

Design:
- INSERT OR IGNORE on uniqueness constraints makes all writes idempotent.
- Regular SQLite tables (not FTS5) — graph traversal via recursive CTEs, not BM25.
- Silent-fail on every DB operation — never blocks /learn.
- WAL mode set by _DB from file_index.py (shared connection helper reused).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

YOUK_ROOT = Path("/youk")
_INDEX_DB = YOUK_ROOT / "knowledge" / "shared-index.db"

_DDL = """
CREATE TABLE IF NOT EXISTS concepts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT    NOT NULL,
    type         TEXT    NOT NULL DEFAULT 'concept',
    project_slug TEXT    NOT NULL,
    session_n    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL,
    summary      TEXT    NOT NULL DEFAULT '',
    UNIQUE (label, project_slug, session_n)
);

CREATE INDEX IF NOT EXISTS concepts_label    ON concepts (label);
CREATE INDEX IF NOT EXISTS concepts_project  ON concepts (project_slug);

CREATE TABLE IF NOT EXISTS concept_edges (
    from_id        INTEGER NOT NULL REFERENCES concepts(id),
    to_id          INTEGER NOT NULL REFERENCES concepts(id),
    edge_type      TEXT    NOT NULL DEFAULT 'related',
    weight         REAL    NOT NULL DEFAULT 1.0,
    source_session INTEGER NOT NULL DEFAULT 0,
    UNIQUE (from_id, to_id, edge_type)
);

CREATE INDEX IF NOT EXISTS edges_from ON concept_edges (from_id);
CREATE INDEX IF NOT EXISTS edges_to   ON concept_edges (to_id);
"""

# Concept types derived from /learn output sections
_TYPE_MAP: dict[str, str] = {
    "pattern": "pattern",
    "contract": "contract",
    "decision": "decision",
    "nfr": "nfr",
    "domain": "domain",
    "skill": "skill",
}


def _connect(db_path: Path = _INDEX_DB) -> sqlite3.Connection:
    """Open shared-index.db, ensure WAL + concept-graph DDL applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_DDL)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _clean_label(raw: str) -> str:
    """Normalise a raw heading or phrase into a compact label (≤60 chars)."""
    label = re.sub(r"[^a-zA-Z0-9 _\-/]", "", raw).strip()
    return label[:60] if label else ""


def _infer_type(section_key: str) -> str:
    for k, v in _TYPE_MAP.items():
        if k in section_key.lower():
            return v
    return "concept"


def extract_concepts(
    patterns: list[str],
    domain_knowledge: list[str],
    project_slug: str,
    session_n: int,
) -> list[dict[str, Any]]:
    """Convert /learn output fields into concept dicts ready for write_concepts().

    Only extracts from structured lists — never from free-form prose — so
    signal-to-noise stays high without an LLM call.

    Returns list of {"label", "type", "project_slug", "session_n", "summary"}.
    """
    concepts: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(UTC).isoformat()

    def _add(raw: str, concept_type: str, summary: str = "") -> None:
        label = _clean_label(raw)
        if not label or label.lower() in seen:
            return
        seen.add(label.lower())
        concepts.append({
            "label": label,
            "type": concept_type,
            "project_slug": project_slug,
            "session_n": session_n,
            "created_at": now,
            "summary": summary[:200],
        })

    for p in patterns or []:
        if isinstance(p, str) and p.strip():
            _add(p.strip(), "pattern")

    for d in domain_knowledge or []:
        if isinstance(d, str) and d.strip():
            _add(d.strip(), "domain")

    return concepts


def _cooccurrence_edges(
    concepts: list[dict[str, Any]],
    session_n: int,
) -> list[tuple[str, str, str, float]]:
    """Emit (label_a, label_b, edge_type, weight) pairs for same-session co-occurrence.

    Only pairs concepts of the same type within a single session — cross-type
    edges would be noise at this stage.
    """
    edges: list[tuple[str, str, str, float]] = []
    by_type: dict[str, list[str]] = {}
    for c in concepts:
        by_type.setdefault(c["type"], []).append(c["label"])

    for ctype, labels in by_type.items():
        for i, a in enumerate(labels):
            for b in labels[i + 1 :]:
                edges.append((a, b, f"co_{ctype}", 1.0))
    return edges


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_concepts(
    concepts: list[dict[str, Any]],
    project_slug: str,
    session_n: int,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Upsert concepts into shared-index.db and emit co-occurrence edges.

    Idempotent: INSERT OR IGNORE on (label, project_slug, session_n) and
    (from_id, to_id, edge_type).

    Returns {"written": int, "edges_written": int, "project_slug": str}.
    """
    if not concepts:
        return {"written": 0, "edges_written": 0, "project_slug": project_slug}

    written = 0
    edges_written = 0

    try:
        conn = _connect(db_path)
        try:
            for c in concepts:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO concepts
                       (label, type, project_slug, session_n, created_at, summary)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (c["label"], c["type"], c["project_slug"],
                     c["session_n"], c["created_at"], c["summary"]),
                )
                if cursor.rowcount:
                    written += 1

            conn.commit()

            # Build co-occurrence edges from newly inserted concepts
            raw_edges = _cooccurrence_edges(concepts, session_n)
            for label_a, label_b, edge_type, weight in raw_edges:
                row_a = conn.execute(
                    "SELECT id FROM concepts WHERE label = ? AND project_slug = ?",
                    (label_a, project_slug),
                ).fetchone()
                row_b = conn.execute(
                    "SELECT id FROM concepts WHERE label = ? AND project_slug = ?",
                    (label_b, project_slug),
                ).fetchone()
                if row_a and row_b:
                    cursor = conn.execute(
                        """INSERT OR IGNORE INTO concept_edges
                           (from_id, to_id, edge_type, weight, source_session)
                           VALUES (?, ?, ?, ?, ?)""",
                        (row_a["id"], row_b["id"], edge_type, weight, session_n),
                    )
                    if cursor.rowcount:
                        edges_written += 1

            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Never block /learn on DB errors
        pass

    return {"written": written, "edges_written": edges_written, "project_slug": project_slug}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def query_concept_graph(
    query: str,
    project_slug: str | None = None,
    limit: int = 5,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Find concepts matching query label (substring) + their direct neighbors.

    project_slug=None searches across all projects.
    Returns top-N seed matches extended with one hop of neighbors, deduplicated.

    Returns {"concepts": list[dict], "query": str, "total": int}.
    """
    if not query.strip():
        return {"concepts": [], "query": query, "total": 0}

    if not db_path.exists():
        return {"concepts": [], "query": query, "total": 0, "note": "index not yet built"}

    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    try:
        conn = _connect(db_path)
        try:
            pattern = f"%{query.strip().lower()}%"

            if project_slug:
                seeds = conn.execute(
                    """SELECT id, label, type, project_slug, session_n, summary
                       FROM concepts
                       WHERE lower(label) LIKE ? AND project_slug = ?
                       ORDER BY session_n DESC
                       LIMIT ?""",
                    (pattern, project_slug, limit),
                ).fetchall()
            else:
                seeds = conn.execute(
                    """SELECT id, label, type, project_slug, session_n, summary
                       FROM concepts
                       WHERE lower(label) LIKE ?
                       ORDER BY session_n DESC
                       LIMIT ?""",
                    (pattern, limit),
                ).fetchall()

            for row in seeds:
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    results.append({
                        "label": row["label"],
                        "type": row["type"],
                        "project_slug": row["project_slug"],
                        "session_n": row["session_n"],
                        "summary": row["summary"],
                        "match": "direct",
                    })

            # One-hop neighbors: concepts connected to any seed
            if seen_ids and len(results) < limit * 2:
                placeholders = ",".join("?" * len(seen_ids))
                neighbors = conn.execute(
                    f"""SELECT c.id, c.label, c.type, c.project_slug, c.session_n, c.summary,
                               e.edge_type
                        FROM concept_edges e
                        JOIN concepts c ON c.id = e.to_id
                        WHERE e.from_id IN ({placeholders})
                        UNION
                        SELECT c.id, c.label, c.type, c.project_slug, c.session_n, c.summary,
                               e.edge_type
                        FROM concept_edges e
                        JOIN concepts c ON c.id = e.from_id
                        WHERE e.to_id IN ({placeholders})
                        ORDER BY session_n DESC
                        LIMIT ?""",
                    (*seen_ids, *seen_ids, limit),
                ).fetchall()

                for row in neighbors:
                    if row["id"] not in seen_ids:
                        seen_ids.add(row["id"])
                        results.append({
                            "label": row["label"],
                            "type": row["type"],
                            "project_slug": row["project_slug"],
                            "session_n": row["session_n"],
                            "summary": row["summary"],
                            "match": f"neighbor:{row['edge_type']}",
                        })
        finally:
            conn.close()
    except Exception:
        return {"concepts": [], "query": query, "total": 0, "error": "query_failed"}

    return {"concepts": results[:limit * 2], "query": query, "total": len(results)}


def get_concept_stats(
    project_slug: str | None = None,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Return concept graph health: concept counts per project, total edges."""
    if not db_path.exists():
        return {"status": "absent", "projects": [], "total_concepts": 0, "total_edges": 0}

    try:
        conn = _connect(db_path)
        try:
            if project_slug:
                rows = conn.execute(
                    """SELECT project_slug, COUNT(*) as concept_count
                       FROM concepts WHERE project_slug = ? GROUP BY project_slug""",
                    (project_slug,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT project_slug, COUNT(*) as concept_count
                       FROM concepts GROUP BY project_slug ORDER BY project_slug""",
                ).fetchall()

            total_c = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
            total_e = conn.execute("SELECT COUNT(*) FROM concept_edges").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return {"status": "error", "projects": [], "total_concepts": 0, "total_edges": 0}

    projects = [
        {"project_slug": r["project_slug"], "concept_count": r["concept_count"]}
        for r in rows
    ]
    return {
        "status": "healthy",
        "projects": projects,
        "total_concepts": total_c,
        "total_edges": total_e,
    }
