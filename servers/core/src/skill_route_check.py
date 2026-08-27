"""Verify that every skill CLAUDE.md routes to actually exists and loads.

Replaces the thing _audit_skill_quality pretended to do. That audit scored SKILL.md
files on markdown structure, which cannot distinguish a good skill from a bad one: a
file with three prose lines, one empty code fence and the word "Quality" scores 2 of 4
and passes. Scoring quality by substring is not possible, so this checks something that
is falsifiable instead.

The failure this catches is the one that actually happened. 14 skills were committed to
the repo, referenced by CLAUDE.md, and had no runtime symlink, so route_to_skill could
not load them. Nothing detected it for weeks because every existing check inspected a
description of the system rather than the system.

Binary and cheap: a route either resolves to a loadable SKILL.md or it does not.
"""
from __future__ import annotations

import re
from pathlib import Path

# Only explicit routing calls: route_to_skill("name", ...).
#
# Slash commands are deliberately NOT parsed. In CLAUDE.md they are prose documentation
# with inconsistent shapes: some name a skill (/intake), some alias another command
# (/requirements → nfr_check), some name an MCP tool (/health → self_heal()), and some
# are not routes at all (/explain → full depth, filler-free). Inferring routes from that
# produced three false positives on the first real run — compact-context and route-task
# are tools, and "full" came from prose.
#
# Guessing intent from prose is the same failure this module exists to replace, so the
# check is scoped to the one form that is unambiguous. Narrow and trustworthy beats
# broad and noisy: a check nobody believes gets ignored, which is how 14 dead skills
# survived alongside three green audits.
_ROUTE_PATTERN = re.compile(r"""route_to_skill\(\s*["']([a-z0-9_-]+)["']""")


def _normalize(name: str) -> str:
    """Fold separators. route_to_skill('nfr_check') loads the nfr-check skill."""
    return name.strip().lower().replace("_", "-")


def _referenced_skills(claude_md: Path) -> set[str]:
    """Skill names reached by an explicit route_to_skill call in CLAUDE.md."""
    if not claude_md.exists():
        return set()
    text = claude_md.read_text(errors="ignore")
    return {_normalize(n) for n in _ROUTE_PATTERN.findall(text)}


def check_skill_routes(claude_root: Path, youk_root: Path | None = None) -> dict:
    """Resolve every skill CLAUDE.md routes to.

    Returns {checked, unresolvable, empty, healthy, message}. Never raises: a health
    check must not be able to fail a session.

    A route is unresolvable when no SKILL.md can be read at the routed name, which is
    what a missing symlink looks like from the runtime's point of view. It is reported
    separately from `empty`, a SKILL.md that exists but has no content, because the two
    have different fixes: one is an install problem, the other an authoring problem.
    """
    try:
        claude_md = claude_root / "CLAUDE.md"
        skills_dir = claude_root / "skills"
        referenced = sorted(_referenced_skills(claude_md))

        if not referenced:
            return {
                "checked": 0, "unresolvable": [], "empty": [],
                "healthy": True, "message": "",
            }

        unresolvable, empty = [], []
        for name in referenced:
            skill_md = skills_dir / name / "SKILL.md"
            try:
                if not skill_md.exists():
                    unresolvable.append(name)
                elif not skill_md.read_text(errors="ignore").strip():
                    empty.append(name)
            except OSError:
                # A dangling symlink raises rather than returning False on read.
                unresolvable.append(name)

        parts = []
        if unresolvable:
            parts.append(
                f"CLAUDE.md routes to {len(unresolvable)} skill(s) that will not load "
                f"({', '.join(unresolvable)}) — the route fails silently at runtime. "
                "Run scripts/install.sh if they exist in the repo."
            )
        if empty:
            parts.append(
                f"{len(empty)} routed skill(s) have an empty SKILL.md "
                f"({', '.join(empty)})."
            )

        return {
            "checked": len(referenced),
            "unresolvable": unresolvable,
            "empty": empty,
            "healthy": not unresolvable and not empty,
            "message": " ".join(parts),
        }
    except Exception:
        return {
            "checked": 0, "unresolvable": [], "empty": [],
            "healthy": True, "message": "",
        }
