"""Tests for translation_risk="medium" soft block in route_task.

PR-1 of L9 gap closure: medium-risk translations are flagged with a warning
and a state file, but NOT blocked (blocked=False). task_checkpoint surfaces
the unsurfaced flag if mark_medium_risk_surfaced was never called.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest


@pytest.fixture
def routing_root(tmp_path, monkeypatch):
    """Isolated YOUK_ROOT for routing tests."""
    root = tmp_path / "youk"
    (root / "state").mkdir(parents=True)

    import routing
    import state_paths
    monkeypatch.setattr(routing, "YOUK_ROOT", root)
    monkeypatch.setattr(state_paths, "YOUK_ROOT", root)
    return root


def _make_intent_brief(translation_risk: str, question: str = "") -> dict:
    return {
        "ambiguity_detected": False,
        "estimated_size": "M",
        "goal_translation": {
            "stated_as": "make this elite",
            "interpreted_as": "refactor auth module",
            "observable_outcome": "faster auth",
            "translation_risk": translation_risk,
            "translation_question": question or None,
        },
    }


def _call_route_task(task: str, intent_brief: dict, slug: str = "", routing_root: Path | None = None):
    from routing import route_task
    return route_task(task, intent_brief=intent_brief, slug=slug)


class TestMediumRiskWarning:
    def test_medium_risk_adds_warning_not_blocked(self, routing_root):
        brief = _make_intent_brief("medium", "What does success look like?")
        result = _call_route_task("refactor the auth module", brief, slug="test-proj")
        assert result.blocked is False
        warning_ids = [w.rule_id for w in result.warnings]
        assert "medium-translation-risk" in warning_ids

    def test_medium_risk_warning_carries_question(self, routing_root):
        q = "What would you observe that tells you this worked?"
        brief = _make_intent_brief("medium", q)
        result = _call_route_task("refactor the auth module", brief, slug="test-proj")
        warning = next(w for w in result.warnings if w.rule_id == "medium-translation-risk")
        assert q in warning.message

    def test_medium_risk_uses_default_question_when_none(self, routing_root):
        brief = _make_intent_brief("medium", "")
        result = _call_route_task("add caching layer", brief, slug="test-proj")
        warning = next(w for w in result.warnings if w.rule_id == "medium-translation-risk")
        assert "successful outcome" in warning.message.lower()

    def test_medium_risk_writes_state_file_surfaced_false(self, routing_root):
        brief = _make_intent_brief("medium", "What does success mean here?")
        _call_route_task("add feature X", brief, slug="test-proj")
        # State file should exist somewhere under state/
        state_files = list(routing_root.rglob("medium-risk-question.json"))
        assert state_files, "medium-risk-question.json not written"
        data = json.loads(state_files[0].read_text())
        assert data["surfaced"] is False
        assert data["question"]

    def test_high_risk_still_blocks(self, routing_root):
        brief = _make_intent_brief("high", "What do you mean by elite?")
        result = _call_route_task("make auth elite", brief, slug="test-proj")
        assert result.blocked is True
        assert result.collapsing_question

    def test_no_medium_risk_warning_for_xs_tasks(self, routing_root):
        brief = {
            "ambiguity_detected": False,
            "estimated_size": "XS",
            "goal_translation": {
                "stated_as": "fix typo",
                "interpreted_as": "fix typo",
                "observable_outcome": "typo fixed",
                "translation_risk": "medium",
                "translation_question": None,
            },
        }
        result = _call_route_task("fix typo in README", brief, slug="test-proj")
        warning_ids = [w.rule_id for w in result.warnings]
        assert "medium-translation-risk" not in warning_ids

    def test_none_translation_risk_no_warning(self, routing_root):
        brief = _make_intent_brief("none")
        result = _call_route_task("add logging to auth module", brief, slug="test-proj")
        warning_ids = [w.rule_id for w in result.warnings]
        assert "medium-translation-risk" not in warning_ids


class TestMediumRiskCheckpoint:
    def _prime_session_state(self, youk_root: Path, project_dir: Path) -> str:
        """Write session.json with last_project so _slug() resolves correctly. Returns slug."""
        import session as _session
        slug = _session._slug(str(project_dir))
        state_file = youk_root / "state" / "session.json"
        state_file.write_text(json.dumps({
            "session_counter": 1,
            "last_project": str(project_dir),
            "last_head": "",
        }))
        return slug

    def _write_mrq(self, youk_root: Path, slug: str, surfaced: bool, question: str = "What does success look like?") -> None:
        """Write medium-risk-question.json to the slug-scoped state dir."""
        slug_dir = youk_root / "state" / "sessions" / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        (slug_dir / "medium-risk-question.json").write_text(json.dumps({
            "question": question,
            "surfaced": surfaced,
            "written_at": "2026-01-01T00:00:00",
        }))

    def test_task_checkpoint_flags_unsurfaced_question(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")

        project_dir = youk_root
        slug = self._prime_session_state(youk_root, project_dir)
        self._write_mrq(youk_root, slug, surfaced=False)

        result = session.task_checkpoint(str(project_dir), "add feature X", size="M")
        assert result.get("medium_risk_unsurfaced") is True
        assert result.get("medium_risk_question") == "What does success look like?"

    def test_task_checkpoint_clean_when_surfaced(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")

        project_dir = youk_root
        slug = self._prime_session_state(youk_root, project_dir)
        self._write_mrq(youk_root, slug, surfaced=True)

        result = session.task_checkpoint(str(project_dir), "add feature X", size="M")
        assert "medium_risk_unsurfaced" not in result

    def test_task_checkpoint_no_flag_for_xs_tasks(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")

        project_dir = youk_root
        slug = self._prime_session_state(youk_root, project_dir)
        self._write_mrq(youk_root, slug, surfaced=False, question="Does not matter")

        result = session.task_checkpoint(str(project_dir), "fix typo", size="XS")
        assert "medium_risk_unsurfaced" not in result
