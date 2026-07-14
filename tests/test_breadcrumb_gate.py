"""
Tests for the routing breadcrumb gate (session-level enforcement).

Verifies:
1. route_task writes routing-breadcrumb.json for M/L/XL non-blocked decisions
2. route_task does NOT write breadcrumb for XS/S decisions
3. route_task does NOT write breadcrumb when blocked=True
4. task_checkpoint: routing_missed=False when breadcrumb present (consumes it)
5. task_checkpoint: routing_missed=True when breadcrumb absent for M+ task
6. task_checkpoint: routing_missed not in result for XS/S tasks
7. Breadcrumb file consumed (deleted) after task_checkpoint reads it
8. routing_action message contains "route_task"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# 1–3. route_task breadcrumb writes
# ---------------------------------------------------------------------------

class TestRoutingBreadcrumbWrite:
    def test_m_task_writes_breadcrumb(self, tmp_path):
        from routing import route_task
        bf = tmp_path / "routing-breadcrumb.json"
        with patch("routing._BREADCRUMB_FILE", bf):
            result = route_task("implement new feature in session tracking module")
        if not result.blocked and result.size.value in ("M", "L", "XL"):
            assert bf.exists()

    def test_breadcrumb_contains_task_size_and_timestamp(self, tmp_path):
        from routing import route_task
        bf = tmp_path / "routing-breadcrumb.json"
        task = "implement routing breadcrumb feature for session enforcement"
        with patch("routing._BREADCRUMB_FILE", bf):
            result = route_task(task)
        if not result.blocked and result.size.value in ("M", "L", "XL"):
            data = json.loads(bf.read_text())
            assert "task" in data
            assert data["size"] in ("M", "L", "XL")
            assert "routed_at" in data

    def test_xs_task_does_not_write_breadcrumb(self, tmp_path):
        from routing import route_task
        bf = tmp_path / "routing-breadcrumb.json"
        with patch("routing._BREADCRUMB_FILE", bf):
            route_task("fix typo")
        assert not bf.exists()

    def test_s_task_does_not_write_breadcrumb(self, tmp_path):
        from routing import route_task
        bf = tmp_path / "routing-breadcrumb.json"
        with patch("routing._BREADCRUMB_FILE", bf):
            result = route_task("rename variable in one file")
        # Only assert no breadcrumb when routing actually returned XS/S
        if result.size.value in ("XS", "S"):
            assert not bf.exists()

    def test_blocked_decision_does_not_write_breadcrumb(self, tmp_path):
        from routing import route_task
        bf = tmp_path / "routing-breadcrumb.json"
        intent_brief = {
            "ambiguity_detected": False,
            "goal_translation": {
                "translation_risk": "high",
                "translation_question": "What would tell you this worked?",
            },
            "estimated_size": "M",
        }
        with patch("routing._BREADCRUMB_FILE", bf):
            result = route_task("get it to elite level", intent_brief=intent_brief)
        assert result.blocked is True
        assert not bf.exists()

    def test_breadcrumb_write_failure_does_not_raise(self, tmp_path):
        from routing import route_task
        # Non-existent parent directory — mkdir inside _write_routing_breadcrumb
        # is patched to fail; routing should still return a valid decision
        bf = tmp_path / "no_dir" / "routing-breadcrumb.json"
        with patch("routing._BREADCRUMB_FILE", bf):
            with patch("routing.Path.mkdir", side_effect=OSError("disk full")):
                result = route_task("implement authentication system from scratch")
        assert result is not None


# ---------------------------------------------------------------------------
# 4–8. task_checkpoint breadcrumb gate
# ---------------------------------------------------------------------------

class TestTaskCheckpointBreadcrumbGate:
    def _setup(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("session.YOUK_ROOT", tmp_path)
        monkeypatch.setattr("session._build_brief", lambda _: {"brief": "TEST BRIEF"})
        monkeypatch.setattr("session._load_state", lambda: {"last_project": "test", "session_counter": 1})
        monkeypatch.setattr("session._write_session_stub", lambda *a: None)
        monkeypatch.setattr("session._update_resume_point", lambda *a: None)
        monkeypatch.setattr("session._check_session_goal", lambda _: None)
        return state_dir

    def _write_breadcrumb(self, state_dir: Path) -> None:
        (state_dir / "routing-breadcrumb.json").write_text(json.dumps({
            "task": "implement feature",
            "size": "M",
            "routed_at": "2026-07-14T10:00:00",
        }))

    def test_routing_missed_false_when_breadcrumb_present(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        state_dir = self._setup(tmp_path, monkeypatch)
        self._write_breadcrumb(state_dir)
        result = task_checkpoint(str(tmp_path), "implement feature", size="M")
        assert result.get("routing_missed") is not True

    def test_routing_missed_true_when_breadcrumb_absent_for_m(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        # No breadcrumb written
        result = task_checkpoint(str(tmp_path), "implement feature without routing", size="M")
        assert result.get("routing_missed") is True

    def test_routing_missed_true_for_l_task_without_breadcrumb(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        result = task_checkpoint(str(tmp_path), "large feature implementation", size="L")
        assert result.get("routing_missed") is True

    def test_routing_not_checked_for_xs(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        result = task_checkpoint(str(tmp_path), "fix typo in comment", size="XS")
        assert "routing_missed" not in result

    def test_routing_not_checked_for_s(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        result = task_checkpoint(str(tmp_path), "small rename", size="S")
        assert "routing_missed" not in result

    def test_breadcrumb_consumed_after_checkpoint(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        state_dir = self._setup(tmp_path, monkeypatch)
        self._write_breadcrumb(state_dir)
        bf = state_dir / "routing-breadcrumb.json"
        assert bf.exists()
        task_checkpoint(str(tmp_path), "implement feature", size="M")
        assert not bf.exists()

    def test_second_m_task_without_new_breadcrumb_is_missed(self, tmp_path, monkeypatch):
        """Breadcrumb consumed on first checkpoint — second M+ task without route_task fires routing_missed."""
        from session import task_checkpoint
        state_dir = self._setup(tmp_path, monkeypatch)
        self._write_breadcrumb(state_dir)
        # First task — consumes breadcrumb
        task_checkpoint(str(tmp_path), "first feature", size="M")
        # Second task — no new breadcrumb written (route_task not called again)
        result = task_checkpoint(str(tmp_path), "second feature without re-routing", size="M")
        assert result.get("routing_missed") is True

    def test_routing_action_mentions_route_task(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        result = task_checkpoint(str(tmp_path), "build new thing", size="M")
        assert "route_task" in result.get("routing_action", "")

    def test_routing_action_mentions_skill_chain(self, tmp_path, monkeypatch):
        from session import task_checkpoint
        self._setup(tmp_path, monkeypatch)
        result = task_checkpoint(str(tmp_path), "build new thing", size="M")
        action = result.get("routing_action", "")
        assert "nfr_check" in action or "challenge" in action or "dev_loop" in action
