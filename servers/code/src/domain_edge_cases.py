"""
Domain-aware edge-case elicitation (CIR-163, Phase 2 of 4).

Filters the generic edge-case taxonomy (skills/stress-test/references/edge-case-questions.md,
already loaded by nfr.py's load_functional_edge_case_questions) against this project's real
Domain Brief (state/domain-brief.json, CIR-162 Phase 1) so a developer sees domain-specific
candidates only when a real invariant is genuinely relevant to the task -- never the generic
taxonomy applied wholesale. design.md's cited requirements-engineering research is explicit:
LLM-surfaced candidates flood engineers with false positives unless filtered against real
context; this is that filter, not a second parallel elicitation mechanism.

Matching is deliberately proportionate to real project scale (state/problem-space-modeling/
design.md's explicit non-goals: no embeddings, no vector DB, no ML model) -- a bounded context
is relevant to a task only if one of its own ubiquitous_language terms, or its own name,
actually appears in the task text. No invented vocabulary, no fuzzy scoring beyond term count.

Reads state/domain-brief.json directly as JSON rather than importing servers/core/src/
domain_brief.py: youk-core and youk-code are separate Docker containers by design (ADR-001,
itself one of the real invariants this module can surface) -- youk-code has read access to
the generated state file, never to core's own module.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

YOUK_ROOT = Path("/youk")

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _domain_brief_path(root: Path) -> Path:
    return root / "state" / "domain-brief.json"


def load_domain_brief(root: Path = YOUK_ROOT) -> dict | None:
    """
    Returns None if the Domain Brief hasn't been generated for this project (CIR-162
    Phase 1 not run yet) or is unreadable -- a missing/broken brief means zero
    domain-specific candidates surfaced, never an error that blocks nfr-check.
    """
    path = _domain_brief_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _task_words(task: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(task)}


def surface_domain_edge_cases(task: str, root: Path = YOUK_ROOT, *, top_n: int = 5) -> list[dict]:
    """
    Real domain-specific edge-case candidates for this task, filtered against the real
    Domain Brief -- never the generic taxonomy applied to every task regardless of fit.

    A bounded context is relevant only if the task text contains one of its own
    ubiquitous_language terms (case-insensitive whole-word match) or its own name
    (case-insensitive substring). Each surfaced candidate names which real invariant
    and source (file + ADR/decision id) made it relevant, so a developer can check the
    claim rather than just trust it. Ranked by match strength, capped at top_n.

    Returns [] when the Domain Brief is missing or nothing in it is genuinely relevant
    to this task -- an empty list is the correct, honest answer, never a forced match
    (same never-backfill discipline as domain_brief.py's extractors).
    """
    brief = load_domain_brief(root)
    if not brief:
        return []

    task_words = _task_words(task)
    task_lower = task.lower()
    candidates: list[dict] = []

    for bc in brief.get("bounded_contexts", []):
        name = bc.get("name", "")
        terms = bc.get("ubiquitous_language", [])
        matched_terms = sorted({t for t in terms if t.lower() in task_words})
        name_matched = bool(name) and name.lower() in task_lower
        if not matched_terms and not name_matched:
            continue
        score = len(matched_terms) + (2 if name_matched else 0)
        for inv in bc.get("invariants", []):
            candidates.append(
                {
                    "question": f"Does this task respect the real invariant: {inv['statement']}",
                    "bounded_context": name,
                    "matched_terms": matched_terms,
                    "source_file": inv.get("source_file", ""),
                    "source_id": inv.get("source_id", ""),
                    "score": score,
                }
            )

    candidates.sort(key=lambda c: -c["score"])
    return candidates[:top_n]
