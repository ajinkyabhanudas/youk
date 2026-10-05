"""The always-on footprint can only go down.

bench/footprint-baseline.json is the budget. A change that grows the CLAUDE.md template,
AGENTS.md or any skill description fails here until the growth is removed or the baseline
is deliberately raised in the same change (python3 scripts/footprint.py --write-baseline),
which puts the decision in the diff where a reviewer sees it.
"""
from __future__ import annotations

import json
from pathlib import Path

import footprint

REPO = Path(__file__).parent.parent


def _skill(dir_: Path, name: str, description: str) -> None:
    (dir_ / name).mkdir(parents=True)
    (dir_ / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\n---\nBody text.\n")


class TestTheRealRepoStaysWithinBudget:
    def test_baseline_is_committed_and_well_formed(self):
        baseline = json.loads(footprint.BASELINE.read_text())
        assert set(footprint.RATCHETED) <= set(baseline["sources"])
        assert baseline["total_tokens"] == sum(baseline["sources"][k] for k in footprint.RATCHETED)

    def test_no_ratcheted_source_exceeds_the_baseline(self):
        baseline = json.loads(footprint.BASELINE.read_text())
        problems = footprint.check(footprint.measure(REPO), baseline)
        assert not problems, (
            f"{problems}. Trim the growth, or run scripts/footprint.py --write-baseline "
            "in this change if the increase is deliberate."
        )


class TestMeasurement:
    def test_folded_multiline_description_is_counted_once_without_newlines(self, tmp_path):
        _skill(tmp_path, "alpha", "one two\n  three four")
        assert footprint.skill_descriptions(tmp_path) == {"alpha": len("one two three four")}

    def test_skill_without_frontmatter_counts_zero(self, tmp_path):
        (tmp_path / "bare").mkdir()
        (tmp_path / "bare" / "SKILL.md").write_text("no frontmatter here")
        assert footprint.skill_descriptions(tmp_path) == {"bare": 0}

    def test_growing_a_description_is_flagged(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "servers").mkdir(parents=True)
        _skill(repo / "skills", "alpha", "short")
        small = footprint.measure(repo)
        _skill(repo / "skills", "beta", "x" * 400)
        big = footprint.measure(repo)
        problems = footprint.check(big, small)
        assert problems and "skill_descriptions" in problems[0]

    def test_shrinking_is_not_flagged(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "servers").mkdir(parents=True)
        _skill(repo / "skills", "alpha", "x" * 400)
        big = footprint.measure(repo)
        _skill(repo / "skills", "beta", "y")
        (repo / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: s\n---\n")
        assert footprint.check(footprint.measure(repo), big) == []

    def test_mcp_docstrings_are_counted_per_tool(self, tmp_path):
        server = tmp_path / "servers" / "core" / "src"
        server.mkdir(parents=True)
        (server / "server.py").write_text(
            'import x\n@mcp.tool()\ndef a():\n    """twelve chars"""\n@mcp.tool()\n'
            'def b():\n    """four"""\ndef c():\n    """not a tool"""\n')
        assert footprint.mcp_docstring_chars(tmp_path / "servers") == (2, 16)
