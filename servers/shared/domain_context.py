"""Pick the parts of a project's Domain Brief that apply to one task.

The Domain Brief (state/domain-brief.json) is the stable half: bounded
contexts, ubiquitous language and invariants taken from real decision records.
Which of it applies is decided fresh for every task by vocabulary overlap --
nothing about the relevance of a context to a task is stored or reused, so a
past task cannot bias a later one (docs/problem-space-modeling-design.md).

Lives in servers/shared because both containers need it: youk-code's nfr_check
edge-case pass and youk-core's optimize_intent sizing call. It reads plain
JSON and imports nothing from either container.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def match_invariants(task: str, brief: dict, *, top_n: int = 5) -> list[dict]:
    """At most top_n invariants from bounded contexts whose vocabulary (the
    context's ubiquitous_language terms plus its own name words) overlaps the
    task, most overlap first. A context with no overlap contributes nothing,
    so an unrelated task against a populated brief returns []."""
    task_words = words(task)
    candidates: list[dict] = []
    for ctx in brief.get("bounded_contexts", []):
        ctx_terms = {t.lower() for t in ctx.get("ubiquitous_language", [])}
        ctx_terms |= words(ctx.get("name", ""))
        matched = sorted(task_words & ctx_terms)
        if not matched:
            continue
        for inv in ctx.get("invariants", []):
            candidates.append(
                {
                    "invariant": inv["statement"],
                    "source_file": inv["source_file"],
                    "source_id": inv["source_id"],
                    "bounded_context": ctx["name"],
                    "matched_terms": matched,
                    "relevance_score": len(matched),
                }
            )
    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
    return candidates[:top_n]
