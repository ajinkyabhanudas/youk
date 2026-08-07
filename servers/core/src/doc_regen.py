"""Auto-regenerate generated docs when the staleness graph flags them (Task: energize
the link graph to ACT, not just report).

find_stale_relations detects that a derived doc is stale. For docs that are GENERATED from
data (STATS.md from audit data, etc.), the fix is trivial and safe: re-run the generator.
For hand-written prose (PHILOSOPHY.md) or source files (session.py), there is no safe
auto-fix — those stay as human-surfaced warnings. This module closes the loop only for the
generated ones.

THE BOUNDARY (why this is safe): only files in GENERATED_DOCS are ever regenerated, each by
an explicit, known command. youk never rewrites source code or hand-written prose — that
would be the drifted-fix disaster. A stale .py or a stale hand-doc is reported, never touched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

YOUK_ROOT = Path("/youk")

# Registry: generated-doc path (relative to youk root) -> the command that regenerates it.
# ONLY add entries here whose generator is deterministic and writes just that file.
# A doc absent from this registry is treated as hand-written/source — never auto-regenerated.
GENERATED_DOCS: dict[str, list[str]] = {
    "STATS.md": ["python3", "scripts/export_stats.py"],
}


def is_generated(doc_path: str) -> bool:
    """True if doc_path has a registered generator (safe to auto-regenerate)."""
    return doc_path in GENERATED_DOCS


def regenerate_stale_generated_docs(
    stale: list[dict],
    youk_root: Path = YOUK_ROOT,
    dry_run: bool = False,
) -> dict:
    """For each stale relation whose derived file (to_path) is a GENERATED doc, run its
    generator. Reports what it regenerated and what it left for a human.

    stale: the "stale" list from find_stale_relations.
    dry_run: if True, report what WOULD regenerate without running anything.

    Returns {"regenerated": [...], "needs_human": [...], "errors": [...]}.
    """
    regenerated: list[str] = []
    needs_human: list[str] = []
    errors: list[dict] = []
    seen: set[str] = set()

    for s in stale:
        doc = s.get("to_path", "")
        if not doc or doc in seen:
            continue
        seen.add(doc)

        if not is_generated(doc):
            # Source file or hand-written prose — never auto-touch. Surface to human.
            needs_human.append(doc)
            continue

        if dry_run:
            regenerated.append(doc)
            continue

        cmd = GENERATED_DOCS[doc]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(youk_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                regenerated.append(doc)
            else:
                errors.append({"doc": doc, "error": result.stderr[-200:] or "nonzero exit"})
        except Exception as exc:
            errors.append({"doc": doc, "error": str(exc)})

    return {
        "regenerated": regenerated,
        "needs_human": needs_human,
        "errors": errors,
    }
