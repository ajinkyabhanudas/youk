"""Shared file index — SQLite FTS5 (BM25) across all projects.

Schema
------
file_index     : (project_slug, file_path) PRIMARY KEY, plus metadata + semantic units
                 for BM25 retrieval and impact analysis.
file_relations : directed edge table — (from_project, from_path, to_path, rel_type, weight).
                 rel_types: doc_link (markdown href), doc_map_ref (doc-map.yaml refs:),
                 config_ref (YAML/TOML path value), import (code → module).

Key design choices:
- Composite (project_slug, file_path) prevents collision when two projects share a name.
- FTS5 virtual table over symbols + imports + headings gives BM25 without embedding cost.
- file_hash-based skip makes index_project() safe to call at every session_start.
- find_affected() uses the imports column for reverse-lookup (legacy; also promoted to edges).
- file_relations edge table enables: what docs reference this file, what this file links to,
  and unified code↔doc bridging via find_related_docs().
- Zero infrastructure: one shared file at knowledge/shared-index.db, no always-on server.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, "/shared")

YOUK_ROOT = Path("/youk")
_INDEX_DB = YOUK_ROOT / "knowledge" / "shared-index.db"

_DDL = """
CREATE TABLE IF NOT EXISTS file_index (
    project_slug    TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    file_hash       TEXT NOT NULL DEFAULT '',
    last_indexed    TEXT NOT NULL DEFAULT '',
    symbols         TEXT NOT NULL DEFAULT '',
    imports         TEXT NOT NULL DEFAULT '',
    headings        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_slug, file_path)
);

CREATE VIRTUAL TABLE IF NOT EXISTS file_fts USING fts5(
    project_slug UNINDEXED,
    file_path UNINDEXED,
    symbols,
    imports,
    headings,
    content='file_index',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS file_index_ai AFTER INSERT ON file_index BEGIN
    INSERT INTO file_fts(rowid, project_slug, file_path, symbols, imports, headings)
    VALUES (new.rowid, new.project_slug, new.file_path, new.symbols, new.imports, new.headings);
END;

CREATE TRIGGER IF NOT EXISTS file_index_ad AFTER DELETE ON file_index BEGIN
    INSERT INTO file_fts(file_fts, rowid, project_slug, file_path, symbols, imports, headings)
    VALUES ('delete', old.rowid, old.project_slug, old.file_path, old.symbols, old.imports, old.headings);
END;

CREATE TRIGGER IF NOT EXISTS file_index_au AFTER UPDATE ON file_index BEGIN
    INSERT INTO file_fts(file_fts, rowid, project_slug, file_path, symbols, imports, headings)
    VALUES ('delete', old.rowid, old.project_slug, old.file_path, old.symbols, old.imports, old.headings);
    INSERT INTO file_fts(rowid, project_slug, file_path, symbols, imports, headings)
    VALUES (new.rowid, new.project_slug, new.file_path, new.symbols, new.imports, new.headings);
END;

CREATE TABLE IF NOT EXISTS file_relations (
    from_project    TEXT NOT NULL,
    from_path       TEXT NOT NULL,
    to_path         TEXT NOT NULL,
    rel_type        TEXT NOT NULL,
    weight          REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (from_project, from_path, to_path, rel_type)
);

CREATE INDEX IF NOT EXISTS file_relations_to ON file_relations (to_path);
CREATE INDEX IF NOT EXISTS file_relations_from ON file_relations (from_project, from_path);
"""

# File extensions worth indexing, by type
_CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".c", ".cpp", ".h"}
_DOC_EXTS = {".md", ".rst", ".txt"}
_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".json", ".env.example"}
_ALL_EXTS = _CODE_EXTS | _DOC_EXTS | _CONFIG_EXTS

# Directories that are never worth indexing
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env", ".env",
    "dist", "build", ".next", ".nuxt", "target", "vendor",
}

# Max file size to index (bytes) — skip large generated files
_MAX_FILE_BYTES = 256 * 1024  # 256 KB


class _DB:
    """Context manager that opens, initialises, and closes the shared SQLite index."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> sqlite3.Connection:
        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_DDL)
        self._conn.commit()
        return self._conn

    def __exit__(self, *args: object) -> None:
        if self._conn is not None:
            try:
                self._conn.commit()
            except Exception:
                pass
            self._conn.close()
            self._conn = None


def _connect(db_path: Path = _INDEX_DB) -> _DB:
    return _DB(db_path)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    """SHA1 of file content — used for hash-skip on unchanged files."""
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def _extract_python(text: str) -> tuple[str, str]:
    """Extract (symbols, imports) from Python source via AST. Falls back to regex."""
    symbols: list[str] = []
    imports: list[str] = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                symbols.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
    except SyntaxError:
        # Regex fallback for partial/invalid files
        symbols = re.findall(r"^(?:def|class|async def)\s+(\w+)", text, re.MULTILINE)
        imports = re.findall(r"^(?:import|from)\s+(\w+)", text, re.MULTILINE)
    return " ".join(dict.fromkeys(symbols)), " ".join(dict.fromkeys(imports))


def _extract_typescript(text: str) -> tuple[str, str]:
    """Extract (symbols, imports) from TypeScript/JavaScript via regex."""
    symbols = re.findall(
        r"(?:export\s+)?(?:function|class|const|let|var|type|interface|enum)\s+(\w+)",
        text,
    )
    imports = re.findall(r"""(?:import|require)\s*\(?['"]([^'"]+)['"]""", text)
    # Normalise imports: take first path segment, strip relative markers
    norm_imports = [i.lstrip("./").split("/")[0] for i in imports if i]
    return " ".join(dict.fromkeys(symbols)), " ".join(dict.fromkeys(norm_imports))


def _extract_go(text: str) -> tuple[str, str]:
    """Extract (symbols, imports) from Go source via regex."""
    symbols = re.findall(r"^func\s+(?:\([^)]+\)\s+)?(\w+)", text, re.MULTILINE)
    imports = re.findall(r'"([^"]+)"', text)
    # Go imports are full paths; take last segment as the common name
    norm_imports = [i.split("/")[-1] for i in imports if "/" in i or not i.startswith(".")]
    return " ".join(dict.fromkeys(symbols)), " ".join(dict.fromkeys(norm_imports))


def _extract_headings(text: str) -> str:
    """Extract markdown headings from .md/.rst files."""
    headings = re.findall(r"^#{1,4}\s+(.+)", text, re.MULTILINE)
    return " ".join(h.strip() for h in headings[:20])


def _extract_doc_links(text: str, file_path: str) -> list[tuple[str, str]]:
    """Extract outbound file links from markdown: [label](path) and ![label](path).

    Returns list of (to_path, rel_type) where to_path is normalised relative to
    the project root (same form as file_index.file_path). External URLs (http/https/#)
    and anchor-only links are dropped.
    """
    raw = re.findall(r"!?\[(?:[^\]]*)\]\(([^)]+)\)", text)
    base_dir = Path(file_path).parent
    results: list[tuple[str, str]] = []
    for href in raw:
        href = href.split("#")[0].strip()  # drop fragment
        if not href or href.startswith(("http://", "https://", "mailto:")):
            continue
        # Resolve relative to the file's directory within the project
        resolved = (base_dir / href).as_posix()
        # Normalise: strip leading "./" and collapse ".." segments naively
        parts = []
        for part in resolved.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in (".", ""):
                parts.append(part)
        to_path = "/".join(parts)
        if to_path:
            results.append((to_path, "doc_link"))
    return results


def _extract_config_refs(text: str, suffix: str) -> list[tuple[str, str]]:
    """Extract file-path references from YAML/TOML values.

    Looks for string values that end with a known file extension and contain
    at least one path separator or start with a known prefix (servers/, docs/, etc.).
    Returns list of (to_path, "config_ref").
    """
    _FILE_EXT_PATTERN = re.compile(
        r"""['"]([^'"]+\.(?:py|ts|tsx|js|go|rs|md|rst|yaml|yml|toml|json|sh|txt))['"]\s*[,\]\}\n]"""
    )
    _PATH_MARKERS = ("servers/", "docs/", "scripts/", "skills/", "config/", "tests/", "knowledge/")
    results: list[tuple[str, str]] = []
    if suffix not in {".yaml", ".yml", ".toml", ".json"}:
        return results
    for m in _FILE_EXT_PATTERN.finditer(text):
        val = m.group(1).strip()
        if "/" in val or any(val.startswith(p) for p in _PATH_MARKERS):
            results.append((val, "config_ref"))
    return results


def _load_docmap_edges(project_dir: Path) -> list[tuple[str, str, str, str]]:
    """Read docs/doc-map.yaml and emit relation edges.

    Returns list of (from_path, to_path, rel_type, weight) where:
    - from_path is the tool/file/skill entry (normalised)
    - to_path is each entry in its refs: list
    - rel_type is always "doc_map_ref"
    - weight is 2.0 (explicit declaration is higher-confidence than extracted link)

    Silent-fails if doc-map.yaml absent or malformed.
    """
    try:
        import yaml
    except ImportError:
        return []

    docmap = project_dir / "docs" / "doc-map.yaml"
    if not docmap.exists():
        return []

    try:
        data = yaml.safe_load(docmap.read_text()) or {}
    except Exception:
        return []

    edges: list[tuple[str, str, str, str]] = []

    # mcp_tools: {server: [{tool: name, refs: [...]}]}
    for _server, entries in (data.get("mcp_tools") or {}).items():
        for entry in (entries or []):
            tool = entry.get("tool", "")
            for ref in (entry.get("refs") or []):
                # from_path = synthetic "servers/…/server.py#tool_name" — use actual ref as anchor
                edges.append((ref, f"tool:{tool}", "doc_map_ref", 2.0))

    # src_files: [{file: path, refs: [...]}]
    for entry in (data.get("src_files") or []):
        src = entry.get("file", "")
        for ref in (entry.get("refs") or []):
            if src and ref:
                edges.append((src, ref, "doc_map_ref", 2.0))
                edges.append((ref, src, "doc_map_ref", 2.0))  # bidirectional for src↔doc

    # skills: [{skill: name, refs: [...]}]
    for entry in (data.get("skills") or []):
        skill = entry.get("skill", "")
        for ref in (entry.get("refs") or []):
            skill_path = f"skills/{skill}/SKILL.md"
            if ref:
                edges.append((skill_path, ref, "doc_map_ref", 2.0))

    return edges


def _upsert_relations(
    conn: sqlite3.Connection,
    from_project: str,
    from_path: str,
    edges: list[tuple[str, str]],  # (to_path, rel_type)
    weight: float = 1.0,
) -> int:
    """Insert/replace relation edges for a single source file. Returns count inserted."""
    if not edges:
        return 0
    conn.executemany(
        """INSERT OR REPLACE INTO file_relations
           (from_project, from_path, to_path, rel_type, weight)
           VALUES (?, ?, ?, ?, ?)""",
        [(from_project, from_path, to_path, rel_type, weight) for to_path, rel_type in edges],
    )
    return len(edges)


def _extract_semantic_units(path: Path) -> tuple[str, str, str, str]:
    """Return (summary, symbols, imports, headings) for a file."""
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return "", "", "", ""

    ext = path.suffix.lower()
    symbols = imports = headings = ""

    if ext == ".py":
        symbols, imports = _extract_python(text)
    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        symbols, imports = _extract_typescript(text)
    elif ext == ".go":
        symbols, imports = _extract_go(text)
    elif ext in _DOC_EXTS:
        headings = _extract_headings(text)
    # Config files: no symbol extraction, path + headings sufficient

    # Summary: first non-empty, non-comment line (≤120 chars)
    summary = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*", "---")):
            summary = stripped[:120]
            break

    return summary, symbols, imports, headings


# ---------------------------------------------------------------------------
# Git dirty-bit: only re-index changed files
# ---------------------------------------------------------------------------

def _git_dirty_paths(project_dir: Path) -> set[str] | None:
    """Return set of relative paths changed since HEAD, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = result.stdout.splitlines() + staged.stdout.splitlines()
        return {ln.strip() for ln in lines if ln.strip()}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def index_project(
    project_dir: str | Path,
    project_slug: str,
    force: bool = False,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Walk project_dir and upsert semantic units into the shared index.

    Incremental: files whose file_hash matches the stored hash are skipped.
    When force=False and git is available, only dirty files from `git diff HEAD`
    are re-examined (others compared by hash for safety).

    Returns {"indexed": int, "skipped": int, "total_files": int, "project_slug": str}
    """
    from datetime import datetime as _dt, UTC as _UTC

    project_path = Path(project_dir)
    if not project_path.exists():
        return {"indexed": 0, "skipped": 0, "total_files": 0, "project_slug": project_slug,
                "error": f"project_dir not found: {project_dir}"}

    # force=True: bypass all skip logic (dirty-bit and hash)
    dirty_paths = None if force else _git_dirty_paths(project_path)
    now = _dt.now(_UTC).isoformat()

    # Load existing hashes for this project to enable hash-skip (not needed when force)
    existing_hashes: dict[str, str] = {}
    if not force:
        with _connect(db_path) as conn:
            rows = conn.execute(
                "SELECT file_path, file_hash FROM file_index WHERE project_slug = ?",
                (project_slug,),
            ).fetchall()
            existing_hashes = {r["file_path"]: r["file_hash"] for r in rows}

    indexed = 0
    skipped = 0
    total = 0

    with _connect(db_path) as conn:
        for file_path in project_path.rglob("*"):
            if file_path.is_dir():
                continue
            if any(part in _SKIP_DIRS for part in file_path.parts):
                continue
            if file_path.suffix.lower() not in _ALL_EXTS:
                continue
            try:
                if file_path.stat().st_size > _MAX_FILE_BYTES:
                    continue
            except Exception:
                continue

            total += 1
            rel = str(file_path.relative_to(project_path))

            if not force:
                # Dirty-bit fast path: git says file is clean → check hash
                if dirty_paths is not None and rel not in dirty_paths:
                    stored_hash = existing_hashes.get(rel, "")
                    if stored_hash and stored_hash == _file_hash(file_path):
                        skipped += 1
                        continue

                # Hash-only path when git is unavailable
                if dirty_paths is None:
                    current_hash = _file_hash(file_path)
                    if existing_hashes.get(rel) == current_hash:
                        skipped += 1
                        continue

            current_hash = _file_hash(file_path)
            summary, symbols, imports, headings = _extract_semantic_units(file_path)

            # DELETE + INSERT rather than ON CONFLICT UPDATE so that FTS5 triggers
            # fire on both paths (UPDATE-branch of ON CONFLICT bypasses AFTER DELETE).
            conn.execute(
                "DELETE FROM file_index WHERE project_slug = ? AND file_path = ?",
                (project_slug, rel),
            )
            conn.execute(
                """INSERT INTO file_index
                   (project_slug, file_path, summary, file_hash, last_indexed,
                    symbols, imports, headings)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (project_slug, rel, summary, current_hash, now,
                 symbols, imports, headings),
            )

            # Extract and upsert outbound relations for this file.
            # Wipe stale edges from a prior index of this file first.
            conn.execute(
                "DELETE FROM file_relations WHERE from_project = ? AND from_path = ?",
                (project_slug, rel),
            )
            edges: list[tuple[str, str]] = []
            try:
                text = file_path.read_text(errors="replace")
                if file_path.suffix.lower() in _DOC_EXTS:
                    edges.extend(_extract_doc_links(text, rel))
                if file_path.suffix.lower() in _CONFIG_EXTS:
                    edges.extend(_extract_config_refs(text, file_path.suffix.lower()))
                # Promote import-based relations into the edge table (mirrors find_affected logic)
                if imports:
                    for imp in imports.split():
                        edges.append((imp, "import"))  # to_path = module stem (resolved later)
            except Exception:
                pass
            _upsert_relations(conn, project_slug, rel, edges)

            indexed += 1

        # After walking all files, load explicit doc-map edges (authoritative declarations).
        # These supplement extracted edges with higher-weight, manually maintained links.
        docmap_raw = _load_docmap_edges(project_path)
        if docmap_raw:
            conn.executemany(
                """INSERT OR REPLACE INTO file_relations
                   (from_project, from_path, to_path, rel_type, weight)
                   VALUES (?, ?, ?, ?, ?)""",
                [(project_slug, fp, tp, rt, w) for fp, tp, rt, w in docmap_raw],
            )

        conn.commit()

    return {
        "indexed": indexed,
        "skipped": skipped,
        "total_files": total,
        "project_slug": project_slug,
    }


def find_relevant(
    query: str,
    project_slug: str | None = None,
    limit: int = 10,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """BM25 search over indexed files.

    project_slug filters to a single project; None searches across all projects.
    Returns top-N results with attribution (project_slug + file_path).

    Results from the current project are boosted: returned first, then other projects.
    """
    if not query.strip():
        return {"results": [], "query": query, "total": 0}

    # Sanitise FTS5 query: strip special characters that break the parser
    safe_query = re.sub(r'[^\w\s]', ' ', query).strip()
    if not safe_query:
        return {"results": [], "query": query, "total": 0}

    with _connect(db_path) as conn:
        try:
            if project_slug:
                # Boost current project: run twice, current project first then rest
                rows = conn.execute(
                    """SELECT fi.project_slug, fi.file_path, fi.summary,
                              fi.symbols, fi.imports, fi.headings,
                              bm25(file_fts) AS score
                       FROM file_fts
                       JOIN file_index fi ON fi.rowid = file_fts.rowid
                       WHERE file_fts MATCH ? AND fi.project_slug = ?
                       ORDER BY score
                       LIMIT ?""",
                    (safe_query, project_slug, limit),
                ).fetchall()
                # Fill remainder from other projects
                if len(rows) < limit:
                    others = conn.execute(
                        """SELECT fi.project_slug, fi.file_path, fi.summary,
                                  fi.symbols, fi.imports, fi.headings,
                                  bm25(file_fts) AS score
                           FROM file_fts
                           JOIN file_index fi ON fi.rowid = file_fts.rowid
                           WHERE file_fts MATCH ? AND fi.project_slug != ?
                           ORDER BY score
                           LIMIT ?""",
                        (safe_query, project_slug, limit - len(rows)),
                    ).fetchall()
                    rows = list(rows) + list(others)
            else:
                rows = conn.execute(
                    """SELECT fi.project_slug, fi.file_path, fi.summary,
                              fi.symbols, fi.imports, fi.headings,
                              bm25(file_fts) AS score
                       FROM file_fts
                       JOIN file_index fi ON fi.rowid = file_fts.rowid
                       WHERE file_fts MATCH ?
                       ORDER BY score
                       LIMIT ?""",
                    (safe_query, limit),
                ).fetchall()
        except sqlite3.OperationalError:
            return {"results": [], "query": query, "total": 0, "error": "fts_query_failed"}

    results = [
        {
            "project_slug": r["project_slug"],
            "file_path": r["file_path"],
            "summary": r["summary"],
            "score": round(r["score"], 4),
        }
        for r in rows
    ]
    return {"results": results, "query": query, "total": len(results)}


def find_affected(
    file_path: str,
    project_slug: str,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Return files that import or reference the given file.

    Searches for the file's stem (module name) in other files' imports column.
    Used for impact analysis: "what breaks if I change this file?"

    Returns {"affected": list of {project_slug, file_path, summary}, "source_file": str}
    """
    stem = Path(file_path).stem  # e.g. "session" from "servers/core/src/session.py"

    with _connect(db_path) as conn:
        # Files that import this module by stem name.
        # imports column is space-separated (e.g. "os pathlib json" or single "main").
        # Match stem as whole word using space-padded LIKE on a padded column.
        rows = conn.execute(
            """SELECT project_slug, file_path, summary
               FROM file_index
               WHERE (' ' || imports || ' ') LIKE ?
                 AND NOT (project_slug = ? AND file_path = ?)
               ORDER BY project_slug, file_path
               LIMIT 50""",
            (f"% {stem} %", project_slug, file_path),
        ).fetchall()

    affected = [
        {"project_slug": r["project_slug"], "file_path": r["file_path"], "summary": r["summary"]}
        for r in rows
    ]
    return {
        "source_file": file_path,
        "project_slug": project_slug,
        "module_stem": stem,
        "affected": affected,
        "affected_count": len(affected),
    }


def find_stale_relations(
    project_slug: str | None = None,
    db_path: Path = _INDEX_DB,
    limit: int = 20,
) -> dict[str, Any]:
    """Graph-driven staleness: walk file_relations and flag derived files whose source
    was re-indexed more recently than they were.

    This replaces the hand-maintained 13-entry doc-map.yaml staleness list with the full
    file_relations graph (all indexed links). For each relation (from_path -> to_path),
    if the authority/source (from_path) has a newer last_indexed than the derived doc
    (to_path), the derived doc is a staleness candidate — the source changed, the doc may
    not have followed. Uses last_indexed (updated on each re-index when file_hash changes)
    as the freshness signal; both endpoints must be indexed to compare.

    project_slug: restrict to one project's relations, or None for all.
    Returns {"stale": [{from_path, to_path, rel_type, source_indexed, derived_indexed,
             project_slug}], "checked": int, "stale_count": int}
    """
    project_clause = ""
    params: tuple = ()
    if project_slug is not None:
        project_clause = " WHERE r.from_project = ?"
        params = (project_slug,)

    with _connect(db_path) as conn:
        # Join each relation to its two endpoints' last_indexed timestamps.
        # A relation is stale when the source endpoint is newer than the derived endpoint.
        rows = conn.execute(
            f"""
            SELECT r.from_project AS project_slug, r.from_path, r.to_path, r.rel_type,
                   src.last_indexed AS source_indexed,
                   dst.last_indexed AS derived_indexed
            FROM file_relations r
            JOIN file_index src
              ON src.project_slug = r.from_project AND src.file_path = r.from_path
            JOIN file_index dst
              ON dst.project_slug = r.from_project AND dst.file_path = r.to_path
            {project_clause}
            """,
            params,
        ).fetchall()

    checked = len(rows)
    stale = []
    for r in rows:
        src_t = r["source_indexed"]
        dst_t = r["derived_indexed"]
        if src_t is None or dst_t is None:
            continue
        if src_t > dst_t:
            stale.append(
                {
                    "project_slug": r["project_slug"],
                    "from_path": r["from_path"],
                    "to_path": r["to_path"],
                    "rel_type": r["rel_type"],
                    "source_indexed": src_t,
                    "derived_indexed": dst_t,
                }
            )

    # Most-recently-diverged first (by how new the source is), capped.
    # last_indexed is an ISO-8601 string — lexical order equals chronological order.
    stale.sort(key=lambda s: s["source_indexed"], reverse=True)
    return {
        "stale": stale[:limit],
        "checked": checked,
        "stale_count": len(stale),
    }


def find_relations(
    file_path: str,
    project_slug: str,
    direction: str = "both",
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """Return explicit relation edges for a file from the file_relations table.

    direction: "out" = what this file links to; "in" = what links to this file;
               "both" = union of both directions.

    Each result includes: file_path, rel_type, weight, and direction.
    Results are sorted by weight descending, then file_path.

    Use this to answer:
    - "What docs reference session.py?" → direction="in"
    - "What does guardrails.md link to?" → direction="out"
    - "Full relation neighbourhood of this file?" → direction="both" (default)
    """
    if direction not in ("in", "out", "both"):
        return {"error": f"invalid direction '{direction}' — must be in/out/both", "relations": []}

    if not db_path.exists():
        return {"file_path": file_path, "relations": [], "total": 0}

    with _connect(db_path) as conn:
        outbound: list[dict] = []
        inbound: list[dict] = []

        if direction in ("out", "both"):
            rows = conn.execute(
                """SELECT to_path, rel_type, weight
                   FROM file_relations
                   WHERE from_project = ? AND from_path = ?
                   ORDER BY weight DESC, to_path""",
                (project_slug, file_path),
            ).fetchall()
            outbound = [
                {"file_path": r["to_path"], "rel_type": r["rel_type"],
                 "weight": r["weight"], "direction": "out"}
                for r in rows
            ]

        if direction in ("in", "both"):
            rows = conn.execute(
                """SELECT from_path, rel_type, weight
                   FROM file_relations
                   WHERE from_project = ? AND to_path = ?
                   ORDER BY weight DESC, from_path""",
                (project_slug, file_path),
            ).fetchall()
            inbound = [
                {"file_path": r["from_path"], "rel_type": r["rel_type"],
                 "weight": r["weight"], "direction": "in"}
                for r in rows
            ]

    all_relations = outbound + inbound
    return {
        "file_path": file_path,
        "project_slug": project_slug,
        "direction": direction,
        "relations": all_relations,
        "total": len(all_relations),
        "outbound_count": len(outbound),
        "inbound_count": len(inbound),
    }


def find_related_docs(
    query: str,
    project_slug: str | None = None,
    limit: int = 8,
    db_path: Path = _INDEX_DB,
) -> dict[str, Any]:
    """BM25 search that bridges code files and non-code docs via the relation graph.

    Runs BM25 search, then for each result follows relation edges one hop to surface
    related files of the opposite type (code→doc, doc→code). Returns two ranked lists:
    - related_code: code files relevant to the query or linked from matching docs
    - related_docs: doc/config files relevant to the query or linked from matching code

    This lets you ask questions like:
    - "What docs explain route_task?" → BM25 hits server.py + edges find README + doc-map
    - "What code implements the NFR gate?" → BM25 hits docs + edges find session.py + nfr.py
    - "What is connected to guardrails?" → surfaces both the YAML and the docs that reference it

    query: natural language or symbol name
    project_slug: if set, boosts current-project results first
    limit: max results per bucket (code and docs each capped separately)
    """
    if not query.strip():
        return {"related_code": [], "related_docs": [], "query": query, "total": 0}

    _DOC_SUFFIXES = {".md", ".rst", ".txt"}
    _CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb"}
    _CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".json"}

    def _classify(path: str) -> str:
        s = Path(path).suffix.lower()
        if s in _CODE_SUFFIXES:
            return "code"
        if s in _DOC_SUFFIXES:
            return "doc"
        if s in _CONFIG_SUFFIXES:
            return "config"
        return "other"

    # Step 1: BM25 search — broader limit to give relation expansion material
    bm25 = find_relevant(query, project_slug=project_slug, limit=limit * 2, db_path=db_path)
    bm25_results = bm25.get("results", [])

    seen: set[str] = set()
    code_results: list[dict] = []
    doc_results: list[dict] = []

    def _add(entry: dict, source: str) -> None:
        key = f"{entry.get('project_slug','')}:{entry['file_path']}"
        if key in seen:
            return
        seen.add(key)
        kind = _classify(entry["file_path"])
        item = {**entry, "source": source}
        if kind == "code":
            code_results.append(item)
        else:
            doc_results.append(item)

    # Step 2: classify direct BM25 hits
    for r in bm25_results:
        _add(r, "bm25")

    # Step 3: one-hop relation expansion — for each BM25 hit, follow edges to opposite type
    if db_path.exists():
        with _connect(db_path) as conn:
            for r in bm25_results:
                fp = r["file_path"]
                slug = r.get("project_slug") or project_slug or ""
                kind = _classify(fp)

                # Outbound edges from this file
                out_rows = conn.execute(
                    """SELECT to_path, rel_type, weight
                       FROM file_relations
                       WHERE from_project = ? AND from_path = ?
                       ORDER BY weight DESC LIMIT 10""",
                    (slug, fp),
                ).fetchall()

                # Inbound edges pointing to this file
                in_rows = conn.execute(
                    """SELECT from_path, rel_type, weight
                       FROM file_relations
                       WHERE from_project = ? AND to_path = ?
                       ORDER BY weight DESC LIMIT 10""",
                    (slug, fp),
                ).fetchall()

                for row in list(out_rows) + list(in_rows):
                    neighbor = row[0]  # to_path or from_path
                    neighbor_kind = _classify(neighbor)
                    # Only expand to opposite type — code→doc or doc→code
                    if (kind == "code" and neighbor_kind != "code") or \
                       (kind != "code" and neighbor_kind == "code"):
                        # Fetch summary from file_index if available
                        summary_row = conn.execute(
                            "SELECT summary FROM file_index WHERE project_slug = ? AND file_path = ?",
                            (slug, neighbor),
                        ).fetchone()
                        neighbor_entry = {
                            "project_slug": slug,
                            "file_path": neighbor,
                            "summary": summary_row["summary"] if summary_row else "",
                            "score": round(r.get("score", 0.0) * float(row[2]) * 0.5, 4),
                        }
                        _add(neighbor_entry, f"relation:{row[1]}")

    # Sort each bucket: bm25 hits first (lower BM25 score = better), then relation hits
    def _sort_key(item: dict) -> tuple:
        return (0 if item["source"] == "bm25" else 1, item.get("score", 0.0))

    code_results.sort(key=_sort_key)
    doc_results.sort(key=_sort_key)

    return {
        "query": query,
        "project_slug": project_slug,
        "related_code": code_results[:limit],
        "related_docs": doc_results[:limit],
        "total": len(code_results[:limit]) + len(doc_results[:limit]),
    }


def get_index_stats(project_slug: str | None = None, db_path: Path = _INDEX_DB) -> dict[str, Any]:
    """Return index health stats: file counts per project, last indexed timestamps."""
    if not db_path.exists():
        return {"status": "absent", "projects": [], "total_files": 0}

    with _connect(db_path) as conn:
        if project_slug:
            rows = conn.execute(
                """SELECT project_slug, COUNT(*) as file_count, MAX(last_indexed) as last_indexed
                   FROM file_index WHERE project_slug = ? GROUP BY project_slug""",
                (project_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT project_slug, COUNT(*) as file_count, MAX(last_indexed) as last_indexed
                   FROM file_index GROUP BY project_slug ORDER BY project_slug""",
            ).fetchall()

        total = conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]

        relation_rows = conn.execute(
            "SELECT rel_type, COUNT(*) as cnt FROM file_relations GROUP BY rel_type"
        ).fetchall()
        relation_summary = {r["rel_type"]: r["cnt"] for r in relation_rows}

    projects = [
        {
            "project_slug": r["project_slug"],
            "file_count": r["file_count"],
            "last_indexed": r["last_indexed"],
        }
        for r in rows
    ]

    return {
        "status": "healthy",
        "projects": projects,
        "total_files": total,
        "relations": relation_summary,
        "total_relations": sum(relation_summary.values()),
    }
