"""S11: the always-on context stays small and the lean arm matches what the installer ships."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parent.parent
TOTAL_BUDGET_TOKENS = 3000      # G2 target for always-on text
MAX_DESCRIPTION_WORDS = 25
MAX_LEAN_LINES = 15
MAX_AGENTS_LINES = 10


def _frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
    return yaml.safe_load(match.group(1))


def test_every_skill_description_fits_the_word_limit():
    too_long = {}
    for path in sorted((REPO / "skills").glob("*/SKILL.md")):
        words = len(str(_frontmatter(path)["description"]).split())
        if words > MAX_DESCRIPTION_WORDS:
            too_long[path.parent.name] = words
    assert not too_long, f"descriptions over {MAX_DESCRIPTION_WORDS} words: {too_long}"


def test_internal_development_notes_are_not_listed_as_skills():
    assert not (REPO / "skills" / "compaction").exists()
    assert not (REPO / "skills" / "session").exists()
    assert (REPO / "docs" / "internal" / "compaction-patterns.md").is_file()
    assert (REPO / "docs" / "internal" / "session-patterns.md").is_file()


def test_the_lean_context_is_short_and_the_installer_ships_it():
    lean = (REPO / "bench" / "arms" / "lean" / "context.md").read_text().strip()
    assert len(lean.splitlines()) <= MAX_LEAN_LINES
    assert lean in (REPO / "docs" / "claude-md-template.md").read_text()


def test_agents_md_stays_short():
    assert len((REPO / "AGENTS.md").read_text().strip().splitlines()) <= MAX_AGENTS_LINES


def test_the_full_arm_keeps_its_frozen_text():
    full = (REPO / "bench" / "arms" / "full" / "CLAUDE.md").read_text()
    assert "route_task" in full and len(full) > 5000     # the pre-slimming instruction set


def test_total_always_on_tokens_are_under_the_g2_target():
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import footprint
    total = footprint.measure(REPO)["total_tokens"]
    assert total <= TOTAL_BUDGET_TOKENS, f"{total} tokens always on, target {TOTAL_BUDGET_TOKENS}"
