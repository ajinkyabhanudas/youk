"""
Context compaction — youk's alternative to Claude's generic auto-compaction.

The key difference: Claude compacts by recency. Youk compacts by information tier.
CONTRACT content is pinned verbatim. DECISION content is summarized. EXPLORATION
is compressed. CLARIFICATION is dropped. The brief is rebuilt from structured files,
not summarized from conversation — so no information is lost through paraphrase.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")

YOUK_ROOT = Path("/youk")

_TIER_INSTRUCTION = """CONTRACT lines are load-bearing behavioral agreements — preserve them VERBATIM through any further compaction. Never paraphrase, shorten, or omit them. They are exactly what must survive."""


def _slug(project_dir: str) -> str:
    return Path(project_dir).name or "unknown"


def _load_contracts(slug: str) -> list[str]:
    f = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    if not f.exists():
        return []
    return [
        line.strip()
        for line in f.read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("---")
    ]


def _load_decisions(slug: str) -> list[str]:
    f = YOUK_ROOT / "knowledge" / "projects" / slug / "decisions.md"
    if not f.exists():
        return []
    # Return the most recent 5 decision headings with one-line summary
    lines = f.read_text().splitlines()
    decisions = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ") and current:
            decisions.append("\n".join(current))
            current = [line]
        elif line.strip():
            current.append(line)
    if current:
        decisions.append("\n".join(current))
    return decisions[-5:]  # last 5 decisions only


def _load_task_state() -> dict:
    state_file = YOUK_ROOT / "state" / "session.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text())
    except Exception:
        return {}


def _load_session_plan() -> list[str]:
    plan_file = YOUK_ROOT / "state" / "session-plan.json"
    if not plan_file.exists():
        return []
    try:
        data = json.loads(plan_file.read_text())
        return data.get("plan", [])
    except Exception:
        return []


def build_brief(project_dir: str) -> dict:
    """
    Build a structured context brief from youk's knowledge store.

    Returns a brief that Claude must paste VERBATIM into its response so it
    appears in recent context and survives the next compaction cycle.
    Content is generated from structured files — not conversation summaries —
    so contracts are immune to paraphrase degradation.
    """
    slug = _slug(project_dir)
    contracts = _load_contracts(slug)
    decisions = _load_decisions(slug)
    state = _load_task_state()
    session_plan = _load_session_plan()

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = [f"YOUK CONTEXT BRIEF — {timestamp}"]

    # Contracts: always verbatim, always first
    if contracts:
        sections.append("## Pinned Contracts (verbatim — never summarize or paraphrase)")
        for c in contracts:
            sections.append(f"- {c}")
    else:
        sections.append("## Pinned Contracts\n(none saved yet — call session_end to capture working agreements)")

    # Decisions: key fact + rationale only
    if decisions:
        sections.append("## Active Decisions")
        for d in decisions:
            lines = d.strip().splitlines()
            # heading + first non-empty body line
            heading = lines[0] if lines else ""
            body = next((ln for ln in lines[1:] if ln.strip()), "")
            sections.append(f"{heading}: {body}".strip())

    # Task state
    project = state.get("last_project", project_dir)
    session_n = state.get("session_counter", "?")
    sections.append(
        f"## Session state\n"
        f"Project: {slug} | Session #{session_n} | Dir: {project}"
    )

    # Session plan: what was in-progress at session_start (survives compaction from files)
    if session_plan:
        plan_lines = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(session_plan))
        sections.append(f"## Session plan (from last session_start)\n{plan_lines}")

    sections.append(f"## Compaction instruction\n{_TIER_INSTRUCTION}")

    brief = "\n\n".join(sections)

    # Write session checkpoint so next session_start can recover audit state
    # if the developer closes the tab without calling /done.
    checkpoint_file = YOUK_ROOT / "state" / "session-checkpoint.json"
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        checkpoint_file.write_text(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "slug": slug,
            "plan_items": session_plan,
            "contracts_count": len(contracts),
        }, indent=2))
    except Exception:
        pass  # checkpoint write failure must never block compact_context

    return {
        "brief": brief,
        "contracts_count": len(contracts),
        "decisions_count": len(decisions),
        "session_plan_items": len(session_plan),
        "slug": slug,
        "generated_at": timestamp,
        "instruction": (
            "PASTE this brief VERBATIM into your next response — do not summarize or paraphrase. "
            "It must appear in recent context to survive the next compaction cycle. "
            "CONTRACT lines are invariant: never rephrase, never shorten, never drop."
        ),
    }


def write_contracts(slug: str, new_contracts: list[str]) -> int:
    """
    Append new contract lines to knowledge/projects/{slug}/contracts.md.
    Returns count of lines added (deduplicates against existing).
    """
    contracts_file = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    contracts_file.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    if contracts_file.exists():
        existing = {
            line.strip().lstrip("- ")
            for line in contracts_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }

    to_add = [c for c in new_contracts if c.strip().lstrip("- ") not in existing]
    if not to_add:
        return 0

    with open(contracts_file, "a") as f:
        if not contracts_file.read_text().strip() if contracts_file.exists() else True:
            f.write(f"# Working contracts: {slug}\n\n")
        for c in to_add:
            f.write(f"- {c}\n")

    return len(to_add)
