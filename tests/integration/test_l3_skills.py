"""L3 — Skill Completeness: registry vs SKILL.md files + list_skills + route_to_skill."""
import re
from pathlib import Path

import pytest

from .mcp_client import call_tool, YOUK_DIR

SKILLS_DIR = Path.home() / ".claude" / "youk" / "skills"
REGISTRY_FILE = SKILLS_DIR / "SKILL-REGISTRY.md"

CAPABILITY_SKILLS = {
    "dev-loop", "code-review", "security-review", "verify",
    "nfr-check", "adr", "learn", "challenge", "write-spec",
}

YOUK_DIR_STR = str(YOUK_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_registry_skills() -> set[str]:
    """Extract skill names from the registry table (rows starting with `| `/name`)."""
    names = set()
    for line in REGISTRY_FILE.read_text().splitlines():
        m = re.match(r"^\|\s+`/([a-z][a-z0-9-]*)`", line)
        if m:
            names.add(m.group(1))
    return names


# ---------------------------------------------------------------------------
# Filesystem checks (no Docker)
# ---------------------------------------------------------------------------

def test_registry_file_exists():
    assert REGISTRY_FILE.exists(), f"SKILL-REGISTRY.md not found at {REGISTRY_FILE}"


def test_registry_parseable():
    skills = _parse_registry_skills()
    assert len(skills) >= 20, f"Registry parsed only {len(skills)} skills — check table format"


def test_every_registry_skill_has_skill_md():
    skills = _parse_registry_skills()
    missing = []
    for name in sorted(skills):
        skill_md = SKILLS_DIR / name / "SKILL.md"
        if not skill_md.exists():
            missing.append(name)
    if missing:
        pytest.xfail(
            f"{len(missing)} skill(s) in SKILL-REGISTRY.md have no SKILL.md "
            f"(known gaps — add or remove from registry):\n"
            + "\n".join(f"  MISSING: skills/{name}/SKILL.md" for name in missing)
        )


def test_no_orphan_skill_directories():
    """Skill directories without SKILL.md are dead weight — warn."""
    registered = _parse_registry_skills()
    orphans = []
    for d in SKILLS_DIR.iterdir():
        if not d.is_dir():
            continue
        if not (d / "SKILL.md").exists():
            continue  # already caught by test above if in registry
        if d.name not in registered:
            orphans.append(d.name)
    # Non-fatal: some dirs (build, check, close, etc.) are intentional workflow aliases
    if orphans:
        pytest.xfail(
            f"Skill dirs with SKILL.md not in registry: {sorted(orphans)}\n"
            "If intentional, add them to SKILL-REGISTRY.md."
        )


# ---------------------------------------------------------------------------
# MCP checks (require Docker)
# ---------------------------------------------------------------------------

def _get_skill_list(sandbox_state) -> list:
    """list_skills returns a list directly (not wrapped in a dict key)."""
    r = call_tool("youk-code:latest", "list_skills", {}, state_dir=sandbox_state)
    # MCP wraps list return as {"_content": [{"type":"text","text":"[...]"}]}
    # or parses directly as a list if JSON
    if isinstance(r, list):
        return r
    if "_content" in r:
        import json
        for block in r["_content"]:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    pass
    # Fallback: may be parsed as {"_raw": "[...]"}
    if "_raw" in r:
        import json
        try:
            return json.loads(r["_raw"])
        except (json.JSONDecodeError, TypeError):
            pass
    return r.get("skills", [])


def test_list_skills_count(sandbox_state):
    skills = _get_skill_list(sandbox_state)
    assert len(skills) >= 20, f"list_skills returned only {len(skills)} skills"


def test_list_skills_contains_capability_skills(sandbox_state):
    skills = _get_skill_list(sandbox_state)
    names = {s if isinstance(s, str) else s.get("name", "") for s in skills}
    missing = CAPABILITY_SKILLS - names
    assert not missing, f"list_skills missing capability skills: {missing}"


def test_route_to_skill_dev_loop(sandbox_state):
    # seed a routing breadcrumb so route_to_skill doesn't gate on missing routing
    import json, datetime
    slug = "checkup-test"
    (sandbox_state / "session-open.json").write_text(json.dumps({"slug": slug}))
    (sandbox_state / "routing-breadcrumb.json").write_text(json.dumps({
        "slug": slug, "size": "M", "task": "test", "ts": datetime.datetime.utcnow().isoformat(),
    }))
    r = call_tool("youk-code:latest", "route_to_skill", {
        "skill": "dev-loop", "task": "implement retry logic",
    }, state_dir=sandbox_state)
    assert r.get("mode") == "in_session", f"Expected mode=in_session, got: {r}"
    assert r.get("skill_content"), "route_to_skill returned empty skill_content"


def test_route_to_skill_code_review(sandbox_state):
    r = call_tool("youk-code:latest", "route_to_skill", {
        "skill": "code-review", "task": "review auth module",
    }, state_dir=sandbox_state)
    assert r.get("mode") == "in_session"
    assert r.get("skill_content")


def test_route_to_skill_unknown_returns_error(sandbox_state):
    try:
        r = call_tool("youk-code:latest", "route_to_skill", {
            "skill": "nonexistent-skill-xyz", "task": "test",
        }, state_dir=sandbox_state)
        # Should return an error field, not crash
        assert "error" in r or "message" in r, (
            f"route_to_skill('nonexistent') should return error, got: {r}"
        )
    except RuntimeError:
        pass  # MCP-level error is also acceptable
