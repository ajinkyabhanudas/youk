"""
Skill re-entry suggestions from skill-graph.yaml reentry_edges.

After a capability skill (code-review, security-review, etc.) surfaces findings,
write_skill_handoff() calls check_reentry(). If the skill-graph has a reentry_edge
for that skill at or above the finding's severity, returns a suggestion dict so
the routing loop can propose routing back to the target skill.

Zero API. Pure file read + dict lookup. Fail-silent throughout.
"""
from __future__ import annotations

import yaml
from pathlib import Path

_DEFAULT_GRAPH = Path("/youk") / "knowledge" / "skill-graph.yaml"

_SEVERITY_RANK: dict[str, int] = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "BLOCKING": 4,
}


def _load_edges(skill_graph_path: Path) -> dict[str, list[dict]]:
    """Return reentry_edges dict from skill-graph.yaml, or {} on any failure."""
    try:
        data = yaml.safe_load(skill_graph_path.read_text(encoding="utf-8"))
        return (data or {}).get("reentry_edges", {})
    except Exception:
        return {}


def check_reentry(
    from_skill: str,
    findings_severity: str,
    skills_run_this_session: list[str] | None = None,
    skill_graph_path: Path | None = None,
) -> dict | None:
    """
    Check whether a skill re-entry is warranted after findings are surfaced.

    from_skill: skill that just completed (e.g. "code-review").
    findings_severity: highest severity in the findings — "BLOCKING"|"HIGH"|"MEDIUM"|"LOW".
    skills_run_this_session: list of skills already invoked; used to set already_ran.
    skill_graph_path: override for testing; defaults to /youk/knowledge/skill-graph.yaml.

    Returns a suggestion dict if an edge exists and severity meets the threshold:
        {
            "to_skill": str,
            "label": str,
            "trigger": str,
            "already_ran": bool,
            "message": str,
        }
    Returns None when no edge matches, severity is below threshold, or any error occurs.
    """
    try:
        graph_path = skill_graph_path or _DEFAULT_GRAPH
        edges = _load_edges(graph_path)
        if not edges:
            return None

        skill_edges = edges.get(from_skill)
        if not skill_edges:
            return None

        caller_rank = _SEVERITY_RANK.get(findings_severity.upper(), 0)
        run_set = set(skills_run_this_session or [])

        # Return first matching edge — graph ordering is priority order.
        for edge in skill_edges:
            threshold = edge.get("severity", "HIGH")
            if caller_rank >= _SEVERITY_RANK.get(threshold.upper(), 99):
                to_skill = edge.get("to", "")
                label = edge.get("label", "")
                trigger = edge.get("trigger", "")
                already_ran = to_skill in run_set
                return {
                    "to_skill": to_skill,
                    "label": label,
                    "trigger": trigger,
                    "already_ran": already_ran,
                    "message": (
                        f"Re-entry suggested: route to '{to_skill}' "
                        f"({trigger}). already_ran={already_ran}."
                    ),
                }

        return None

    except Exception:
        return None
