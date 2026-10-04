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
from pathlib import Path

YOUK_ROOT = Path("/youk")

# servers/shared is on sys.path in both containers.
from domain_context import match_invariants, words as _words  # noqa: F401


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
    """Invariants from the brief's bounded contexts that overlap this task,
    each carrying the real source that made it relevant. See
    domain_context.match_invariants for the matching rule."""
    return match_invariants(task, brief, top_n=top_n)


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
