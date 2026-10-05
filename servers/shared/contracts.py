"""Which contracts apply: one definition, read by the server, the hooks and the brief.

Before this module the same question was answered four ways. session.py loaded project plus
global (defaults and ranked live learnings), compaction.py loaded project only, the hooks
loaded the first lines of a rendered file, and the session plan printed one global contract
as "Active contract" while the brief said "none saved". Two readers that disagree produce
contradictory briefs and make the repeat-correction metric unreliable.

Sources, in the order they apply:
  knowledge/default-contracts.md           committed, inherited by every install
  state/global-patterns.jsonl              live cross-project learnings, best supported first
    (falls back to knowledge/global/contracts.md, the rendered copy, when there is no store)
  knowledge/projects/{slug}/contracts.md   this project's own agreements

Stdlib plus jsonl_lock only, so hooks can import it.
"""
from __future__ import annotations

import re
from pathlib import Path

from jsonl_lock import locked_jsonl_read_all

DEFAULT_GLOBAL_CAP = 50


def _lines(path: Path) -> list[str]:
    """Contract lines of a markdown file: stripped, no blanks, headings or rules. A missing or
    unreadable file is no contracts, never an error."""
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#") and not line.startswith("---")
        ]
    except OSError:
        return []


def effective_patterns(rows: list[dict]) -> list[dict]:
    """The store is append-only: a later row with the same id supersedes the earlier one
    (retirement appends a copy with status "retired"). Returns the live rows, last row per id,
    retired ones dropped, in first-seen order."""
    latest: dict[str, dict] = {}
    for i, r in enumerate(rows):
        key = r.get("id")
        latest[key if key is not None else f"\x00row{i}"] = r  # id-less rows are each their own
    return [r for r in latest.values() if r.get("status") != "retired"]


def ranked_global_lessons(root: Path, room: int) -> list[str] | None:
    """Live cross-project learnings, best supported first (confirmed count, then newest), as the
    "- [sub_domain] statement" lines contracts.md renders. None when there is no store, so the
    caller can fall back to the rendered file."""
    store = Path(root) / "state" / "global-patterns.jsonl"
    if not store.exists():
        return None
    try:
        rows = [r for r in effective_patterns(locked_jsonl_read_all(store)) if r.get("statement")]
    except Exception:
        return None
    if not rows:
        return None
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    rows.sort(key=lambda r: -int(r.get("confirmed_count") or 0))  # stable: newest first per count
    return [f"- [{r.get('sub_domain', 'general')}] {r['statement']}" for r in rows[:room]]


def project_contracts(root: Path, slug: str) -> list[str]:
    return _lines(Path(root) / "knowledge" / "projects" / slug / "contracts.md")


def global_contracts(root: Path, cap: int = DEFAULT_GLOBAL_CAP) -> list[str]:
    """Defaults are always kept; personal learnings fill the remaining room up to `cap`. Choosing
    by evidence rather than age means a lesson confirmed in several projects outlives a newer
    one-off, and a retired learning never loads."""
    root = Path(root)
    defaults = _lines(root / "knowledge" / "default-contracts.md")[:cap]
    room = cap - len(defaults)
    if room <= 0:
        return defaults
    personal = ranked_global_lessons(root, room)
    if personal is None:
        personal = _lines(root / "knowledge" / "global" / "contracts.md")[-room:]
    return defaults + personal


def effective_contracts(root: Path, slug: str, global_cap: int = DEFAULT_GLOBAL_CAP) -> dict:
    """{"global": [...], "project": [...], "all": [...]} with global first, the order they apply."""
    glob = global_contracts(root, global_cap)
    proj = project_contracts(root, slug)
    return {"global": glob, "project": proj, "all": glob + proj}


# --- classification ------------------------------------------------------------------------
# Which contracts a machine can check (a command to run, something never to commit or push)
# and which need judgment. Conservative on purpose: a wrongly "mechanical" contract would become
# a blocking check, so anything uncertain stays "judgment". Used to decide what to compile into
# hook checks; the list it produces is reviewed by a person before anything is enforced.
_MECHANICAL_PATTERNS = (
    # a command to run: `run` or `execute` followed by a backticked command
    re.compile(r"\b(always\s+)?(run|execute)\s+`[^`\n]+`", re.IGNORECASE),
    re.compile(r"\bnever\s+(commit|push|read|print|log|force[- ]push)\b", re.IGNORECASE),
    re.compile(r"\bmust\s+never\s+be\s+(committed|pushed)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+use\s+--[a-z]", re.IGNORECASE),  # a flag that must not be used
    re.compile(r"--no-verify"),
)


def classify_contract(text: str) -> str:
    """"mechanical" or "judgment"."""
    return "mechanical" if any(p.search(text) for p in _MECHANICAL_PATTERNS) else "judgment"
