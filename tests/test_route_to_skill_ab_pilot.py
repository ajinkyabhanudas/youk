"""Tests for the A/B pilot wiring in route_to_skill.

Covers the gap between "assign_variant works in isolation" (test_ab_experiments.py)
and "route_to_skill actually returns divergent rationale text" — the claim the smoke
test proved manually against the live deployed container. These pin the same
behaviour so it stays proven after the manual check is forgotten.

Also covers the LOW objection challenge raised before this was built: adding
rationale_why_terse must not disturb the existing suppress-after-N-preemptions flow,
which is a separate, orthogonal mechanism (WHETHER a rationale shows) from the pilot
(WHICH TEXT shows when it does).
"""
from __future__ import annotations

import json

import pytest

import skills


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point every module constant at tmp_path and force state writable."""
    monkeypatch.setattr(skills, "YOUK_ROOT", tmp_path)
    monkeypatch.setattr(skills, "_YOUK_ROOT", tmp_path)
    monkeypatch.setattr(skills, "_SESSION_STATE", tmp_path / "state" / "session.json")
    monkeypatch.setattr(skills, "_RATIONALE_STATE", tmp_path / "state" / "skill-rationale-state.json")
    monkeypatch.setattr(skills, "_SKILL_GRAPH", tmp_path / "knowledge" / "skill-graph.yaml")
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(skills, "_STATE_WRITABLE", True)

    import skill_loader
    monkeypatch.setattr(skill_loader, "CLAUDE_ROOT", tmp_path)
    monkeypatch.setattr(skill_loader, "SKILLS_DIR", tmp_path / "skills")
    yield


def _write_skill(root, name: str, frontmatter: dict, body: str = "Body text.\n"):
    d = root / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f'{k}: "{v}"')
    lines.append("---")
    lines.append(body)
    (d / "SKILL.md").write_text("\n".join(lines))


class TestPilotVariantSelection:
    def test_control_and_treatment_return_different_text(self, tmp_path, monkeypatch):
        _write_skill(tmp_path, "nfr-check", {
            "rationale_why": "The full sentence.",
            "rationale_why_terse": "[nfr-check] terse.",
        })
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})

        # Find one slug for each variant deterministically.
        from ab_experiments import assign_variant
        control = next(s for s in (f"s{i}" for i in range(50))
                       if assign_variant(s, "exp-1") == "control")
        treatment = next(s for s in (f"s{i}" for i in range(50))
                         if assign_variant(s, "exp-1") == "treatment")

        monkeypatch.setattr(skills, "_get_current_slug", lambda: control)
        r1 = skills.route_to_skill("nfr-check", "task")
        monkeypatch.setattr(skills, "_get_current_slug", lambda: treatment)
        r2 = skills.route_to_skill("nfr-check", "task")

        assert r1["ab_variant"] == "control"
        assert r2["ab_variant"] == "treatment"
        assert r1["rationale"] != r2["rationale"]
        assert r1["rationale"] == "The full sentence."
        assert r2["rationale"] == "[nfr-check] terse."

    def test_falls_back_to_control_when_terse_field_absent(self, tmp_path, monkeypatch):
        """A skill can be added to the pilot before its terse text is authored."""
        _write_skill(tmp_path, "nfr-check", {"rationale_why": "Only the full sentence."})
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})
        monkeypatch.setattr(skills, "_get_current_slug", lambda: "any-session")

        r = skills.route_to_skill("nfr-check", "task")
        assert r["ab_variant"] in ("control", "treatment")
        assert r["rationale"] == "Only the full sentence."
        if r["ab_variant"] == "treatment":
            # Fallback occurred; logged variant must reflect what was actually shown.
            pass  # covered by the exposure-log test below

    def test_non_pilot_skill_gets_no_variant(self, tmp_path, monkeypatch):
        _write_skill(tmp_path, "some-other-skill", {"rationale_why": "Text."})
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})
        monkeypatch.setattr(skills, "_get_current_slug", lambda: "s1")

        r = skills.route_to_skill("some-other-skill", "task")
        assert r["ab_variant"] is None
        assert r["rationale"] == "Text."

    def test_exposure_is_logged_with_the_actual_shown_variant(self, tmp_path, monkeypatch):
        """When the terse field is absent, the fallback must log 'control', not
        whatever assign_variant originally drew — the log must reflect reality."""
        _write_skill(tmp_path, "nfr-check", {"rationale_why": "Only full."})
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})

        from ab_experiments import assign_variant, read_exposures
        treatment_slug = next(s for s in (f"s{i}" for i in range(50))
                              if assign_variant(s, "exp-1") == "treatment")
        monkeypatch.setattr(skills, "_get_current_slug", lambda: treatment_slug)

        r = skills.route_to_skill("nfr-check", "task")
        assert r["ab_variant"] == "control"  # fell back, no terse field exists

        records = read_exposures(tmp_path, "exp-1")
        assert len(records) == 1
        assert records[0]["variant"] == "control"


class TestSuppressionIsUnaffected:
    """The existing 'stop showing rationale after N preemptions' mechanism is
    orthogonal to which text is shown and must keep working unchanged."""

    def test_suppressed_skill_shows_no_rationale_regardless_of_variant(self, tmp_path, monkeypatch):
        _write_skill(tmp_path, "nfr-check", {
            "rationale_why": "Full.", "rationale_why_terse": "Terse.",
        })
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})
        monkeypatch.setattr(skills, "_get_current_slug", lambda: "s1")

        state_file = tmp_path / "state" / "skill-rationale-state.json"
        state_file.write_text(json.dumps({"nfr-check": {"shown_count": 3, "suppressed": True}}))

        r = skills.route_to_skill("nfr-check", "task")
        assert r["rationale"] is None
        assert r["rationale_suppressed"] is True
        assert r["ab_variant"] is None  # never assigned; suppressed short-circuits first

    def test_shown_count_still_increments_for_pilot_skills(self, tmp_path, monkeypatch):
        _write_skill(tmp_path, "nfr-check", {
            "rationale_why": "Full.", "rationale_why_terse": "Terse.",
        })
        monkeypatch.setattr(skills, "_AB_PILOT_SKILLS", {"nfr-check": "exp-1"})
        monkeypatch.setattr(skills, "_get_current_slug", lambda: "s1")

        skills.route_to_skill("nfr-check", "task")
        state = json.loads((tmp_path / "state" / "skill-rationale-state.json").read_text())
        assert state["nfr-check"]["shown_count"] == 1
