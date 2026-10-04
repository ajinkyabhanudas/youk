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
import time
from pathlib import Path

YOUK_ROOT = Path("/youk")

# servers/shared is on sys.path in both containers.
from domain_context import match_invariants, project_brief_path, words as _words  # noqa: F401


def domain_brief_path(youk_root: Path = YOUK_ROOT) -> Path:
    return youk_root / "state" / "domain-brief.json"


_SLUG_MAX_AGE_SECONDS = 4 * 60 * 60  # same window youk-core uses for the active session


def current_project_slug(youk_root: Path = YOUK_ROOT) -> str:
    """Slug of the most recently opened session (state/sessions/*/open.json, newer
    than four hours), or "" when none. Read from the shared volume as plain JSON
    because this container cannot import youk-core's state_paths."""
    sessions = youk_root / "state" / "sessions"
    if not sessions.exists():
        return ""
    now = time.time()
    for f in sorted(sessions.glob("*/open.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if now - f.stat().st_mtime > _SLUG_MAX_AGE_SECONDS:
            continue
        try:
            slug = json.loads(f.read_text()).get("slug", "")
        except (OSError, ValueError):
            continue
        if slug:
            return slug
    return ""


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_domain_brief(youk_root: Path = YOUK_ROOT) -> dict | None:
    """
    The current project's own brief (state/domain-briefs/{slug}.json) when it
    exists; otherwise the legacy single state/domain-brief.json, but only if it
    was built for the current project (when the current project is known).
    Returns None when there is no usable brief -- a project without one gets
    zero domain-specific candidates, never a crash and never another project's.
    """
    slug = current_project_slug(youk_root)
    if slug:
        per_project = project_brief_path(youk_root, slug)
        if per_project.exists():
            return _read_json(per_project)
    legacy = domain_brief_path(youk_root)
    if not legacy.exists():
        return None
    brief = _read_json(legacy)
    if brief is not None and slug and brief.get("project") != slug:
        return None
    return brief


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
