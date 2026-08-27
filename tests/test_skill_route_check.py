"""Tests for skill route resolution.

Guards the failure that went undetected for weeks: 14 skills committed to the repo,
routed to by CLAUDE.md, with no runtime symlink. route_to_skill could not load any of
them, and three checks named for contracts and audits all stayed green.

Every test that asserts a pass also has a sibling proving the check fails on the
corresponding broken state, per verify bar 7.
"""
from __future__ import annotations

from pathlib import Path

from skill_route_check import _referenced_skills, check_skill_routes


def _make(root: Path, claude_md: str, skills: list[str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CLAUDE.md").write_text(claude_md)
    (root / "skills").mkdir(exist_ok=True)
    for s in skills:
        (root / "skills" / s).mkdir(exist_ok=True)
        (root / "skills" / s / "SKILL.md").write_text(f"# {s}\n\nreal content\n")
    return root


_MD = 'Call route_to_skill("challenge", task) then route_to_skill("coverage-tree", task).'


class TestDetectsUnloadableRoutes:
    def test_missing_skill_is_unresolvable(self, tmp_path):
        r = check_skill_routes(_make(tmp_path / "c", _MD, ["challenge"]))
        assert r["unresolvable"] == ["coverage-tree"]
        assert r["healthy"] is False

    def test_all_present_is_healthy(self, tmp_path):
        r = check_skill_routes(_make(tmp_path / "c", _MD, ["challenge", "coverage-tree"]))
        assert r["unresolvable"] == []
        assert r["healthy"] is True
        assert r["message"] == ""

    def test_message_names_skill_and_remedy(self, tmp_path):
        msg = check_skill_routes(_make(tmp_path / "c", _MD, ["challenge"]))["message"]
        assert "coverage-tree" in msg
        assert "install.sh" in msg

    def test_empty_skill_md_is_reported_separately(self, tmp_path):
        """An empty file is an authoring problem, not an install problem."""
        root = _make(tmp_path / "c", _MD, ["challenge", "coverage-tree"])
        (root / "skills" / "coverage-tree" / "SKILL.md").write_text("   \n")
        r = check_skill_routes(root)
        assert r["empty"] == ["coverage-tree"]
        assert r["unresolvable"] == []
        assert r["healthy"] is False

    def test_dangling_symlink_counts_as_unresolvable(self, tmp_path):
        """This is exactly what a stale install looks like."""
        root = _make(tmp_path / "c", _MD, ["challenge"])
        (root / "skills" / "coverage-tree").mkdir()
        (root / "skills" / "coverage-tree" / "SKILL.md").symlink_to(tmp_path / "gone")
        assert check_skill_routes(root)["unresolvable"] == ["coverage-tree"]


class TestOnlyExplicitRoutesAreParsed:
    """Slash commands are prose and must not be inferred as routes.

    Parsing them produced three false positives on real data: compact-context and
    route-task are MCP tools, and "full" came from `/explain → full depth, filler-free`.
    """

    def test_slash_commands_are_ignored(self, tmp_path):
        md = "Use /explain for depth. /health runs self_heal(). /forge → skill-forge"
        assert _referenced_skills_from(tmp_path, md) == set()

    def test_mcp_tool_calls_are_not_routes(self, tmp_path):
        md = "Call compact_context(project_dir) and route_task(task)."
        assert _referenced_skills_from(tmp_path, md) == set()

    def test_explicit_route_is_parsed(self, tmp_path):
        md = 'route_to_skill("dev-loop", task)'
        assert _referenced_skills_from(tmp_path, md) == {"dev-loop"}

    def test_underscore_spelling_normalizes(self, tmp_path):
        """route_to_skill('nfr_check') loads the nfr-check directory."""
        md = 'route_to_skill("nfr_check", task)'
        assert _referenced_skills_from(tmp_path, md) == {"nfr-check"}

    def test_single_quotes_are_parsed(self, tmp_path):
        assert _referenced_skills_from(tmp_path, "route_to_skill('verify', t)") == {"verify"}


class TestDegradesSafely:
    def test_missing_claude_md_is_not_a_failure(self, tmp_path):
        (tmp_path / "skills").mkdir(parents=True)
        r = check_skill_routes(tmp_path)
        assert r["healthy"] is True
        assert r["checked"] == 0

    def test_no_routes_found_is_not_a_failure(self, tmp_path):
        r = check_skill_routes(_make(tmp_path / "c", "no routes here", []))
        assert r["healthy"] is True
        assert r["checked"] == 0

    def test_never_raises_on_garbage(self, tmp_path):
        root = _make(tmp_path / "c", _MD, [])
        (root / "skills").rmdir()
        assert check_skill_routes(root)["checked"] >= 0


def _referenced_skills_from(tmp_path: Path, md: str) -> set[str]:
    f = tmp_path / f"CLAUDE_{abs(hash(md))}.md"
    f.write_text(md)
    return _referenced_skills(f)


class TestHealthWiring:
    """Covers the glue joining both structural checks to the health report.

    Both were inline try/except blocks no test reached. The modules had dedicated
    tests; the wiring had none, which is how adding the second one pushed health.py
    under its coverage floor without any behaviour being untested in isolation.
    """

    @staticmethod
    def _roots(tmp_path, routed_skills: list[str], repo_skills: list[str]):
        claude, youk = tmp_path / "claude", tmp_path / "youk"
        _make(claude, _MD, routed_skills)
        (youk / "skills").mkdir(parents=True)
        for s in repo_skills:
            (youk / "skills" / s).mkdir()
        return youk, claude

    def test_route_failure_surfaces_as_a_finding(self, tmp_path):
        from health import _structural_skill_findings

        youk, claude = self._roots(tmp_path, ["challenge"], ["challenge", "coverage-tree"])
        findings = _structural_skill_findings(youk, claude)
        assert any("coverage-tree" in f for f in findings)

    def test_healthy_install_produces_no_findings(self, tmp_path):
        from health import _structural_skill_findings

        youk, claude = self._roots(
            tmp_path, ["challenge", "coverage-tree"], ["challenge", "coverage-tree"]
        )
        assert _structural_skill_findings(youk, claude) == []

    def test_link_drift_surfaces_as_a_finding(self, tmp_path):
        """A repo skill with no runtime counterpart is reported even if no route names it."""
        from health import _structural_skill_findings

        youk, claude = self._roots(
            tmp_path, ["challenge", "coverage-tree"], ["challenge", "coverage-tree", "orphan-x"]
        )
        assert any("orphan-x" in f for f in _structural_skill_findings(youk, claude))

    def test_never_raises_on_missing_roots(self, tmp_path):
        """A health check must not be able to fail a session."""
        from health import _structural_skill_findings

        assert _structural_skill_findings(tmp_path / "nope", tmp_path / "gone") == []
