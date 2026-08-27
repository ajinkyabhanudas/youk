"""org_score must not report health while youk itself is broken.

The gap this closes, stated plainly: self_heal reported org_score 9.3 across 88
sessions while route_task returned schema-invalid output on nearly every call, 14
routed skills could not load, and importing server.py wrote to disk. All twelve of
its findings were usage telemetry — invocation rate, autonomy, loop-dry rate. None
observed whether youk worked.

README line 80 claims youk "verifies the capabilities it built are actually running
in the real loop". Without this gate that claim was false, and the claim itself is
why nobody looked: it sounded like the check already existed.

Capping rather than subtracting is deliberate. A broken skill is simply never invoked,
which nudges the invocation rate down by a fraction and reads as developer choice. A
subtracted term lets a high invocation rate mask a dead capability; a ceiling cannot
be out-earned.
"""
from __future__ import annotations

from pathlib import Path

from health import _CAP_LINK_DRIFT, _CAP_ROUTES_BROKEN, _structural_integrity_cap

_MD = 'route_to_skill("challenge", task) and route_to_skill("coverage-tree", task)'


def _install(tmp_path, routed: list[str], repo: list[str]) -> tuple[Path, Path]:
    claude, youk = tmp_path / "claude", tmp_path / "youk"
    (claude / "skills").mkdir(parents=True)
    (claude / "CLAUDE.md").write_text(_MD)
    for s in routed:
        (claude / "skills" / s).mkdir()
        (claude / "skills" / s / "SKILL.md").write_text(f"# {s}\ncontent\n")
    (youk / "skills").mkdir(parents=True)
    for s in repo:
        (youk / "skills" / s).mkdir()
    return youk, claude


class TestCapsWhenStructureIsBroken:
    def test_unloadable_route_caps_score(self, tmp_path):
        """The pre-#89 state: coverage-tree routed to, no runtime symlink."""
        youk, claude = _install(tmp_path, ["challenge"], ["challenge", "coverage-tree"])
        cap, reasons = _structural_integrity_cap(youk, claude)
        assert cap == _CAP_ROUTES_BROKEN
        assert any("coverage-tree" in r for r in reasons)

    def test_link_drift_alone_caps_lower_than_broken_route(self, tmp_path):
        """Degraded, not broken: the skill exists in the repo, just is not linked."""
        youk, claude = _install(
            tmp_path, ["challenge", "coverage-tree"], ["challenge", "coverage-tree", "extra"]
        )
        cap, reasons = _structural_integrity_cap(youk, claude)
        assert cap == _CAP_LINK_DRIFT
        assert any("extra" in r for r in reasons)

    def test_broken_route_wins_over_link_drift(self, tmp_path):
        """Both failing takes the stricter ceiling."""
        youk, claude = _install(tmp_path, ["challenge"], ["challenge", "coverage-tree", "extra"])
        cap, _ = _structural_integrity_cap(youk, claude)
        assert cap == _CAP_ROUTES_BROKEN

    def test_empty_skill_md_caps_as_broken(self, tmp_path):
        youk, claude = _install(
            tmp_path, ["challenge", "coverage-tree"], ["challenge", "coverage-tree"]
        )
        (claude / "skills" / "coverage-tree" / "SKILL.md").write_text("  \n")
        cap, _ = _structural_integrity_cap(youk, claude)
        assert cap == _CAP_ROUTES_BROKEN


class TestNoCapWhenHealthy:
    def test_healthy_install_has_no_cap(self, tmp_path):
        youk, claude = _install(
            tmp_path, ["challenge", "coverage-tree"], ["challenge", "coverage-tree"]
        )
        cap, reasons = _structural_integrity_cap(youk, claude)
        assert cap is None
        assert reasons == []

    def test_missing_roots_do_not_cap(self, tmp_path):
        """A health check must not be able to fail a session, or punish a fresh install."""
        cap, reasons = _structural_integrity_cap(tmp_path / "nope", tmp_path / "gone")
        assert cap is None
        assert reasons == []

    def test_no_routes_declared_does_not_cap(self, tmp_path):
        claude, youk = tmp_path / "c", tmp_path / "y"
        (claude / "skills").mkdir(parents=True)
        (claude / "CLAUDE.md").write_text("no routes here")
        (youk / "skills").mkdir(parents=True)
        assert _structural_integrity_cap(youk, claude)[0] is None


class TestCapCannotBeOutEarned:
    def test_ceiling_beats_a_perfect_behavioural_score(self, tmp_path):
        """The actual regression: 9.3 while broken.

        Proves a ceiling, not a subtraction. A near-perfect behavioural score still
        lands at the cap, so a high invocation rate cannot mask a dead capability.
        """
        youk, claude = _install(tmp_path, ["challenge"], ["challenge", "coverage-tree"])
        cap, _ = _structural_integrity_cap(youk, claude)
        perfect_behavioural_score = 9.3
        assert min(perfect_behavioural_score, cap) == _CAP_ROUTES_BROKEN

    def test_cap_constants_are_ordered(self):
        """Broken must always be stricter than degraded."""
        assert _CAP_ROUTES_BROKEN < _CAP_LINK_DRIFT
