"""
Tests for M+ routing hard gate:
- route_to_skill("dev-loop") blocked without prior route_task
- route-task-ran.json array format
- per-task NFR state tracking
- short BUILD_SIGNAL prompts bypass MIN_PROMPT_LEN gate
"""
from __future__ import annotations
import json
import hashlib
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
_HOOK_SCRIPTS = _REPO / "plugin" / "scripts"
for _p in [str(_HOOK_SCRIPTS)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── skills.py gate tests ──────────────────────────────────────────────────────

class TestDevLoopGate:
    """route_to_skill('dev-loop') must be blocked when route_task hasn't run."""

    @staticmethod
    def _patch(monkeypatch, tmp_path):
        import skills
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(skills, "_ROUTE_TASK_RAN", state_dir / "route-task-ran.json")
        monkeypatch.setattr(skills, "_SESSION_OPEN", state_dir / "session-open.json")
        monkeypatch.setattr(skills, "_SESSION_STATE", state_dir / "session.json")
        return skills, state_dir

    def test_dev_loop_blocked_without_route_task(self, monkeypatch, tmp_path):
        skills, state_dir = self._patch(monkeypatch, tmp_path)
        result = skills.route_to_skill("dev-loop", "add auth endpoint")
        assert result.get("blocked") is True
        assert "route_task" in result.get("reason", "")

    def test_dev_loop_blocked_when_flag_missing(self, monkeypatch, tmp_path):
        skills, state_dir = self._patch(monkeypatch, tmp_path)
        # No route-task-ran.json exists at all
        result = skills.route_to_skill("dev-loop", "build feature")
        assert result.get("blocked") is True

    def test_dev_loop_passes_after_route_task(self, monkeypatch, tmp_path):
        skills, state_dir = self._patch(monkeypatch, tmp_path)
        slug = "myproject"
        (state_dir / "session-open.json").write_text(json.dumps({"slug": slug}))
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": slug, "task": "add auth", "task_hash": "abc12345", "size": "M", "ts": "2026-07-14T10:00:00"}
        ]))
        # Patch skill loader to avoid FileNotFoundError
        monkeypatch.setattr(skills, "load_skill_with_context", lambda *a, **kw: "# skill content")
        result = skills.route_to_skill("dev-loop", "add auth endpoint")
        assert result.get("blocked") is None
        assert result.get("mode") == "in_session"

    def test_non_gated_skill_always_passes(self, monkeypatch, tmp_path):
        skills, state_dir = self._patch(monkeypatch, tmp_path)
        # No route-task-ran.json — should not block non-gated skills
        monkeypatch.setattr(skills, "load_skill_with_context", lambda *a, **kw: "# code-review content")
        result = skills.route_to_skill("code-review", "review this diff")
        assert result.get("blocked") is None
        assert result.get("mode") == "in_session"

    def test_dev_loop_blocked_wrong_slug(self, monkeypatch, tmp_path):
        skills, state_dir = self._patch(monkeypatch, tmp_path)
        (state_dir / "session-open.json").write_text(json.dumps({"slug": "project-a"}))
        # Route task ran for a different project
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "project-b", "task": "add auth", "task_hash": "abc12345", "size": "M", "ts": "2026-07-14T10:00:00"}
        ]))
        result = skills.route_to_skill("dev-loop", "add auth endpoint")
        assert result.get("blocked") is True


# ── route-task-ran.json array format tests ────────────────────────────────────

class TestRouteTaskRanArray:
    """route-task-ran.json must be an array to track multiple tasks per session."""

    def test_route_task_writes_array(self, tmp_path):
        """Writing route-task-ran.json twice (simulating server logic) yields an array."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        flag_file = state_dir / "route-task-ran.json"
        slug = "proj"

        def _write_entry(task: str):
            task_hash = hashlib.md5(task.encode()).hexdigest()[:8]
            new_entry = {"slug": slug, "task": task[:120], "task_hash": task_hash, "size": "M", "ts": "2026-07-14T10:00:00"}
            existing: list[dict] = []
            if flag_file.exists():
                try:
                    raw = json.loads(flag_file.read_text())
                    existing = raw if isinstance(raw, list) else [raw]
                except Exception:
                    pass
            existing = [e for e in existing if e.get("slug") == slug]
            existing.append(new_entry)
            flag_file.write_text(json.dumps(existing))

        _write_entry("add auth endpoint")
        _write_entry("add rate limiting")

        data = json.loads(flag_file.read_text())
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["task"] == "add auth endpoint"
        assert data[1]["task"] == "add rate limiting"

    def test_legacy_single_object_still_reads(self, monkeypatch, tmp_path):
        """_routing_ran_last_session handles legacy single-object format."""
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "route-task-ran.json").write_text(json.dumps(
            {"slug": "myproject", "task": "old task", "size": "M", "ts": "2026-07-01T10:00:00"}
        ))
        ran, task = session._routing_ran_last_session("myproject")
        assert ran is True
        assert task == "old task"

    def test_array_format_reads_first_match(self, monkeypatch, tmp_path):
        """_routing_ran_last_session finds first matching slug in array."""
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "proj", "task": "task one", "task_hash": "aaa", "size": "M", "ts": "2026-07-14T09:00:00"},
            {"slug": "proj", "task": "task two", "task_hash": "bbb", "size": "M", "ts": "2026-07-14T10:00:00"},
        ]))
        ran, task = session._routing_ran_last_session("proj")
        assert ran is True
        assert task == "task one"

    def test_no_match_returns_false(self, monkeypatch, tmp_path):
        """_routing_ran_last_session returns False when slug doesn't match."""
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "other-proj", "task": "task", "task_hash": "aaa", "size": "M", "ts": "2026-07-14T10:00:00"},
        ]))
        ran, task = session._routing_ran_last_session("myproject")
        assert ran is False
        assert task == ""


# ── BUILD_SIGNAL short prompt detection tests ─────────────────────────────────

class TestShortBuildSignalDetection:
    """Short prompts with explicit BUILD_SIGNALS must still trigger M+ detection."""

    def test_build_a_feature_short_prompt_detected(self):
        # "build a " is in _BUILD_SIGNALS — short prompts now bypass the 15-char gate
        from youk_hook_utils import detect_task_size
        assert detect_task_size("build a page") == "M"

    def test_add_a_feature_short_prompt_detected(self):
        # "add a " is in _BUILD_SIGNALS
        from youk_hook_utils import detect_task_size
        assert detect_task_size("add a login") == "M"

    def test_implement_login_detected(self):
        from youk_hook_utils import detect_task_size
        assert detect_task_size("implement login") == "M"

    def test_question_with_build_word_not_detected(self):
        from youk_hook_utils import detect_task_size
        assert detect_task_size("how do we build this?") is None

    def test_slash_command_not_detected(self):
        from youk_hook_utils import detect_task_size
        assert detect_task_size("/build auth") is None

    def test_pure_short_prompt_no_signal_not_detected(self):
        from youk_hook_utils import detect_task_size
        # Short with no build signal — still no detection
        assert detect_task_size("ok") is None

    def test_ok_thanks_not_detected(self):
        from youk_hook_utils import detect_task_size
        assert detect_task_size("ok thanks") is None


# ── routing_ran_for_task tests ────────────────────────────────────────────────

class TestRoutingRanForTask:
    """routing_ran_for_task returns True only when exact slug+task_hash match exists."""

    def test_returns_true_on_exact_match(self, tmp_path):
        from youk_hook_utils import routing_ran_for_task
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        slug = "myproject"
        task_hash = hashlib.md5(b"add auth endpoint").hexdigest()[:8]
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": slug, "task": "add auth endpoint", "task_hash": task_hash, "size": "M", "ts": "2026-07-14T10:00:00"}
        ]))
        assert routing_ran_for_task(tmp_path, slug, task_hash) is True

    def test_returns_false_on_slug_mismatch(self, tmp_path):
        from youk_hook_utils import routing_ran_for_task
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        task_hash = hashlib.md5(b"add auth endpoint").hexdigest()[:8]
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "other-proj", "task": "add auth endpoint", "task_hash": task_hash, "size": "M", "ts": "2026-07-14T10:00:00"}
        ]))
        assert routing_ran_for_task(tmp_path, "myproject", task_hash) is False

    def test_returns_false_on_task_hash_mismatch(self, tmp_path):
        from youk_hook_utils import routing_ran_for_task
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "route-task-ran.json").write_text(json.dumps([
            {"slug": "myproject", "task": "add auth endpoint", "task_hash": "aaa11111", "size": "M", "ts": "2026-07-14T10:00:00"}
        ]))
        assert routing_ran_for_task(tmp_path, "myproject", "bbb22222") is False

    def test_returns_false_when_no_file(self, tmp_path):
        from youk_hook_utils import routing_ran_for_task
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        assert routing_ran_for_task(tmp_path, "myproject", "abc12345") is False
