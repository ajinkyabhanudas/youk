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


def _parse_domain_file(text: str, concept_type: str) -> list[tuple[str, str]]:
    """Parse a structured domain .md file into (label, summary) pairs.

    Domain files have the format:
      ---
      name: slug-label
      description: one-line description
      ---
      ## Section Heading
      *Added: ...*
      *Source: ...*
      **What it is:** first prose sentence...

    Extracts one concept per ## heading (the heading text is the label).
    Summary is the first **What it is:** sentence, or the frontmatter description
    if no headings exist (single-concept files).
    """
    pairs: list[tuple[str, str]] = []

    # Extract frontmatter description as fallback summary
    fm_desc = ""
    fm_match = re.search(r"^---\n.*?description:\s*(.+?)\n.*?---", text, re.DOTALL)
    if fm_match:
        fm_desc = fm_match.group(1).strip()[:200]

    # Find all ## level headings (entry titles) — skip # h1
    heading_pattern = re.compile(r"^#{2,3} (.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(text))

    if not headings:
        # Single-concept file: use frontmatter name + description
        name_match = re.search(r"^---\nname:\s*(.+)$", text, re.MULTILINE)
        if name_match and fm_desc:
            pairs.append((name_match.group(1).strip(), fm_desc))
        return pairs

    for i, h in enumerate(headings):
        label = h.group(1).strip()
        # Skip meta-headings that are structural, not conceptual
        if label.lower() in ("added", "source", "note", "notes", "context"):
            continue
        # Extract block text between this heading and the next
        block_start = h.end()
        block_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[block_start:block_end]

        # Best summary: first "What it is:" sentence
        what_match = re.search(r"\*\*What it is:\*\*\s*(.+?)(?:\n|$)", block)
        if what_match:
            summary = what_match.group(1).strip()[:200]
        else:
            # Fallback: first non-metadata, non-empty line
            summary = ""
            for line in block.splitlines():
                stripped = line.strip().lstrip("*").strip()
                if stripped and not stripped.startswith("Added") and not stripped.startswith("Source"):
                    summary = stripped[:200]
                    break

        pairs.append((label, summary or fm_desc))

    return pairs


def extract_concepts(
    patterns: list[str],
    domain_knowledge: list[str],
    project_slug: str,
    session_n: int,
) -> list[dict[str, Any]]:
    """Convert /learn raw line lists into concept dicts.

    Legacy interface kept for backward compat. Prefer extract_concepts_from_domain_dir
    which parses the structured .md format correctly instead of treating each line
    as a separate concept label.

    Returns list of {"label", "type", "project_slug", "session_n", "summary"}.
    """
    concepts: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(UTC).isoformat()

    def _add(raw: str, concept_type: str, summary: str = "") -> None:
        label = _clean_label(raw)
        # Reject lines that are clearly metadata fragments, not concept labels
        _SKIP_PREFIXES = ("added", "source", "what it is", "analogy", "where the", "project example",
                          "when to reach", "sharper", "rule:", "the ", "a ", "an ", "in ", "note")
        if not label or label.lower() in seen:
            return
        if any(label.lower().startswith(p) for p in _SKIP_PREFIXES):
            return
        if len(label) > 80:  # prose sentence, not a label
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


def extract_concepts_from_domain_dir(
    domain_dir: Path,
    project_slug: str,
    session_n: int,
) -> list[dict[str, Any]]:
    """Parse all domain .md files in domain_dir into concept dicts.

    Uses _parse_domain_file to extract structured (label, summary) pairs
    from the ## heading format — not line-splitting. Produces one concept
    per knowledge entry, not one per prose line.

    Returns list of {"label", "type", "project_slug", "session_n", "summary"}.
    """
    concepts: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(UTC).isoformat()

    if not domain_dir.exists():
        return concepts

    for md_file in domain_dir.glob("*.md"):
        if md_file.name == "gaps.md":
            continue
        try:
            text = md_file.read_text()
        except Exception:
            continue

        # Infer concept type from filename
        concept_type = "pattern" if "pattern" in md_file.name.lower() else "domain"
        pairs = _parse_domain_file(text, concept_type)

        for label_raw, summary in pairs:
            label = _clean_label(label_raw)
            if not label or label.lower() in seen:
                continue
            seen.add(label.lower())
            concepts.append({
                "label": label,
                "type": concept_type,
                "project_slug": project_slug,
                "session_n": session_n,
                "created_at": now,
                "summary": summary[:200],
                "source_file": md_file.name,  # scopes co-occurrence edges to same file
            })

    return concepts


def _cooccurrence_edges(
    concepts: list[dict[str, Any]],
    session_n: int,
) -> list[tuple[str, str, str, float]]:
    """Emit (label_a, label_b, edge_type, weight) pairs for same-file co-occurrence.

    Only pairs concepts that share the same source_file — entries from the same
    knowledge .md file are genuinely related. Cross-file pairing is O(n²) noise:
    68 youk domain concepts would produce 2278 edges making every concept a
    neighbor of every other, defeating the graph query entirely.

    Falls back to same-type pairing (original behaviour) when source_file is absent,
    so the legacy extract_concepts() path still works.
    """
    edges: list[tuple[str, str, str, float]] = []

    # Prefer grouping by source_file — only pair within the same file
    has_source = any(c.get("source_file") for c in concepts)
    if has_source:
        by_file: dict[str, list[tuple[str, str]]] = {}
        for c in concepts:
            key = c.get("source_file") or "__unknown__"
            by_file.setdefault(key, []).append((c["label"], c["type"]))
        for items in by_file.values():
            for i, (a, atype) in enumerate(items):
                for b, btype in items[i + 1:]:
                    edge_type = f"co_{atype}" if atype == btype else "co_related"
                    edges.append((a, b, edge_type, 1.0))
    else:
        # Legacy fallback: pair same-type within session (kept for backward compat)
        by_type: dict[str, list[str]] = {}
        for c in concepts:
            by_type.setdefault(c["type"], []).append(c["label"])
        for ctype, labels in by_type.items():
            for i, a in enumerate(labels):
                for b in labels[i + 1:]:
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
