"""Tests for ceremony_sequencer.py — gate order tracking per session slug."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

import ceremony_sequencer as cs


@pytest.fixture
def seq_root(tmp_path):
    root = tmp_path / "youk"
    (root / "state").mkdir(parents=True)
    return root


SLUG = "test-proj-abc123"


class TestRecordGate:
    def test_record_creates_file(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        f = seq_root / "state" / "sessions" / SLUG / "ceremony-sequence.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert len(data) == 1
        assert data[0]["gate"] == "challenge"
        assert "fired_at" in data[0]

    def test_record_is_idempotent(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        f = seq_root / "state" / "sessions" / SLUG / "ceremony-sequence.json"
        data = json.loads(f.read_text())
        assert len(data) == 1, "Duplicate gate entry written"

    def test_record_appends_multiple_gates(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        cs.record_gate("nfr", SLUG, youk_root=seq_root)
        gates = cs.get_sequence(SLUG, youk_root=seq_root)
        assert gates == ["challenge", "nfr"]

    def test_record_empty_slug_noop(self, seq_root):
        cs.record_gate("challenge", "", youk_root=seq_root)
        sessions_dir = seq_root / "state" / "sessions"
        assert not sessions_dir.exists() or not any(sessions_dir.iterdir())


class TestCheckOrder:
    def test_nfr_without_challenge_warns(self, seq_root):
        result = cs.check_order("nfr", SLUG, size="M", youk_root=seq_root)
        assert result["ok"] is False
        assert result["warning"] is not None
        assert "challenge" in result["warning"].lower()

    def test_nfr_after_challenge_ok(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        result = cs.check_order("nfr", SLUG, size="M", youk_root=seq_root)
        assert result["ok"] is True
        assert result["warning"] is None

    def test_xs_task_always_ok(self, seq_root):
        result = cs.check_order("nfr", SLUG, size="XS", youk_root=seq_root)
        assert result["ok"] is True
        assert result["warning"] is None

    def test_s_task_always_ok(self, seq_root):
        result = cs.check_order("challenge_gate", SLUG, size="S", youk_root=seq_root)
        assert result["ok"] is True

    def test_challenge_gate_without_nfr_warns(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        result = cs.check_order("challenge_gate", SLUG, size="M", youk_root=seq_root)
        assert result["ok"] is False
        assert result["warning"] is not None

    def test_challenge_gate_after_nfr_ok(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        cs.record_gate("nfr", SLUG, youk_root=seq_root)
        result = cs.check_order("challenge_gate", SLUG, size="M", youk_root=seq_root)
        assert result["ok"] is True

    def test_unknown_gate_always_ok(self, seq_root):
        result = cs.check_order("unknown-gate", SLUG, size="M", youk_root=seq_root)
        assert result["ok"] is True


class TestDevLoopRegistered:
    def test_false_on_fresh_state(self, seq_root):
        assert cs.dev_loop_registered(SLUG, youk_root=seq_root) is False

    def test_true_after_recording(self, seq_root):
        cs.record_gate("dev-loop", SLUG, youk_root=seq_root)
        assert cs.dev_loop_registered(SLUG, youk_root=seq_root) is True

    def test_false_when_other_gates_recorded(self, seq_root):
        cs.record_gate("challenge", SLUG, youk_root=seq_root)
        cs.record_gate("nfr", SLUG, youk_root=seq_root)
        assert cs.dev_loop_registered(SLUG, youk_root=seq_root) is False

    def test_false_for_empty_slug(self, seq_root):
        cs.record_gate("dev-loop", "", youk_root=seq_root)
        assert cs.dev_loop_registered("", youk_root=seq_root) is False


class TestTaskCheckpointDevLoop:
    """Integration test: task_checkpoint surfaces dev_loop_not_registered on M+ tasks."""

    def _prime_session_state(self, youk_root: Path, project_dir: Path) -> str:
        import session as _session
        slug = _session._slug(str(project_dir))
        state_file = youk_root / "state" / "session.json"
        state_file.write_text(json.dumps({
            "session_counter": 1,
            "last_project": str(project_dir),
            "last_head": "",
        }))
        return slug

    def test_checkpoint_flags_missing_dev_loop(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")
        monkeypatch.setattr(session, "YOUK_ROOT", youk_root)

        project_dir = youk_root
        self._prime_session_state(youk_root, project_dir)
        # No dev-loop recorded — ceremony sequence file absent

        result = session.task_checkpoint(str(project_dir), "build ceremony sequencer", size="M")
        assert "dev_loop_not_registered" in result

    def test_checkpoint_clean_when_dev_loop_registered(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")
        monkeypatch.setattr(session, "YOUK_ROOT", youk_root)

        project_dir = youk_root
        slug = self._prime_session_state(youk_root, project_dir)
        cs.record_gate("dev-loop", slug, youk_root=youk_root)

        result = session.task_checkpoint(str(project_dir), "build ceremony sequencer", size="M")
        assert "dev_loop_not_registered" not in result

    def test_xs_task_no_dev_loop_check(self, youk_root, monkeypatch):
        import session
        import state_paths
        monkeypatch.setattr(state_paths, "YOUK_ROOT", youk_root)
        monkeypatch.setattr(session, "STATE_FILE", youk_root / "state" / "session.json")
        monkeypatch.setattr(session, "YOUK_ROOT", youk_root)

        project_dir = youk_root
        self._prime_session_state(youk_root, project_dir)

        result = session.task_checkpoint(str(project_dir), "fix typo", size="XS")
        assert "dev_loop_not_registered" not in result
