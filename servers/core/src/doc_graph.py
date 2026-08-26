"""
doc_graph.py — concept coherence for youk's knowledge network.

Four structural checks on docs/doc-map.yaml:

1. Timestamp drift   — authority file committed more recently than a derived file
2. Broken links      — derived file listed in doc-map.yaml no longer exists on disk
3. Orphaned concepts — authority file listed in doc-map.yaml no longer exists on disk
4. Untracked docs    — .md files in docs/ not referenced anywhere in doc-map.yaml
5. Invariant match   — optional per-concept string that must appear in all derived files

Uses git log commit timestamps (cross-clone stable). Falls back to mtime
if git is unavailable or the file is not tracked.

Exposed as:
  - load_concept_graph(youk_root)              → list[dict]
  - check_concept_staleness(...)               → dict with stale, broken, orphaned keys
  - find_untracked_docs(youk_root, doc_map)    → list[str]
  - format_staleness_warnings(result)          → list[str]

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


def _all_referenced_paths(doc_map: dict) -> set[str]:
    """Collect every file path referenced anywhere in the doc-map (derived_in + authority + refs)."""
    paths: set[str] = set()
    for concept in doc_map.get("concepts", []) or []:
        auth = concept.get("authority", "")
        if auth and not auth.startswith("~/.claude/"):
            paths.add(auth)
        for d in concept.get("derived_in", []) or []:
            if not d.startswith("~/.claude/"):
                paths.add(d)

    for _server, tools in (doc_map.get("mcp_tools") or {}).items():
        for entry in (tools or []):
            for ref in (entry.get("refs") or []):
                if not ref.startswith("~/.claude/"):
                    paths.add(ref)

    for entry in (doc_map.get("src_files") or []):
        for ref in (entry.get("refs") or []):
            if not ref.startswith("~/.claude/"):
                paths.add(ref)

    for entry in (doc_map.get("skills") or []):
        for ref in (entry.get("refs") or []):
            if not ref.startswith("~/.claude/"):
                paths.add(ref)

    return paths


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


def load_doc_map(youk_root: Path) -> dict:
    """Load the full doc-map.yaml. Returns {} on any error."""
    doc_map_file = youk_root / "docs" / "doc-map.yaml"
    if not doc_map_file.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(doc_map_file.read_text()) or {}
    except Exception:
        return {}


def find_untracked_docs(youk_root: Path, doc_map: dict) -> list[str]:
    """
    Scan docs/*.md for files not referenced anywhere in doc-map.yaml.
    Returns relative paths (from youk_root) of untracked files.
    """
    docs_dir = youk_root / "docs"
    if not docs_dir.exists():
        return []

    referenced = _all_referenced_paths(doc_map)
    untracked = []
    for md_file in sorted(docs_dir.glob("*.md")):
        rel = str(md_file.relative_to(youk_root))
        if rel not in referenced:
            untracked.append(rel)
    return untracked


def check_concept_staleness(
    concepts: list[dict],
    youk_root: Path,
    claude_root: Path,
) -> dict:
    """
    Four-check structural audit of the concept graph.

    Returns dict with:
      stale    — list of {concept, authority, stale_in, description}
                 (authority newer than derived file by timestamp)
      broken   — list of {concept, authority, missing_derived}
                 (derived file listed but not on disk)
      orphaned — list of {concept, authority}
                 (authority file listed but not on disk)
      semantic — list of {concept, authority, invariant, missing_in}
                 (invariant string absent from derived file)

    Callers that previously expected a list[dict] for stale concepts
    should use result["stale"]. The format_staleness_warnings() function
    accepts the full dict and formats all four check types.
    """
    stale: list[dict] = []
    broken: list[dict] = []
    orphaned: list[dict] = []
    semantic: list[dict] = []

    for c in concepts:
        authority_raw = c.get("authority", "")
        derived_raw = c.get("derived_in", []) or []
        concept_name = c.get("concept", "")
        description = c.get("description", "")
        invariant = c.get("invariant", "")

        authority_path = _resolve(authority_raw, youk_root, claude_root)

        # Check 3: orphaned concept (authority missing)
        if not authority_path.exists():
            orphaned.append({
                "concept": concept_name,
                "authority": authority_raw,
                "description": description,
            })
            continue

        authority_age = _file_age(authority_path)

        stale_in: list[str] = []
        missing_derived: list[str] = []
        semantic_missing: list[str] = []

        for d_raw in derived_raw:
            derived_path = _resolve(d_raw, youk_root, claude_root)

            # Check 2: broken link (derived file missing)
            if not derived_path.exists():
                missing_derived.append(d_raw)
                continue

            derived_age = _file_age(derived_path)

            # Check 1: timestamp drift
            if authority_age is not None and derived_age is not None:
                if authority_age > derived_age:
                    stale_in.append(d_raw)

            # Check 4: invariant match
            if invariant:
                try:
                    content = derived_path.read_text(encoding="utf-8", errors="replace")
                    if invariant not in content:
                        semantic_missing.append(d_raw)
                except Exception:
                    pass

        if stale_in:
            stale.append({
                "concept": concept_name,
                "authority": authority_raw,
                "stale_in": stale_in,
                "description": description,
            })

        if missing_derived:
            broken.append({
                "concept": concept_name,
                "authority": authority_raw,
                "missing_derived": missing_derived,
            })

        if semantic_missing:
            semantic.append({
                "concept": concept_name,
                "authority": authority_raw,
                "invariant": invariant,
                "missing_in": semantic_missing,
            })

    return {
        "stale": stale,
        "broken": broken,
        "orphaned": orphaned,
        "semantic": semantic,
    }


def format_staleness_warnings(result: dict | list, cap: int = 2) -> list[str]:
    """
    Format audit results as actionable session_plan strings.
    Accepts either the new dict result or the legacy list[dict] (stale only).
    Capped at `cap` items total to avoid flooding session_plan.
    """
    warnings: list[str] = []

    # Legacy callers pass a list of stale dicts directly.
    if isinstance(result, list):
        stale = result
        broken = orphaned = semantic = []
    else:
        stale = result.get("stale", [])
        broken = result.get("broken", [])
        orphaned = result.get("orphaned", [])
        semantic = result.get("semantic", [])

    for item in orphaned[:cap]:
        warnings.append(
            f"[ERROR] Concept '{item['concept']}' authority file missing: "
            f"{item['authority']} — remove or update this concept in docs/doc-map.yaml."
        )
        if len(warnings) >= cap:
            return warnings

    for item in broken[:cap]:
        missing = ", ".join(item["missing_derived"][:2])
        warnings.append(
            f"[ERROR] Concept '{item['concept']}' has broken derived links: "
            f"{missing} — file(s) deleted or moved. Update docs/doc-map.yaml."
        )
        if len(warnings) >= cap:
            return warnings

    for item in semantic[:cap]:
        missing = ", ".join(item["missing_in"][:2])
        warnings.append(
            f"[SEMANTIC] Concept '{item['concept']}' invariant '{item['invariant']}' "
            f"absent from: {missing} — derived file may describe old behavior."
        )
        if len(warnings) >= cap:
            return warnings

    for item in stale[:cap]:
        stale_files = ", ".join(item["stale_in"][:2])
        warnings.append(
            f"Concept '{item['concept']}' may be stale in {stale_files} — "
            f"authority ({item['authority']}) was updated more recently. "
            "Run check_doc_graph() or update derived files."
        )
        if len(warnings) >= cap:
            return warnings

    return warnings
