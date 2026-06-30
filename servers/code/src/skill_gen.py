"""Skill generation and assessment — signal-driven SKILL.md lifecycle."""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/shared")
from skill_loader import load_skill, list_skills

try:
    import anthropic
    _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
except Exception:
    _client = None

_MODEL = "claude-sonnet-4-6"
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
    Generate a new SKILL.md from signals (project context, audit gaps, best practices).

    signal_type: "engineer_request" | "demand_gap" | "project_type_gap" | "best_practices_gap"

    Returns draft content + proposal dict. Does NOT write to disk.
    """
    if not _client:
        return {"error": "API client not available — check ANTHROPIC_API_KEY"}

    schema = _load_skill_schema()
    cross_project = _load_cross_project_knowledge()
    examples = _sample_example_skills()

    context_str = ""
    if project_context:
        context_str = "\n".join(f"  {k}: {v}" for k, v in project_context.items())

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
        "engineer_request": "Skill requested directly by the engineer.",
    }.get(signal_type, "")

    system = f"""You are generating a youk SKILL.md. Every word either directs behavior or wastes tokens.
Write as if it is code, not documentation. Be specific and concrete — not aspirational.

=== SKILL SCHEMA (follow exactly) ===
{schema}

=== BEST-PRACTICES KNOWLEDGE (encode relevant patterns) ===
{cross_project}

=== STRUCTURAL EXAMPLES (follow this structure) ===
{examples}

Signal type: {signal_type}
{signal_guidance}

Output ONLY the SKILL.md content. No preamble, no explanation, no markdown fence."""

    context_block = f"\nProject context:\n{context_str}" if context_str else ""
    user = f"Generate a SKILL.md for skill: {name}\n\nPurpose: {purpose}{context_block}"

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    content = response.content[0].text.strip()
    # Strip accidental markdown code fences
    if content.startswith("```"):
        content = re.sub(r"^```[^\n]*\n", "", content)
        content = re.sub(r"\n```$", "", content)

    return {
        "content": content,
        "write_path": f"{name}/SKILL.md",
        "signal_type": signal_type,
        "proposal": {
            "title": f"Generate skill: {name}",
            "rationale": f"Signal: {signal_type}. Purpose: {purpose}",
            "change_type": "FILE_CREATE",
            "target": f"{name}/SKILL.md",
            "content": content,
            "target_section": "",
        },
        "note": (
            "Review content before writing. "
            "Call youk-core.add_proposal(proposal) then apply_proposal(id, confirmed=True) to write."
        ),
    }


def assess_skill(skill_name: str) -> dict:
    """
    Assess a skill against audit evidence and best-practices knowledge.
    Returns coverage score, strengths, gaps, and proposed SKILL_EDIT additions.
    Each proposed_addition maps directly to an add_proposal() call.
    """
    if not _client:
        return {"error": "API client not available — check ANTHROPIC_API_KEY"}

    try:
        skill_content = load_skill(skill_name)
    except FileNotFoundError:
        return {"error": f"Skill not found: {skill_name}"}

    cross_project = _load_cross_project_knowledge()
    audit_evidence = _read_audit_for_skill(skill_name)

    system = f"""You are assessing a youk SKILL.md for coverage gaps and improvement opportunities.

=== BEST-PRACTICES KNOWLEDGE ===
{cross_project}

=== AUDIT EVIDENCE ===
{audit_evidence}

Assess the skill against:
1. Does it encode the best-practices patterns above?
2. Does audit evidence show recurring misses?
3. Are quality bars specific and testable (not aspirational)?
4. Does each phase have clear numbered steps and a compact output summary?
5. Are reference files listed and used at specific phases?

Return ONLY valid JSON — no markdown fence, no explanation:
{{
  "coverage_score": <integer 0-10>,
  "strengths": ["what the skill covers well — be specific"],
  "gaps": [
    {{
      "section": "<section name>",
      "gap": "<specific gap — not vague>",
      "evidence": "<from audit / deduced from best practices / schema requirement>"
    }}
  ],
  "proposed_additions": [
    {{
      "section": "<exact section heading from SKILL.md>",
      "content": "<the exact text to insert>",
      "change_type": "SKILL_EDIT",
      "target": "{skill_name}",
      "target_section": "<exact section heading>"
    }}
  ]
}}"""

    user = f"Assess this SKILL.md:\n\n=== {skill_name}/SKILL.md ===\n{skill_content}"

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```[^\n]*\n", "", text)
    text = re.sub(r"\n```$", "", text)

    try:
        result = json.loads(text)
        result["skill"] = skill_name
        return result
    except json.JSONDecodeError:
        return {
            "skill": skill_name,
            "raw_assessment": text,
            "error": "Could not parse structured JSON — check raw_assessment for content",
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
