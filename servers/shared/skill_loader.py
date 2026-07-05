from __future__ import annotations
from pathlib import Path
from typing import Optional


CLAUDE_ROOT = Path("/claude")
SKILLS_DIR = CLAUDE_ROOT / "skills"


def load_skill(skill_name: str) -> str:
    """Load a SKILL.md file by name from the mounted claude volume."""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name} at {skill_file}")
    return skill_file.read_text()


def load_skill_reference(skill_name: str, reference_name: str) -> str:
    """Load a reference file from a skill's references/ directory."""
    ref_file = SKILLS_DIR / skill_name / "references" / reference_name
    if not ref_file.exists():
        raise FileNotFoundError(f"Reference not found: {skill_name}/references/{reference_name}")
    return ref_file.read_text()


def load_skill_with_context(
    skill_name: str,
    stack: Optional[str] = None,
    framework: Optional[str] = None,
    domain: Optional[str] = None,
) -> str:
    """
    Load a skill's SKILL.md and append relevant stack/domain overlays.

    Token-efficient: overlays are appended only when their file exists —
    a missing overlay file is silently skipped. Each overlay adds ~300-500
    tokens (directive rules only, no tutorial content).

    Lookup order:
    - Stack: references/stacks/{framework}.md → references/stacks/{stack}.md → references/{stack}.md
    - Domain: domain/{domain}.md

    Returns the base SKILL.md content plus any matched overlay sections.
    """
    base = load_skill(skill_name)
    skill_dir = SKILLS_DIR / skill_name
    parts = [base]

    # Stack overlay: try framework first (more specific), then language
    stack_candidates: list[Path] = []
    if framework:
        stack_candidates += [
            skill_dir / "references" / "stacks" / f"{framework}.md",
            skill_dir / "references" / f"{framework}.md",
        ]
    if stack and stack != framework:
        stack_candidates += [
            skill_dir / "references" / "stacks" / f"{stack}.md",
            skill_dir / "references" / f"{stack}.md",
        ]
    for candidate in stack_candidates:
        if candidate.exists():
            overlay = candidate.read_text().strip()
            if overlay:
                parts.append(f"\n## Stack context: {candidate.stem}\n\n{overlay}")
            break  # first match wins

    # Domain overlay
    if domain:
        domain_candidates = [
            skill_dir / "domain" / f"{domain}.md",
            skill_dir / "references" / "domain" / f"{domain}.md",
        ]
        for candidate in domain_candidates:
            if candidate.exists():
                overlay = candidate.read_text().strip()
                if overlay:
                    parts.append(f"\n## Domain context: {domain}\n\n{overlay}")
                break

    return "\n".join(parts)


def load_skill_fast_path(skill_name: str) -> Optional[str]:
    """Extract the fast-path frontmatter from a SKILL.md if present."""
    try:
        content = load_skill(skill_name)
    except FileNotFoundError:
        return None

    if not content.startswith("---"):
        return None

    end = content.find("---", 3)
    if end == -1:
        return None

    frontmatter = content[3:end]
    fast_path_start = frontmatter.find("fast-path:")
    auto_skip_start = frontmatter.find("auto-skip:")

    if fast_path_start != -1:
        return frontmatter[fast_path_start:].strip()
    if auto_skip_start != -1:
        return frontmatter[auto_skip_start:].strip()
    return None


def list_skills() -> list[dict]:
    """List all available skills with basic metadata."""
    if not SKILLS_DIR.exists():
        return []

    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            # Include dirs without SKILL.md — they're gaps, not invisible
            skills.append({
                "name": skill_dir.name,
                "description": "No SKILL.md found — skill directory exists but is incomplete.",
                "has_skill_md": False,
                "has_fast_path": False,
                "size_bytes": 0,
            })
            continue

        content = skill_file.read_text()
        description = _extract_description(content)
        fast_path = load_skill_fast_path(skill_dir.name) is not None

        skills.append({
            "name": skill_dir.name,
            "description": description,
            "has_skill_md": True,
            "has_fast_path": fast_path,
            "size_bytes": skill_file.stat().st_size,
        })
    return skills


def _extract_description(content: str) -> str:
    """Extract the first non-empty line after the frontmatter as a description."""
    lines = content.split("\n")
    in_frontmatter = False
    past_frontmatter = False

    for line in lines:
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                past_frontmatter = True
            continue
        if past_frontmatter and line.strip() and not line.startswith("#"):
            return line.strip()[:120]
        if past_frontmatter and line.startswith("# "):
            return line.lstrip("# ").strip()[:120]

    # No frontmatter — first heading
    for line in lines:
        if line.startswith("# "):
            return line.lstrip("# ").strip()[:120]
    return "No description"
