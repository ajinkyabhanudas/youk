"""Tests for tokens.py — checkpoint accumulation, budget tracking, read_and_clear."""
from __future__ import annotations
import json
import pytest


@pytest.fixture(autouse=True)
def patch_token_file(tmp_path, monkeypatch):
    import tokens
    token_file = tmp_path / "current-session-tokens.json"
    monkeypatch.setattr(tokens, "TOKEN_FILE", token_file)
    return token_file


class TestInitTokenTracker:
    def test_creates_file_with_zero_totals(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1")
        data = json.loads(tokens.TOKEN_FILE.read_text())
        assert data["total_input"] == 0
        assert data["total_output"] == 0
        assert data["checkpoints"] == []
        assert data["session_id"] == "sess-1"

    def test_stores_token_budget(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-2", token_budget=75000)
        data = json.loads(tokens.TOKEN_FILE.read_text())
        assert data["token_budget"] == 75000

    def test_overwrites_existing_file(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1", token_budget=50000)
        tokens.init_token_tracker("sess-2", token_budget=0)
        data = json.loads(tokens.TOKEN_FILE.read_text())
        assert data["session_id"] == "sess-2"
        assert data["token_budget"] == 0


class TestRecordCheckpoint:
    def test_accumulates_input_output(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1")
        tokens.record_checkpoint(1000, 500, "route_task")
        tokens.record_checkpoint(2000, 800, "skill")
        data = json.loads(tokens.TOKEN_FILE.read_text())
        assert data["total_input"] == 3000
        assert data["total_output"] == 1300
        assert len(data["checkpoints"]) == 2

    def test_returns_running_total(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1")
        result = tokens.record_checkpoint(1000, 500, "first")
        assert result["session_total_input"] == 1000
        assert result["session_total_output"] == 500
        assert result["session_total"] == 1500

    def test_vs_budget_pct_computed_when_budget_set(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1", token_budget=10000)
        result = tokens.record_checkpoint(5000, 0, "check")
        assert result["vs_budget_pct"] == 50.0

    def test_vs_budget_pct_none_when_no_budget(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1", token_budget=0)
        result = tokens.record_checkpoint(5000, 0, "check")
        assert result["vs_budget_pct"] is None

    def test_budget_registered_mid_session(self, tmp_path):
        """Budget can be set on any checkpoint — e.g. after route_task returns."""
        import tokens
        tokens.init_token_tracker("sess-1")
        tokens.record_checkpoint(0, 0, "route_task", token_budget=75000)
        result = tokens.record_checkpoint(10000, 5000, "skill")
        assert result["token_budget"] == 75000
        assert result["vs_budget_pct"] == 20.0

    def test_returns_error_when_no_tracker(self, tmp_path):
        import tokens
        result = tokens.record_checkpoint(1000, 500, "orphan")
        assert "error" in result

    def test_checkpoint_note_stored(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1")
        tokens.record_checkpoint(100, 50, "my-note")
        data = json.loads(tokens.TOKEN_FILE.read_text())
        assert data["checkpoints"][0]["note"] == "my-note"


class TestReadAndClear:
    def test_returns_totals_and_deletes_file(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1", token_budget=50000)
        tokens.record_checkpoint(3000, 1000, "a")
        tokens.record_checkpoint(2000, 500, "b")
        result = tokens.read_and_clear()
        assert result["total_input"] == 5000
        assert result["total_output"] == 1500
        assert result["checkpoints"] == 2
        assert not tokens.TOKEN_FILE.exists()

    def test_returns_zeros_when_no_file(self, tmp_path):
        import tokens
        result = tokens.read_and_clear()
        assert result["total_input"] == 0
        assert result["total_output"] == 0
        assert result["checkpoints"] == 0

    def test_budget_preserved_in_result(self, tmp_path):
        import tokens
        tokens.init_token_tracker("sess-1", token_budget=75000)
        result = tokens.read_and_clear()
        assert result["token_budget"] == 75000
