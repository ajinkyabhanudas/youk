"""Skill generation and assessment — signal-driven SKILL.md lifecycle."""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, "/shared")
from skill_loader import load_skill, list_skills

YOUK_ROOT = Path("/youk")
CLAUDE_ROOT = Path("/claude")
SKILLS_DIR = CLAUDE_ROOT / "skills"
AUDIT_DIR = CLAUDE_ROOT / "audit"


# ── Knowledge loading ───────────────────────────────────────────────────────

def _load_skill_schema() -> str:
    path = YOUK_ROOT / "knowledge" / "skill-schema.md"
    return path.read_text() if path.exists() else ""


def _load_cross_project_knowledge() -> str:
    path = YOUK_ROOT / "knowledge" / "cross-project.md"
    return path.read_text() if path.exists() else ""


def _load_stack_overlay_schema() -> str:
    path = CLAUDE_ROOT / "skills" / "stack-overlay-schema.md"
    return path.read_text() if path.exists() else ""


def _sample_example_skills(preferred: list[str] | None = None) -> str:
    """Return compact excerpts from 2 well-formed skills as structural examples."""
    names = preferred or ["dev-loop", "adr"]
    examples = []
    for name in names:
        skill_file = SKILLS_DIR / name / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text()
            # Cap at 2500 chars — enough for structure, not overwhelming
            if len(content) > 2500:
                content = content[:2500] + "\n...[truncated for brevity]"
            examples.append(f"=== EXAMPLE: {name}/SKILL.md ===\n{content}")
    return "\n\n".join(examples)


def _read_audit_for_skill(skill_name: str, months: int = 3) -> str:
    """Extract audit entries where the skill appeared — for gap evidence."""
    if not AUDIT_DIR.exists():
        return ""

    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=months * 30)
    entries = []

    for audit_file in sorted(AUDIT_DIR.glob("*.md")):
        try:
            parts = audit_file.stem.split("-")
            file_date = datetime(int(parts[0]), int(parts[1]), 1)
            if file_date < cutoff:
                continue
        except (ValueError, IndexError):
            continue

        text = audit_file.read_text()
        for block in re.split(r"\n### Session", text):
            # Match sessions that used or mentioned this skill
            if "Skills:" in block and skill_name in block:
                entries.append(block[:600])

    if not entries:
        return "(No audit entries found for this skill yet.)"

    header = f"=== AUDIT EVIDENCE: sessions using '{skill_name}' (last {months} months) ==="
    return header + "\n\n---\n".join(entries[:6])


def _read_audit_for_missing_skills(months: int = 2) -> dict[str, int]:
    """
    Find skills that route_task references but have no SKILL.md.
    Reads 'skills' lines in audit to detect gaps from real sessions.
    Returns {skill_name: mention_count}.
    """
    if not AUDIT_DIR.exists():
        return {}

    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=months * 30)
    known = {s["name"] for s in list_skills() if s["has_skill_md"]}
    missing_counts: dict[str, int] = {}

    for audit_file in sorted(AUDIT_DIR.glob("*.md")):
        try:
            parts = audit_file.stem.split("-")
            file_date = datetime(int(parts[0]), int(parts[1]), 1)
            if file_date < cutoff:
                continue
        except (ValueError, IndexError):
            continue

        for line in audit_file.read_text().splitlines():
            if line.startswith("Skills:"):
                for skill in re.split(r"[,\s]+", line[len("Skills:"):].strip()):
                    skill = skill.strip()
                    if skill and skill not in known and skill != "none":
                        missing_counts[skill] = missing_counts.get(skill, 0) + 1

    return missing_counts


def _read_audit_skill_gap_signals(months: int = 2) -> list[dict]:
    """
    Parse 'SkillGap:' lines from audit entries.
    Returns [{skill, gap, count}] aggregated across sessions.
    """
    if not AUDIT_DIR.exists():
        return []

    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=months * 30)
    raw: dict[str, list[str]] = {}

    for audit_file in sorted(AUDIT_DIR.glob("*.md")):
        try:
            parts = audit_file.stem.split("-")
            file_date = datetime(int(parts[0]), int(parts[1]), 1)
            if file_date < cutoff:
                continue
        except (ValueError, IndexError):
            continue

        for line in audit_file.read_text().splitlines():
            if line.startswith("SkillGap:"):
                rest = line[len("SkillGap:"):].strip()
                if " — " in rest:
                    skill, gap = rest.split(" — ", 1)
                    raw.setdefault(skill.strip(), []).append(gap.strip())

    return [
        {"skill": skill, "gaps": gaps, "count": len(gaps)}
        for skill, gaps in raw.items()
        if len(gaps) >= 1
    ]


# ── Core functions ──────────────────────────────────────────────────────────

def generate_skill(
    name: str,
    purpose: str,
    project_context: dict | None = None,
    signal_type: str = "engineer_request",
) -> dict:
    """
    Assemble context for in-session SKILL.md generation by Claude Code.

    Returns schema + examples + cross-project knowledge so the active Claude Code
    session generates the SKILL.md with full conversation context. No API call.

    signal_type: "engineer_request" | "demand_gap" | "project_type_gap" | "best_practices_gap"
    """
    schema = _load_skill_schema()
    cross_project = _load_cross_project_knowledge()
    examples = _sample_example_skills()

    signal_guidance = {
        "demand_gap": (
            "This skill was referenced by route_task but has no SKILL.md. "
            "The primary example flow should be the exact task that triggered the gap."
        ),
        "project_type_gap": (
            "This skill fills a gap for the detected project type. "
            "Encode project-type-specific quality bars and context capture fields."
        ),
        "best_practices_gap": (
            "This skill encodes a pattern from best-practices knowledge that no existing skill covers. "
            "The quality bars must directly enforce the pattern from cross-project knowledge."
        ),
        "stack_analysis": (
            "Derived proactively from stack analysis (skill-forge Loop A), not from a session miss. "
            "The quality bars must encode the elite pattern the search surfaced, and every bar "
            "must cite its source (repo location or URL). No aspirational bars without a traceable why."
        ),
        "engineer_request": "Skill requested directly by the engineer.",
    }.get(signal_type, "")

    return {
        "mode": "in_session",
        "name": name,
        "purpose": purpose,
        "signal_type": signal_type,
        "signal_guidance": signal_guidance,
        "project_context": project_context or {},
        "skill_schema": schema,
        "cross_project_knowledge": cross_project,
        "example_skills": examples,
        "write_path": f"{name}/SKILL.md",
        "instruction": (
            f"Generate a SKILL.md for skill '{name}'. "
            "Follow skill_schema exactly. Encode patterns from cross_project_knowledge. "
            "Use example_skills for structure. Every line must direct behavior — not document it. "
            "Output ONLY the SKILL.md content, no preamble or markdown fence. "
            "Then call youk-core.add_proposal() with change_type=FILE_CREATE and apply_proposal(confirmed=True) to write it."
        ),
    }


def assess_skill(skill_name: str) -> dict:
    """
    Assemble context for in-session skill assessment by Claude Code.

    Returns SKILL.md content + audit evidence + gap signals so the active
    Claude Code session performs the assessment with full conversation context.
    No API call.

    The returned dict instructs Claude Code to produce:
      coverage_score, strengths, gaps, proposed_additions
    Each proposed_addition maps directly to a youk-core.add_proposal() call.
    """
    try:
        skill_content = load_skill(skill_name)
    except FileNotFoundError:
        return {"error": f"Skill not found: {skill_name}"}

    cross_project = _load_cross_project_knowledge()
    audit_evidence = _read_audit_for_skill(skill_name)
    all_gap_signals = _read_audit_skill_gap_signals()
    skill_gaps = [s for s in all_gap_signals if s["skill"] == skill_name]

    return {
        "mode": "in_session",
        "skill_name": skill_name,
        "skill_content": skill_content,
        "cross_project_knowledge": cross_project,
        "audit_evidence": audit_evidence,
        "gap_signals": skill_gaps,
        "assessment_criteria": [
            "Does it encode the best-practices patterns from cross_project_knowledge?",
            "Does audit evidence show recurring misses that the skill didn't catch?",
            "Are quality bars specific and testable — not aspirational?",
            "Does each phase have clear numbered steps and a compact output summary?",
            "Are reference files listed and used at specific phases?",
        ],
        "instruction": (
            "Assess this skill against the criteria above. "
            "Return coverage_score (0-10), strengths (list), gaps (list of {section, gap, evidence}), "
            "and proposed_additions (list of {section, content, change_type: 'SKILL_EDIT', "
            f"target: '{skill_name}', target_section, rationale}}). "
            "For each proposed_addition call youk-core.add_proposal() then apply_proposal(confirmed=True)."
        ),
    }


def generate_stack_overlay(
    skill_name: str,
    stack: str,
    framework: str | None = None,
    domain: str | None = None,
    project_context: dict | None = None,
) -> dict:
    """
    Assemble context for in-session stack overlay generation.

    Returns the overlay schema + base skill + cross-project knowledge so Claude Code
    generates the overlay file content in-session without an extra API call.

    After generating, Claude Code calls add_proposal(FILE_CREATE) + apply_proposal(confirmed=True)
    to save the file at references/stacks/{framework or stack}.md.
    """
    try:
        base_skill = load_skill(skill_name)
    except FileNotFoundError:
        return {"error": f"Skill not found: {skill_name}"}

    schema = _load_stack_overlay_schema()
    cross_project = _load_cross_project_knowledge()

    # Framework is more specific than stack — use it as filename target when available
    target_label = framework or stack
    write_path = f"{skill_name}/references/stacks/{target_label}.md"

    # Check if overlay already exists — if so, return early with a pointer
    existing = SKILLS_DIR / skill_name / "references" / "stacks" / f"{target_label}.md"
    if existing.exists():
        return {
            "status": "already_exists",
            "write_path": write_path,
            "message": (
                f"Overlay already exists at {write_path}. "
                "It is loaded automatically via load_skill_with_context(). "
                "To update it, call assess_skill or edit the file directly."
            ),
        }

    return {
        "mode": "in_session",
        "skill_name": skill_name,
        "stack": stack,
        "framework": framework,
        "domain": domain,
        "target_label": target_label,
        "write_path": write_path,
        "base_skill_content": base_skill,
        "overlay_schema": schema,
        "cross_project_knowledge": cross_project,
        "project_context": project_context or {},
        "instruction": (
            f"Generate a stack overlay for the '{skill_name}' skill targeting: {target_label}. "
            "Rules:\n"
            "1. Read base_skill_content first — do NOT duplicate what's already checked.\n"
            "2. Follow overlay_schema exactly — all 6 sections required.\n"
            "3. Every line must change behavior, not describe a concept.\n"
            "4. Critical Questions is the highest-value section — do not truncate it.\n"
            "5. Total output must be under 600 tokens.\n"
            "6. Output ONLY the overlay content, no preamble.\n"
            f"7. Then call youk-core.add_proposal(change_type='FILE_CREATE', target='{write_path}') "
            "and apply_proposal(confirmed=True) to save it."
        ),
    }


def detect_skill_gaps() -> dict:
    """
    Aggregate all signal sources to surface skills that need generation or evolution.

    Returns:
    - missing_skills: skills referenced in audit but no SKILL.md exists
    - gap_signals: existing skills with recurring gap signals in audit
    - knowledge_gaps: best-practice patterns in cross-project.md not encoded in any skill
    """
    missing = _read_audit_for_missing_skills()
    gap_signals = _read_audit_skill_gap_signals()

    # Check cross-project patterns against existing skills
    cross_project = _load_cross_project_knowledge()
    existing_content = ""
    for s in list_skills():
        if s["has_skill_md"]:
            try:
                existing_content += load_skill(s["name"]) + "\n"
            except FileNotFoundError:
                pass

    # Simple heuristic: find headings in cross-project.md and check if any skill mentions them
    knowledge_gaps = []
    for match in re.finditer(r"^## (.+)$", cross_project, re.MULTILINE):
        pattern_name = match.group(1).strip()
        # Extract key phrase from the pattern name (first 4 words)
        key = " ".join(pattern_name.lower().split()[:4])
        if key and key not in existing_content.lower():
            knowledge_gaps.append(pattern_name)

    return {
        "missing_skills": [
            {"skill": k, "audit_mentions": v}
            for k, v in sorted(missing.items(), key=lambda x: -x[1])
        ],
        "gap_signals": gap_signals,
        "knowledge_gaps": knowledge_gaps,
        "recommendation": (
            "For missing_skills: call generate_skill(name, purpose, signal_type='demand_gap'). "
            "For gap_signals: call assess_skill(skill_name) to get proposed_additions. "
            "For knowledge_gaps: assess which skill should encode the pattern, or generate a new one."
        ),
    }


def analyze_stack_for_skills(
    stack: str,
    framework: str | None = None,
    domain: str | None = None,
    repo_paths: list[str] | None = None,
    known_skills: list[str] | None = None,
    standard: str | None = None,
) -> dict:
    """
    Assemble context for in-session, stack-proactive skill discovery (skill-forge Loop A).

    The proactive counterpart to detect_skill_gaps(). detect_skill_gaps reads audit history
    (what already went wrong); this asks what an ELITE engineer in this stack would need
    before any session proves it — then loops at a rising standard until even an imagined
    superior engineer has nothing to add.

    standard: the current written bar for "what elite means for this stack." On the first
        cycle this is None; the session raises it each cycle (the RAISE-THE-BAR step) and
        passes the raised bar back in. Convergence is when the bar stops rising — NOT when
        skill-count settles.

    Returns mode='in_session' context. No API call runs here; the Claude session performs
    the deep repo + live internet search and derives skills.
    """
    existing = known_skills if known_skills is not None else [s["name"] for s in list_skills()]
    return {
        "mode": "in_session",
        "stack": stack,
        "framework": framework,
        "domain": domain,
        "repo_paths": repo_paths or [],
        "existing_skills": existing,
        "current_standard": standard or "",
        "skill_schema": _load_skill_schema(),
        "cross_project_knowledge": _load_cross_project_knowledge(),
        "search_directive": {
            "repo": "Read repo idioms, dependency graph, test patterns, and failure modes.",
            "internet": (
                "WebSearch current best practices, common failure modes, and elite patterns "
                "for this stack (framework docs, Anthropic/OpenAI guidance, HN, papers). "
                "Cite sources per derived skill — no skill enters the batch without a traceable why."
            ),
        },
        "raise_the_bar_step": (
            "Before listing skills this cycle: read current_standard and ask 'what would an "
            "engineer BETTER than the one who wrote this bar object to or add?' Rewrite the "
            "standard upward. The raised bar is the loop's real variable — a rising bar can "
            "surface skills the old bar could not see."
        ),
        "derivation_criteria": [
            "For each candidate skill: WHY it's needed (the failure it prevents), HOW it "
            "matters (the causal chain to output quality), sources (repo path or URL), and "
            "covered_by (an existing skill name if already covered — then drop it).",
        ],
        "convergence_rule": (
            "Bar rose this cycle → loop again. Bar stable AND no new skill → converged, exit. "
            "A cycle that spent tokens but neither raised the bar nor added a skill is a wasted "
            "cycle — report it. Adaptive ceiling: past soft_cycles, continue only on substantial "
            "bar-lift; stop at marginal lift or hard_cap, flagging ceiling_hit if not converged."
        ),
        "instruction": (
            "Perform one Loop A cycle: run the raise-the-bar step, then derive the skill set an "
            "elite engineer in this stack needs under the raised bar. For each genuinely new "
            "skill (not covered_by an existing one): generate_skill(signal_type='stack_analysis') "
            "then add_proposal(FILE_CREATE) + apply_proposal(confirmed=True, safe_types=['FILE_CREATE']). "
            "Return {raised_standard, bar_rose: bool, candidates: [{name, why, how_it_matters, "
            "sources, covered_by}]} so the forge loop can decide whether to iterate."
        ),
    }
