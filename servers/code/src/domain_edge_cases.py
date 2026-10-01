"""
Domain-aware edge-case elicitation (CIR-163, Phase 2 of 4).

Cross-references task text against a project's real Domain Brief
(state/domain-brief.json, built by servers/core/src/domain_brief.py --
CIR-162, Phase 1) and surfaces ONLY the bounded-context invariants that are
genuinely relevant to the task at hand -- never every invariant for every
task. See state/problem-space-modeling/design.md section 2 ("Edge-case
elicitation pass (filtered, not a firehose)") for why this matters: the
cited requirements-engineering research says LLMs can surface real domain
gaps, but flood developers with false positives unless filtered against
real context.

Matching is deliberately simple: keyword overlap between the task text and
each bounded context's `ubiquitous_language` terms (plus its own name) --
same string/keyword-matching discipline the design doc requires (no
embeddings, no new dependency), already used for pattern-library retrieval
(CIR-160).

Decoupled from domain_brief.py's dataclasses on purpose: this module runs
in the youk-code container, domain_brief.py runs in youk-core (ADR-001 --
two containers, no shared Python imports between them). The only contract
between the two is the state/domain-brief.json file on the shared YOUK_ROOT
volume, so this module reads plain JSON, never imports domain_brief.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

YOUK_ROOT = Path("/youk")

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def domain_brief_path(youk_root: Path = YOUK_ROOT) -> Path:
    return youk_root / "state" / "domain-brief.json"


def load_domain_brief(youk_root: Path = YOUK_ROOT) -> dict | None:
    """
    Returns None if no Domain Brief exists yet for this project (CIR-162
    Phase 1 hasn't run here) or the file is unreadable/malformed -- a
    project without a brief gets zero domain-specific candidates, never a
    crash and never a fabricated one.
    """
    path = domain_brief_path(youk_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def find_domain_edge_case_candidates(task: str, brief: dict, *, top_n: int = 5) -> list[dict]:
    """
    Score each bounded context's invariants against the task text by
    keyword overlap (the context's ubiquitous_language terms plus its own
    name words) and return at most top_n candidates, highest relevance
    first. A bounded context with zero matched terms contributes nothing --
    an unrelated task and a populated brief together return [], not a
    forced match.

    Each candidate dict carries exactly which real invariant and source
    made it relevant, so a developer sees why it was surfaced, not just
    that it was:
      - invariant: the real statement text
      - source_file / source_id: traceable to the real ADR/decision entry
      - bounded_context: the Domain Brief bounded context name it came from
      - matched_terms: the task words that matched this context's vocabulary
      - relevance_score: len(matched_terms), used only to rank/cap
    """
    task_words = _words(task)
    candidates: list[dict] = []
    for ctx in brief.get("bounded_contexts", []):
        ctx_terms = {t.lower() for t in ctx.get("ubiquitous_language", [])}
        ctx_terms |= _words(ctx.get("name", ""))
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


def domain_edge_case_candidates(
    task: str, *, youk_root: Path = YOUK_ROOT, top_n: int = 5
) -> list[dict]:
    """
    Convenience entry point for nfr.py: load the real Domain Brief from disk
    and filter it for this task. Returns [] if no Domain Brief exists yet --
    never raises, same resilience discipline as nfr.py's own
    load_functional_edge_case_questions().
    """
    brief = load_domain_brief(youk_root)
    if brief is None:
        return []
    return find_domain_edge_case_candidates(task, brief, top_n=top_n)
