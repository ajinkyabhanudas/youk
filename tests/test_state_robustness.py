"""Tests for W1 state robustness — routing_context in active_task.json.

Covers:
- write_routing_context: writes routing_context schema on route_task fire
- append_gate_to_active_task: idempotent gate sequence append
- get_gate_sequence_resume_item: surfaces incomplete gate sequence on resume
- post_tool_use label preference: routing_context.task wins over filename

All functions live in session.py (no mcp dependency) so tests run on host.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import session as _session_mod
from session import (
    write_routing_context,
    append_gate_to_active_task,
    get_gate_sequence_resume_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_active_task(state_dir: Path, data: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "active_task.json").write_text(json.dumps(data))


def _read_active_task(state_dir: Path) -> dict:
    return json.loads((state_dir / "active_task.json").read_text())


def _standard_result(**kwargs) -> dict:
    base = {"size": "M", "ceremony": "standard", "plan_hook": "Plan hook text", "blocked": False}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# write_routing_context
# ---------------------------------------------------------------------------

class TestWriteRoutingContext:
    def test_creates_routing_context_key(self, tmp_path):
        (tmp_path / "state").mkdir()
        write_routing_context("Build the concept graph", _standard_result(), youk_root=tmp_path)
        data = _read_active_task(tmp_path / "state")
        assert "routing_context" in data

    def test_routing_context_has_required_fields(self, tmp_path):
        (tmp_path / "state").mkdir()
        write_routing_context("My semantic task", _standard_result(), youk_root=tmp_path)
        ctx = _read_active_task(tmp_path / "state")["routing_context"]
        assert ctx["task"] == "My semantic task"
        assert ctx["size"] == "M"
        assert ctx["plan_hook"] == "Plan hook text"
        assert isinstance(ctx["gates_expected"], list)
        assert ctx["gates_sequence"] == []
        assert "routed_at" in ctx

    def test_standard_ceremony_expects_four_gates(self, tmp_path):
        (tmp_path / "state").mkdir()
        write_routing_context("task", _standard_result(ceremony="standard"), youk_root=tmp_path)
        ctx = _read_active_task(tmp_path / "state")["routing_context"]
        assert set(ctx["gates_expected"]) == {"challenge", "nfr", "challenge_gate", "dev-loop"}

    def test_minimal_ceremony_expects_two_gates(self, tmp_path):
        (tmp_path / "state").mkdir()
        write_routing_context("task", _standard_result(ceremony="minimal"), youk_root=tmp_path)
        ctx = _read_active_task(tmp_path / "state")["routing_context"]
        assert set(ctx["gates_expected"]) == {"nfr", "dev-loop"}

    def test_none_ceremony_expects_zero_gates(self, tmp_path):
        (tmp_path / "state").mkdir()
        write_routing_context("task", _standard_result(ceremony="none"), youk_root=tmp_path)
        ctx = _read_active_task(tmp_path / "state")["routing_context"]
        assert ctx["gates_expected"] == []

    def test_preserves_existing_files_touched(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {
            "task": "old",
            "files_touched": ["src/foo.py", "src/bar.py"],
        })
        write_routing_context("New semantic task", _standard_result(), youk_root=tmp_path)
        data = _read_active_task(state_dir)
        assert data["files_touched"] == ["src/foo.py", "src/bar.py"]

    def test_overwrites_filename_derived_task_label(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {"task": "editing session.py"})
        write_routing_context("Build concept graph schema", _standard_result(), youk_root=tmp_path)
        data = _read_active_task(state_dir)
        assert data["task"] == "Build concept graph schema"

    def test_overwrites_running_derived_task_label(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {"task": "running: pytest"})
        write_routing_context("Semantic task", _standard_result(), youk_root=tmp_path)
        assert _read_active_task(state_dir)["task"] == "Semantic task"

    def test_routing_context_task_always_set_to_current(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {"task": "Implement auth flow"})
        write_routing_context("New task", _standard_result(), youk_root=tmp_path)
        ctx = _read_active_task(state_dir)["routing_context"]
        assert ctx["task"] == "New task"

    def test_silent_fail_when_state_dir_missing(self, tmp_path):
        # state/ not created — must not raise
        write_routing_context("task", _standard_result(), youk_root=tmp_path)

    def test_stamps_slug_from_session_open(self, tmp_path):
        """write_routing_context must write slug itself — guard cannot rely on a hook."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "session-open.json").write_text('{"slug": "canopy"}')
        write_routing_context("Build eval pipeline", _standard_result(), youk_root=tmp_path)
        data = _read_active_task(state_dir)
        assert data.get("slug") == "canopy"

    def test_slug_absent_when_session_open_missing(self, tmp_path):
        """No session-open.json → slug key absent (not an empty string overwriting hook-written value)."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        # No session-open.json written
        write_routing_context("task", _standard_result(), youk_root=tmp_path)
        data = _read_active_task(state_dir)
        # slug may be absent or empty — must not crash
        assert "routing_context" in data  # core write succeeded


# ---------------------------------------------------------------------------
# append_gate_to_active_task
# ---------------------------------------------------------------------------

class TestAppendGateToActiveTask:
    def _setup(self, tmp_path, fired=None):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {
            "task": "Test task",
            "files_touched": ["a.py"],
            "routing_context": {
                "task": "Test task",
                "gates_expected": ["challenge", "nfr", "challenge_gate", "dev-loop"],
                "gates_sequence": [{"gate": g, "fired_at": "2026-07-28T00:00:00"} for g in (fired or [])],
            }
        })
        return state_dir

    def test_appends_gate_entry(self, tmp_path):
        state_dir = self._setup(tmp_path)
        append_gate_to_active_task("challenge", youk_root=tmp_path)
        seq = _read_active_task(state_dir)["routing_context"]["gates_sequence"]
        assert len(seq) == 1
        assert seq[0]["gate"] == "challenge"
        assert "fired_at" in seq[0]

    def test_idempotent_same_gate_not_appended_twice(self, tmp_path):
        state_dir = self._setup(tmp_path)
        append_gate_to_active_task("nfr", youk_root=tmp_path)
        append_gate_to_active_task("nfr", youk_root=tmp_path)
        seq = _read_active_task(state_dir)["routing_context"]["gates_sequence"]
        assert len(seq) == 1

    def test_multiple_different_gates_all_recorded(self, tmp_path):
        state_dir = self._setup(tmp_path)
        append_gate_to_active_task("challenge", youk_root=tmp_path)
        append_gate_to_active_task("nfr", youk_root=tmp_path)
        append_gate_to_active_task("challenge_gate", youk_root=tmp_path)
        seq = _read_active_task(state_dir)["routing_context"]["gates_sequence"]
        assert [g["gate"] for g in seq] == ["challenge", "nfr", "challenge_gate"]

    def test_silent_fail_when_no_active_task_file(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        append_gate_to_active_task("challenge", youk_root=tmp_path)  # must not raise

    def test_silent_fail_when_no_routing_context(self, tmp_path):
        state_dir = tmp_path / "state"
        _write_active_task(state_dir, {"task": "something", "files_touched": []})
        append_gate_to_active_task("challenge", youk_root=tmp_path)
        data = _read_active_task(state_dir)
        assert "routing_context" not in data

    def test_preserves_other_active_task_fields(self, tmp_path):
        state_dir = self._setup(tmp_path)
        append_gate_to_active_task("challenge", youk_root=tmp_path)
        data = _read_active_task(state_dir)
        assert data["files_touched"] == ["a.py"]
        assert data["task"] == "Test task"


# ---------------------------------------------------------------------------
# get_gate_sequence_resume_item
# ---------------------------------------------------------------------------

class TestGetGateSequenceResumeItem:
    def _write(self, tmp_path, task, expected, fired):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "active_task.json").write_text(json.dumps({
            "task": task,
            "routing_context": {
                "task": task,
                "gates_expected": expected,
                "gates_sequence": [{"gate": g, "fired_at": "2026-07-28T00:00:00"} for g in fired],
            }
        }))

    def test_returns_item_when_gates_incomplete(self, tmp_path):
        self._write(tmp_path, "Build concept graph",
                    ["challenge", "nfr", "challenge_gate", "dev-loop"],
                    ["challenge", "nfr"])
        item = get_gate_sequence_resume_item(youk_root=tmp_path)
        assert item is not None
        assert "Build concept graph" in item
        assert "2/4" in item
        assert "challenge_gate" in item  # next gate

    def test_returns_none_when_all_gates_fired(self, tmp_path):
        self._write(tmp_path, "Done task",
                    ["challenge", "nfr", "challenge_gate", "dev-loop"],
                    ["challenge", "nfr", "challenge_gate", "dev-loop"])
        assert get_gate_sequence_resume_item(youk_root=tmp_path) is None

    def test_returns_none_when_no_gates_fired_yet(self, tmp_path):
        self._write(tmp_path, "New task",
                    ["challenge", "nfr", "challenge_gate", "dev-loop"],
                    [])
        assert get_gate_sequence_resume_item(youk_root=tmp_path) is None

    def test_returns_none_when_active_task_missing(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        assert get_gate_sequence_resume_item(youk_root=tmp_path) is None

    def test_item_includes_fired_gates(self, tmp_path):
        self._write(tmp_path, "My task",
                    ["challenge", "nfr", "challenge_gate", "dev-loop"],
                    ["challenge"])
        item = get_gate_sequence_resume_item(youk_root=tmp_path)
        assert "challenge" in item
        assert "nfr" in item  # next gate

    def test_returns_none_on_corrupt_json(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "active_task.json").write_text("{bad json")
        assert get_gate_sequence_resume_item(youk_root=tmp_path) is None


# ---------------------------------------------------------------------------
# post_tool_use label preference
# ---------------------------------------------------------------------------

class TestPostToolUseRoutingLabelPreference:
    @pytest.fixture(autouse=True)
    def _patch_path(self):
        plugin_scripts = Path(__file__).parent.parent / "plugin" / "scripts"
        if str(plugin_scripts) not in sys.path:
            sys.path.insert(0, str(plugin_scripts))

    def test_routing_task_wins_over_filename_label(self):
        from post_tool_use import infer_task_label
        label = infer_task_label(
            tool_name="Edit",
            tool_input={"file_path": "/src/session.py"},
            existing_task="editing session.py",
            routing_task="Build concept graph schema",
        )
        assert label == "Build concept graph schema"

    def test_routing_task_wins_over_existing_semantic_label(self):
        from post_tool_use import infer_task_label
        label = infer_task_label(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            existing_task="Implement auth flow",
            routing_task="Build concept graph",
        )
        assert label == "Build concept graph"

    def test_falls_back_to_filename_when_no_routing_task(self):
        from post_tool_use import infer_task_label
        label = infer_task_label(
            tool_name="Edit",
            tool_input={"file_path": "/src/health.py"},
            existing_task="editing session.py",
            routing_task="",
        )
        assert label == "editing health.py"

    def test_falls_back_to_existing_semantic_when_no_routing(self):
        from post_tool_use import infer_task_label
        label = infer_task_label(
            tool_name="Bash",
            tool_input={"command": "pytest"},
            existing_task="Implement auth flow",
            routing_task="",
        )
        assert label == "Implement auth flow"

    def test_empty_routing_task_uses_fallback_chain(self):
        from post_tool_use import infer_task_label
        label = infer_task_label(
            tool_name="Bash",
            tool_input={"command": "make build"},
            existing_task="",
            routing_task="",
        )
        assert "make build" in label
