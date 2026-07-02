"""
doc_graph.py — concept coherence for youk's knowledge network.

Reads the `concepts:` block from docs/doc-map.yaml and checks whether
authority files are newer than the derived files that implement each concept.

Uses git log commit timestamps (cross-clone stable). Falls back to mtime
if git is unavailable or the file is not tracked.

Exposed as:
  - load_concept_graph(youk_root)     → list[dict]
  - check_concept_staleness(...)      → list[dict]
  - format_staleness_warnings(stale)  → list[str]

Called by check_doc_graph() MCP tool and wired into _check_doc_freshness()
in session.py so concept drift surfaces at session_start automatically.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git_commit_time(file_path: Path) -> float | None:
    """Return the UNIX commit timestamp for file_path's most recent commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(file_path)],
            capture_output=True, text=True, timeout=3,
            cwd=file_path.parent,
        )
        raw = result.stdout.strip()
        if raw:
            return float(raw)
    except Exception:
        pass
    return None


def _file_age(file_path: Path) -> float | None:
    """
    Staleness proxy for file_path. Prefers git commit timestamp (stable across
    clones); falls back to mtime if git log returns nothing or errors.
    Returns None when the file doesn't exist.
    """
    if not file_path.exists():
        return None
    ts = _git_commit_time(file_path)
    if ts is not None:
        return ts
    return file_path.stat().st_mtime


def _resolve(raw_path: str, youk_root: Path, claude_root: Path) -> Path:
    """
    Resolve a path string from doc-map.yaml to an absolute Path.
    Paths beginning with '~/.claude/' map to claude_root.
    All others are relative to youk_root.
    """
    if raw_path.startswith("~/.claude/"):
        return claude_root / raw_path[len("~/.claude/"):]
    return youk_root / raw_path


def load_concept_graph(youk_root: Path) -> list[dict]:
    """
    Read the `concepts:` block from docs/doc-map.yaml.
    Returns [] if the section is absent or the file doesn't exist.
    """
    doc_map_file = youk_root / "docs" / "doc-map.yaml"
    if not doc_map_file.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(doc_map_file.read_text()) or {}
        return data.get("concepts", []) or []
    except Exception:
        return []


def check_concept_staleness(
    concepts: list[dict],
    youk_root: Path,
    claude_root: Path,
) -> list[dict]:
    """
    For each concept, compare authority file age vs each derived file.
    If authority is NEWER than a derived file → the derived file needs review.

    Returns list of {concept, authority, stale_in, description} dicts.
    Skips gracefully when authority or derived files don't exist.
    """
    stale: list[dict] = []
    for c in concepts:
        authority_raw = c.get("authority", "")
        derived_raw = c.get("derived_in", []) or []
        concept_name = c.get("concept", "")
        description = c.get("description", "")

        authority_path = _resolve(authority_raw, youk_root, claude_root)
        authority_age = _file_age(authority_path)
        if authority_age is None:
            continue  # authority file missing — skip

        stale_in: list[str] = []
        for d_raw in derived_raw:
            derived_path = _resolve(d_raw, youk_root, claude_root)
            derived_age = _file_age(derived_path)
            if derived_age is None:
                continue  # derived file missing — skip
            if authority_age > derived_age:
                stale_in.append(d_raw)

        if stale_in:
            stale.append({
                "concept": concept_name,
                "authority": authority_raw,
                "stale_in": stale_in,
                "description": description,
            })

    return stale


def format_staleness_warnings(stale: list[dict], cap: int = 2) -> list[str]:
    """
    Format stale concept results as actionable session_plan strings.
    Capped at `cap` items to avoid flooding session_plan.
    """
    warnings: list[str] = []
    for item in stale[:cap]:
        stale_files = ", ".join(item["stale_in"][:2])
        warnings.append(
            f"Concept '{item['concept']}' may be stale in {stale_files} — "
            f"authority ({item['authority']}) was updated more recently. "
            "Run check_doc_graph() or update derived files."
        )
    return warnings
