"""Tests for CAP-2: hook-layer gate visibility.

Covers:
  - load_routes_yaml_signals: loads M/L/XL signals from routes.yaml
  - detect_task_size with routes.yaml signals
  - route_task_ran_this_session: slug match + session boundary (mtime)
  - count_route_warnings_this_session: counts only current-session entries
  - log_route_warning: writes to hook-warnings.jsonl
  - build_route_missing_warning: warning text content
  - suppress-after-3 behavior (via count check)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "scripts"))


@pytest.fixture
def hook_root(tmp_path):
    """Minimal youk root for hook tests."""
    root = tmp_path / "youk"
    (root / "state").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    return root


# ── load_routes_yaml_signals ──────────────────────────────────────────────────

class TestLoadRoutesYamlSignals:
    def test_loads_m_signals(self, hook_root):
        """M signals from routes.yaml are included in the result."""
        (hook_root / "config" / "routes.yaml").write_text(
            "task_sizes:\n"
            "  M:\n"
            "    signals: [feature, add, implement]\n"
            "    negative_signals: []\n"
            "  L:\n"
            "    signals: [architecture]\n"
            "    negative_signals: []\n"
            "  XL:\n"
            "    signals: [migration]\n"
            "    negative_signals: []\n"
        )
        from youk_hook_utils import load_routes_yaml_signals
        signals = load_routes_yaml_signals(hook_root)
        assert "feature" in signals
        assert "add" in signals
        assert "architecture" in signals
        assert "migration" in signals

    def test_fallback_when_no_yaml(self, hook_root):
        """Falls back to _BUILD_SIGNALS when routes.yaml is absent."""
        from youk_hook_utils import load_routes_yaml_signals, _BUILD_SIGNALS
        signals = load_routes_yaml_signals(hook_root)
        assert signals == list(_BUILD_SIGNALS)

    def test_fallback_on_invalid_yaml(self, hook_root):
        """Falls back to _BUILD_SIGNALS when routes.yaml is malformed."""
        (hook_root / "config" / "routes.yaml").write_text("not: valid: yaml: [unclosed")
        from youk_hook_utils import load_routes_yaml_signals, _BUILD_SIGNALS
        signals = load_routes_yaml_signals(hook_root)
        assert signals == list(_BUILD_SIGNALS)


# ── detect_task_size with routes signals ──────────────────────────────────────

class TestDetectTaskSizeWithSignals:
    def test_fires_on_routes_signal(self):
        """detect_task_size returns 'M' when routes.yaml signal is present."""
        from youk_hook_utils import detect_task_size
        assert detect_task_size("let's refactor the auth module", signals=["refactor"]) == "M"

    def test_does_not_fire_on_questions(self):
        """detect_task_size returns None for question-prefixed prompts."""
        from youk_hook_utils import detect_task_size
        assert detect_task_size("how do we implement this?", signals=["implement"]) is None

    def test_backward_compat_default_signals(self):
        """detect_task_size with no signals arg uses _BUILD_SIGNALS (backward compat)."""
        from youk_hook_utils import detect_task_size
        assert detect_task_size("implement the new feature") == "M"


# ── route_task_ran_this_session ───────────────────────────────────────────────

class TestRouteTaskRanThisSession:
    def test_returns_false_when_no_flag_file(self, hook_root):
        from youk_hook_utils import route_task_ran_this_session
        assert route_task_ran_this_session(hook_root, "myproject") is False

    def test_returns_false_when_wrong_slug(self, hook_root):
        (hook_root / "state" / "route-task-ran.json").write_text(
            json.dumps([{"slug": "otherproject", "task_hash": "abc"}])
        )
        from youk_hook_utils import route_task_ran_this_session
        assert route_task_ran_this_session(hook_root, "myproject") is False

    def test_returns_true_when_slug_matches(self, hook_root):
        (hook_root / "state" / "route-task-ran.json").write_text(
            json.dumps([{"slug": "myproject", "task_hash": "abc"}])
        )
        from youk_hook_utils import route_task_ran_this_session
        assert route_task_ran_this_session(hook_root, "myproject") is True

    def test_returns_false_when_flag_older_than_session_open(self, hook_root, tmp_path):
        """Flag file older than session-open.json = prior session's route_task."""
        flag = hook_root / "state" / "route-task-ran.json"
        flag.write_text(json.dumps([{"slug": "myproject", "task_hash": "abc"}]))
        # Write session-open.json with a newer mtime
        open_file = hook_root / "state" / "session-open.json"
        open_file.write_text(json.dumps({"slug": "myproject"}))
        # Make flag older than open file (touch open_file to update mtime)
        old_time = open_file.stat().st_mtime - 10
        import os
        os.utime(flag, (old_time, old_time))
        from youk_hook_utils import route_task_ran_this_session
        assert route_task_ran_this_session(hook_root, "myproject") is False

    def test_returns_false_when_flag_from_yesterday_no_session_marker(self, hook_root):
        """When session-open.json is absent, a flag from yesterday is treated as stale
        (prior session) and returns False — not True as slug-only fallback would give."""
        import os, datetime as _dt, time as _time
        flag = hook_root / "state" / "route-task-ran.json"
        flag.write_text(json.dumps([{"slug": "myproject", "task_hash": "abc"}]))
        # Backdate the flag to yesterday
        yesterday = _dt.date.today() - _dt.timedelta(days=1)
        yesterday_ts = _time.mktime(yesterday.timetuple())
        os.utime(flag, (yesterday_ts, yesterday_ts))
        # No session-open.json present
        from youk_hook_utils import route_task_ran_this_session
        assert route_task_ran_this_session(hook_root, "myproject") is False


# ── count_route_warnings_this_session ────────────────────────────────────────

class TestCountRouteWarnings:
    def test_zero_when_no_file(self, hook_root):
        from youk_hook_utils import count_route_warnings_this_session
        assert count_route_warnings_this_session(hook_root, "myproject") == 0

    def test_counts_only_this_session(self, hook_root):
        """Only entries newer than session-open.json are counted."""
        open_file = hook_root / "state" / "session-open.json"
        open_file.write_text(json.dumps({"slug": "myproject"}))
        session_start = open_file.stat().st_mtime

        warnings_file = hook_root / "state" / "hook-warnings.jsonl"
        # Old entry (before session)
        old_entry = json.dumps({"type": "route_missing", "slug": "myproject", "ts": session_start - 100})
        # New entry (this session)
        new_entry = json.dumps({"type": "route_missing", "slug": "myproject", "ts": session_start + 10})
        warnings_file.write_text(old_entry + "\n" + new_entry + "\n")

        from youk_hook_utils import count_route_warnings_this_session
        assert count_route_warnings_this_session(hook_root, "myproject") == 1

    def test_suppress_threshold_at_three(self, hook_root):
        """After 3 warnings, count is 3 and new warnings should not fire."""
        from youk_hook_utils import count_route_warnings_this_session, _ROUTE_WARNING_SUPPRESS_AFTER
        warnings_file = hook_root / "state" / "hook-warnings.jsonl"
        now = time.time()
        lines = [
            json.dumps({"type": "route_missing", "slug": "myproject", "ts": now + i})
            for i in range(_ROUTE_WARNING_SUPPRESS_AFTER)
        ]
        warnings_file.write_text("\n".join(lines) + "\n")
        count = count_route_warnings_this_session(hook_root, "myproject")
        assert count == _ROUTE_WARNING_SUPPRESS_AFTER
        assert not (count < _ROUTE_WARNING_SUPPRESS_AFTER)  # suppression threshold met


# ── log_route_warning ─────────────────────────────────────────────────────────

class TestLogRouteWarning:
    def test_writes_jsonl_entry(self, hook_root):
        from youk_hook_utils import log_route_warning
        log_route_warning(hook_root, "myproject")
        warnings_file = hook_root / "state" / "hook-warnings.jsonl"
        assert warnings_file.exists()
        line = json.loads(warnings_file.read_text().strip())
        assert line["type"] == "route_missing"
        assert line["slug"] == "myproject"
        assert "ts" in line

    def test_appends_multiple_entries(self, hook_root):
        from youk_hook_utils import log_route_warning
        log_route_warning(hook_root, "myproject")
        log_route_warning(hook_root, "myproject")
        warnings_file = hook_root / "state" / "hook-warnings.jsonl"
        lines = [l for l in warnings_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 2


# ── build_route_missing_warning ───────────────────────────────────────────────

class TestBuildRouteMissingWarning:
    def test_contains_required_text(self):
        from youk_hook_utils import build_route_missing_warning
        warning = build_route_missing_warning()
        assert "[YOUK]" in warning
        assert "M+ signals detected" in warning
        assert "route_task has not run this session" in warning
