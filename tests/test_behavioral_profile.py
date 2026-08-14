"""Tests for behavioral_profile.py — skill-timing pattern learning.

The profile learns from session audit data: if commits_made=True and
humanize not in skills_used across HINT_THRESHOLD sessions, the hint
becomes active and surfaces at session_start.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).parent.parent
for _p in [str(_REPO / "servers" / "shared"), str(_REPO / "servers" / "core" / "src")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from behavioral_profile import (
    HINT_THRESHOLD,
    format_hint_warnings,
    is_hint_active,
    load_active_hints,
    record_session_patterns,
    scan_audit_for_patterns,
)


# ---------------------------------------------------------------------------
# record_session_patterns — evidence accumulation
# ---------------------------------------------------------------------------

class TestRecordSessionPatterns:

    def test_no_update_when_no_commits(self, tmp_path):
        p = tmp_path / "profile.json"
        r = record_session_patterns(["humanize", "learn"], commits_made=False, path=p)
        assert r["hints_updated"] == []
        assert not p.exists() or json.loads(p.read_text())["hints"] == {}

    def test_no_update_when_humanize_fired_at_commit(self, tmp_path):
        p = tmp_path / "profile.json"
        r = record_session_patterns(["humanize", "code-review"], commits_made=True, path=p)
        assert r["hints_updated"] == []

    def test_records_miss_when_commits_no_humanize(self, tmp_path):
        p = tmp_path / "profile.json"
        r = record_session_patterns(["code-review", "learn"], commits_made=True, path=p)
        assert "humanize:commit" in r["hints_updated"]
        profile = json.loads(p.read_text())
        assert profile["hints"]["humanize:commit"]["count"] == 1
        assert profile["hints"]["humanize:commit"]["active"] is False

    def test_hint_activates_at_threshold(self, tmp_path):
        p = tmp_path / "profile.json"
        for i in range(HINT_THRESHOLD):
            r = record_session_patterns(["learn"], commits_made=True, path=p)
        assert "humanize:commit" in r["hints_activated"]
        profile = json.loads(p.read_text())
        assert profile["hints"]["humanize:commit"]["active"] is True

    def test_hint_not_active_below_threshold(self, tmp_path):
        p = tmp_path / "profile.json"
        for _ in range(HINT_THRESHOLD - 1):
            record_session_patterns(["learn"], commits_made=True, path=p)
        profile = json.loads(p.read_text())
        assert profile["hints"]["humanize:commit"]["active"] is False

    def test_idempotent_on_active_hint(self, tmp_path):
        p = tmp_path / "profile.json"
        for _ in range(HINT_THRESHOLD + 3):
            r = record_session_patterns(["learn"], commits_made=True, path=p)
        profile = json.loads(p.read_text())
        assert profile["hints"]["humanize:commit"]["active"] is True
        # Activated only fires once (the session it crosses the threshold)
        assert profile["hints"]["humanize:commit"]["count"] == HINT_THRESHOLD + 3


# ---------------------------------------------------------------------------
# load_active_hints — only active hints returned
# ---------------------------------------------------------------------------

class TestLoadActiveHints:

    def test_empty_when_no_profile(self, tmp_path):
        p = tmp_path / "profile.json"
        hints = load_active_hints(path=p)
        assert hints == []

    def test_inactive_hint_not_returned(self, tmp_path):
        p = tmp_path / "profile.json"
        record_session_patterns(["learn"], commits_made=True, path=p)
        hints = load_active_hints(path=p)
        assert hints == []

    def test_active_hint_returned(self, tmp_path):
        p = tmp_path / "profile.json"
        for _ in range(HINT_THRESHOLD):
            record_session_patterns(["learn"], commits_made=True, path=p)
        hints = load_active_hints(path=p)
        assert len(hints) == 1
        assert hints[0]["skill"] == "humanize"
        assert hints[0]["event"] == "commit"
        assert hints[0]["count"] >= HINT_THRESHOLD


# ---------------------------------------------------------------------------
# is_hint_active — point query
# ---------------------------------------------------------------------------

class TestIsHintActive:

    def test_returns_false_before_threshold(self, tmp_path):
        p = tmp_path / "profile.json"
        assert is_hint_active("humanize", "commit", path=p) is False

    def test_returns_true_after_threshold(self, tmp_path):
        p = tmp_path / "profile.json"
        for _ in range(HINT_THRESHOLD):
            record_session_patterns(["learn"], commits_made=True, path=p)
        assert is_hint_active("humanize", "commit", path=p) is True

    def test_unknown_hint_returns_false(self, tmp_path):
        p = tmp_path / "profile.json"
        assert is_hint_active("nonexistent", "commit", path=p) is False


# ---------------------------------------------------------------------------
# format_hint_warnings
# ---------------------------------------------------------------------------

class TestFormatHintWarnings:

    def test_empty_list_produces_no_warnings(self):
        assert format_hint_warnings([]) == []

    def test_active_hints_produce_warnings(self, tmp_path):
        p = tmp_path / "profile.json"
        for _ in range(HINT_THRESHOLD):
            record_session_patterns(["learn"], commits_made=True, path=p)
        hints = load_active_hints(path=p)
        warnings = format_hint_warnings(hints)
        assert len(warnings) >= 2
        assert any("humanize" in w for w in warnings)
        assert any("commit" in w for w in warnings)


# ---------------------------------------------------------------------------
# scan_audit_for_patterns — backfill from audit markdown
# ---------------------------------------------------------------------------

class TestScanAuditForPatterns:

    def _write_audit(self, path: Path, sessions: list[dict]) -> None:
        lines = []
        for i, s in enumerate(sessions):
            skills = ", ".join(s.get("skills", ["none"]))
            commits = "yes" if s.get("commits", False) else "no"
            lines.append(f"\n### Session — 2026-08-{i+1:02d} 12:00 UTC")
            lines.append(f"Project: youk")
            lines.append(f"Summary text")
            lines.append(f"Skills: {skills}")
            lines.append(f"CloseCluster: yes")
            lines.append(f"Commits: {commits}")
        path.write_text("\n".join(lines))

    def test_scans_sessions_and_records_patterns(self, tmp_path):
        audit = tmp_path / "audit.md"
        profile = tmp_path / "profile.json"
        self._write_audit(audit, [
            {"skills": ["learn"], "commits": True},
            {"skills": ["code-review"], "commits": True},
        ])
        result = scan_audit_for_patterns(audit, profile_path=profile)
        assert result["sessions_scanned"] == 2
        assert result["patterns_found"] == 2

    def test_absent_audit_returns_zeros(self, tmp_path):
        result = scan_audit_for_patterns(tmp_path / "nonexistent.md")
        assert result == {"sessions_scanned": 0, "patterns_found": 0}

    def test_sessions_with_humanize_not_counted(self, tmp_path):
        audit = tmp_path / "audit.md"
        profile = tmp_path / "profile.json"
        self._write_audit(audit, [
            {"skills": ["humanize", "learn"], "commits": True},
        ])
        result = scan_audit_for_patterns(audit, profile_path=profile)
        assert result["sessions_scanned"] == 1
        assert result["patterns_found"] == 0
