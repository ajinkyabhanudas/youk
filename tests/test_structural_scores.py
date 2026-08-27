"""Structural health must reach Langfuse, and must not carry session content.

patch_cycle_rate was the only score on a run trace. It describes repair churn and says
nothing about whether youk is intact, which is why org_score sat at 9.3 across 88
sessions while route_task returned schema-invalid output and 14 routed skills could not
load. Nothing that moved would have shown up on a chart.

These are the three signals that would have moved: unloadable routes, repo skills
unreachable at runtime, and docs that contradict their authority.

ADR-011 applies. A skill name and a doc path are session content, so only counts cross
the boundary, and the tests below hold that line.
"""
from __future__ import annotations

import session as session_mod


class _RecordingObs:
    def __init__(self):
        self.scores: list[dict] = []

    def attach_score_by_id(self, trace_id, name, value, comment=""):
        self.scores.append(
            {"trace_id": trace_id, "name": name, "value": value, "comment": comment}
        )


def _install(tmp_path, routed: list[str], repo: list[str]):
    claude, youk = tmp_path / "claude", tmp_path / "youk"
    (claude / "skills").mkdir(parents=True)
    (claude / "CLAUDE.md").write_text(
        'route_to_skill("challenge", t) route_to_skill("coverage-tree", t)'
    )
    for s in routed:
        (claude / "skills" / s).mkdir()
        (claude / "skills" / s / "SKILL.md").write_text(f"# {s}\n")
    (youk / "skills").mkdir(parents=True)
    for s in repo:
        (youk / "skills" / s).mkdir()
    return youk, claude


def _run(tmp_path, monkeypatch, routed, repo) -> _RecordingObs:
    youk, claude = _install(tmp_path, routed, repo)
    monkeypatch.setattr(session_mod, "YOUK_ROOT", youk)
    import skill_route_check
    import skill_link_check

    real_routes = skill_route_check.check_skill_routes
    real_links = skill_link_check.check_skill_links
    monkeypatch.setattr(
        skill_route_check, "check_skill_routes",
        lambda c, y=None: real_routes(claude, youk))
    monkeypatch.setattr(
        skill_link_check, "check_skill_links",
        lambda y, c: real_links(youk, claude))

    obs = _RecordingObs()
    session_mod._attach_structural_scores(obs, "trace-1")
    return obs


class TestStructuralSignalsAreEmitted:
    def test_broken_route_is_scored(self, tmp_path, monkeypatch):
        obs = _run(tmp_path, monkeypatch, ["challenge"], ["challenge", "coverage-tree"])
        routes = [s for s in obs.scores if s["name"] == "routes_broken"]
        assert routes and routes[0]["value"] == 1.0

    def test_healthy_routes_score_zero_not_absent(self, tmp_path, monkeypatch):
        """Zero must be emitted. An absent metric cannot be charted as recovery."""
        obs = _run(
            tmp_path, monkeypatch,
            ["challenge", "coverage-tree"], ["challenge", "coverage-tree"],
        )
        routes = [s for s in obs.scores if s["name"] == "routes_broken"]
        assert routes and routes[0]["value"] == 0.0

    def test_unlinked_skills_are_scored(self, tmp_path, monkeypatch):
        obs = _run(
            tmp_path, monkeypatch,
            ["challenge", "coverage-tree"], ["challenge", "coverage-tree", "orphan"],
        )
        links = [s for s in obs.scores if s["name"] == "skills_unlinked"]
        assert links and links[0]["value"] == 1.0

    def test_all_scores_are_numeric(self, tmp_path, monkeypatch):
        obs = _run(tmp_path, monkeypatch, ["challenge"], ["challenge"])
        assert obs.scores
        for s in obs.scores:
            assert isinstance(s["value"], float)


class TestNoSessionContentLeaks:
    """ADR-011 at the score boundary."""

    def test_skill_names_do_not_appear_in_scores(self, tmp_path, monkeypatch):
        obs = _run(
            tmp_path, monkeypatch,
            ["challenge"], ["challenge", "coverage-tree", "secret-client-skill"],
        )
        flat = repr(obs.scores)
        assert "secret-client-skill" not in flat
        assert "coverage-tree" not in flat

    def test_no_filesystem_paths_in_scores(self, tmp_path, monkeypatch):
        obs = _run(tmp_path, monkeypatch, ["challenge"], ["challenge"])
        flat = repr(obs.scores)
        assert str(tmp_path) not in flat
        assert "/Users" not in flat


class TestNeverFailsTheSession:
    def test_missing_roots_emit_nothing_and_do_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(session_mod, "YOUK_ROOT", tmp_path / "gone")
        obs = _RecordingObs()
        session_mod._attach_structural_scores(obs, "trace-1")
        assert isinstance(obs.scores, list)

    def test_raising_obs_is_swallowed(self, tmp_path, monkeypatch):
        class _Boom:
            def attach_score_by_id(self, *a, **kw):
                raise RuntimeError("langfuse down")

        monkeypatch.setattr(session_mod, "YOUK_ROOT", tmp_path)
        session_mod._attach_structural_scores(_Boom(), "trace-1")
