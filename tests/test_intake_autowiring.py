"""
Tests for intake auto-wiring in optimize_intent.

optimize_intent now returns intake_required=True when:
- estimated_size is M, L, or XL
- input uses solution language ("I want to build X", "add a", "wire in", etc.)
- no intake-ran.json exists for the current session

mark_intake_ran() writes intake-ran.json; after it fires, intake_required=False.
session_end clears intake-ran.json so the next session can trigger intake again.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


def _run_fallback(raw_input: str, youk_root: Path) -> dict:
    """Run optimize_intent in fallback mode (no API) with sandboxed YOUK_ROOT."""
    import intent as intent_mod
    original_available = intent_mod._ANTHROPIC_AVAILABLE
    original_root = intent_mod.YOUK_ROOT
    intent_mod._ANTHROPIC_AVAILABLE = False
    intent_mod.YOUK_ROOT = youk_root
    try:
        return intent_mod.optimize_intent(raw_input)
    finally:
        intent_mod._ANTHROPIC_AVAILABLE = original_available
        intent_mod.YOUK_ROOT = original_root


def _run_fast_pattern(raw_input: str, youk_root: Path) -> dict:
    """Run optimize_intent through the fast pattern path with sandboxed YOUK_ROOT."""
    import intent as intent_mod
    original_root = intent_mod.YOUK_ROOT
    intent_mod.YOUK_ROOT = youk_root
    try:
        return intent_mod.optimize_intent(raw_input)
    finally:
        intent_mod.YOUK_ROOT = original_root


class TestSolutionLanguageDetection:
    """_detect_solution_language() correctly classifies inputs."""

    def _detect(self, raw: str) -> bool:
        import intent as intent_mod
        return intent_mod._detect_solution_language(raw)

    def test_build_a_triggers(self):
        assert self._detect("build a caching layer")

    def test_add_a_triggers(self):
        assert self._detect("add a feature flag system")

    def test_wire_in_triggers(self):
        assert self._detect("wire intake into optimize_intent")

    def test_implement_triggers(self):
        assert self._detect("implement a retry mechanism")

    def test_create_triggers(self):
        assert self._detect("create a new API endpoint")

    def test_fix_bug_excluded(self):
        assert not self._detect("fix the login bug")

    def test_error_excluded(self):
        assert not self._detect("why is this throwing an error?")

    def test_debug_excluded(self):
        assert not self._detect("debug the session handling")

    def test_neutral_question_not_triggered(self):
        assert not self._detect("what does session_end do?")


class TestIntakeRequiredField:
    """optimize_intent returns intake_required correctly."""

    def test_solution_language_m_size_no_prior_intake(self, tmp_path):
        # No intake-ran.json, no session-open.json → intake_required=True
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        result = _run_fallback("build a new caching module", tmp_path)
        assert result.get("intake_required") is True, (
            f"Solution-language M+ with no prior intake should require intake, got: {result.get('intake_required')}"
        )

    def test_debug_task_not_required(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        result = _run_fallback("fix the session bug that crashes on startup", tmp_path)
        assert result.get("intake_required") is False, (
            "Debug/fix tasks should never require intake"
        )

    def test_intake_required_false_after_mark_intake_ran(self, tmp_path):
        # Write intake-ran.json and session-open.json with matching slug
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        slug = "test-project"
        (state_dir / "session-open.json").write_text(json.dumps({"slug": slug}))
        (state_dir / "intake-ran.json").write_text(json.dumps({
            "slug": slug,
            "task": "build a caching module",
            "ts": "2026-07-24T12:00:00",
        }))
        result = _run_fallback("build a new caching module", tmp_path)
        assert result.get("intake_required") is False, (
            "After intake-ran.json written, intake_required must be False"
        )

    def test_intake_required_true_slug_mismatch(self, tmp_path):
        # intake-ran.json exists but for a different session slug
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "session-open.json").write_text(json.dumps({"slug": "current-project"}))
        (state_dir / "intake-ran.json").write_text(json.dumps({
            "slug": "different-project",
            "task": "build something",
            "ts": "2026-07-24T12:00:00",
        }))
        result = _run_fallback("build a new caching module", tmp_path)
        assert result.get("intake_required") is True, (
            "Slug mismatch means intake hasn't run this session — must be True"
        )

    def test_intake_required_present_in_all_paths(self, tmp_path):
        # intake_required field must be present regardless of mode
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        result = _run_fallback("build a feature", tmp_path)
        assert "intake_required" in result, (
            "intake_required field must be present in all optimize_intent return values"
        )

    def test_fast_pattern_includes_intake_required(self, tmp_path):
        # Fast pattern "make it a repo" → M size → intake_required present
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        result = _run_fast_pattern("make it a repo", tmp_path)
        assert "intake_required" in result, (
            "Fast pattern path must also return intake_required"
        )


class TestIntakeHasRun:
    """_intake_has_run() correctly reads state."""

    def test_no_file_returns_false(self, tmp_path):
        import intent as intent_mod
        original = intent_mod.YOUK_ROOT
        intent_mod.YOUK_ROOT = tmp_path
        (tmp_path / "state").mkdir()
        try:
            assert intent_mod._intake_has_run() is False
        finally:
            intent_mod.YOUK_ROOT = original

    def test_matching_slug_returns_true(self, tmp_path):
        import intent as intent_mod
        original = intent_mod.YOUK_ROOT
        intent_mod.YOUK_ROOT = tmp_path
        state = tmp_path / "state"
        state.mkdir()
        slug = "myproject"
        (state / "session-open.json").write_text(json.dumps({"slug": slug}))
        (state / "intake-ran.json").write_text(json.dumps({"slug": slug}))
        try:
            assert intent_mod._intake_has_run() is True
        finally:
            intent_mod.YOUK_ROOT = original

    def test_no_session_open_returns_false(self, tmp_path):
        import intent as intent_mod
        original = intent_mod.YOUK_ROOT
        intent_mod.YOUK_ROOT = tmp_path
        state = tmp_path / "state"
        state.mkdir()
        # intake-ran.json exists but session-open.json does not
        (state / "intake-ran.json").write_text(json.dumps({"slug": "x"}))
        try:
            assert intent_mod._intake_has_run() is False
        finally:
            intent_mod.YOUK_ROOT = original

    def test_corrupt_json_returns_false(self, tmp_path):
        import intent as intent_mod
        original = intent_mod.YOUK_ROOT
        intent_mod.YOUK_ROOT = tmp_path
        state = tmp_path / "state"
        state.mkdir()
        (state / "intake-ran.json").write_text("not-json{{{")
        (state / "session-open.json").write_text(json.dumps({"slug": "x"}))
        try:
            assert intent_mod._intake_has_run() is False
        finally:
            intent_mod.YOUK_ROOT = original


class TestSessionEndClearsIntakeRan:
    """session_end removes intake-ran.json so next session can trigger intake."""

    def test_intake_ran_deleted_on_session_end(self, youk_root, tmp_path, monkeypatch):
        import session as session_mod
        monkeypatch.setattr(session_mod, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)

        state_dir = youk_root / "state"
        intake_file = state_dir / "intake-ran.json"
        intake_file.write_text(json.dumps({"slug": "test", "ts": "2026-07-24T00:00:00"}))
        assert intake_file.exists()

        session_mod.end_session(
            summary="test session end clears intake",
            commits_made=False,
        )

        assert not intake_file.exists(), (
            "session_end must delete intake-ran.json so next session can trigger intake"
        )
