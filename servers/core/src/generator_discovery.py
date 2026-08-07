"""Auto-discover which docs are GENERATED and by what — so doc auto-regen isn't gated
on a hand-maintained list.

The prior version hard-coded GENERATED_DOCS = {"STATS.md": [...]}. That only self-heals
what a human remembered to register — the same hand-list limitation the staleness detector
originally had. This scans scripts/ and finds, mechanically, which script WRITES which .md
file: a script that calls path.write_text() (or open(...,'w')) on "X.md" IS X.md's generator.

Discovery is deliberately CONSERVATIVE — a false positive means auto-running the wrong script
or classifying prose as generated. A doc is only treated as generated when:
  1. a script provably writes that exact filename, AND
  2. the target file actually exists at the youk root (rules out fragments like "-research.md").
Under-discovering (missing a real generator) is safe — it degrades to a human warning.
Over-discovering is not — so the bar is high.
"""
from __future__ import annotations

import ast
from pathlib import Path

YOUK_ROOT = Path("/youk")


def _md_write_targets(script_path: Path) -> set[str]:
    """Return the set of 'X.md' filenames this script provably writes.

    Recognizes two patterns:
      - VAR = <... / "X.md">  then  VAR.write_text(...)
      - open("X.md", "w")
    Only bare filenames (no '/' or glob) are considered — a path fragment or glob is not
    a generator target.
    """
    try:
        tree = ast.parse(script_path.read_text())
    except Exception:
        return set()

    # Map variable names bound to an .md literal.
    md_vars: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for c in ast.walk(node.value):
                if (
                    isinstance(c, ast.Constant)
                    and isinstance(c.value, str)
                    and c.value.endswith(".md")
                    and "/" not in c.value
                    and "*" not in c.value
                ):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            md_vars[tgt.id] = c.value

    written: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # VAR.write_text(...) / VAR.write_bytes(...)
        if isinstance(f, ast.Attribute) and f.attr in ("write_text", "write_bytes"):
            if isinstance(f.value, ast.Name) and f.value.id in md_vars:
                written.add(md_vars[f.value.id])
        # open("X.md", "w"...)
        if isinstance(f, ast.Name) and f.id == "open" and node.args:
            a0 = node.args[0]
            if (
                isinstance(a0, ast.Constant)
                and isinstance(a0.value, str)
                and a0.value.endswith(".md")
                and "/" not in a0.value
                and "*" not in a0.value
            ):
                written.add(a0.value)
    return written


def discover_generators(youk_root: Path = YOUK_ROOT) -> dict[str, list[str]]:
    """Scan scripts/*.py and return {doc_filename: [python3, script_path]} for every doc
    a script provably writes AND that exists at the youk root.

    The returned dict has the same shape as the old hand-maintained GENERATED_DOCS, so it
    is a drop-in replacement — but self-maintaining. A new generated doc + its script is
    picked up automatically the next time this runs; nothing to register by hand.
    """
    scripts_dir = youk_root / "scripts"
    if not scripts_dir.is_dir():
        return {}

    generators: dict[str, list[str]] = {}
    for script in sorted(scripts_dir.glob("*.py")):
        for doc in _md_write_targets(script):
            # Guard: the doc must actually exist at the youk root (rules out fragments).
            if not (youk_root / doc).exists():
                continue
            # First writer wins; deterministic due to sorted() iteration.
            generators.setdefault(doc, ["python3", f"scripts/{script.name}"])
    return generators
