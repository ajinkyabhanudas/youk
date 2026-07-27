"""Shared file index — SQLite FTS5 (BM25) across all projects.

Schema
------
file_index : (project_slug, file_path) PRIMARY KEY, plus metadata + semantic units
             for BM25 retrieval and impact analysis.

Key design choices:
- Composite (project_slug, file_path) prevents collision when two projects share a name
  (e.g. both have session.py).
- FTS5 virtual table over symbols + imports + headings gives BM25 without embedding cost.
- file_hash-based skip makes index_project() safe to call at every session_start —
  unchanged files are O(1) to skip.
- find_affected() uses the imports column for reverse-lookup impact analysis.
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
            indexed += 1

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

    projects = [
        {
            "project_slug": r["project_slug"],
            "file_count": r["file_count"],
            "last_indexed": r["last_indexed"],
        }
        for r in rows
    ]
    return {"status": "healthy", "projects": projects, "total_files": total}
