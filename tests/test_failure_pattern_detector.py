"""Tests for failure_pattern_detector.py — cross-session failure pattern scanning."""
from __future__ import annotations
from pathlib import Path

import pytest

import failure_pattern_detector as fpd


@pytest.fixture
def audit_dir(tmp_path):
    d = tmp_path / "audit"
    d.mkdir()
    return d


def _write_month(audit_dir: Path, filename: str, sessions: list[dict]) -> None:
    """Write a synthetic YYYY-MM.md audit file with the given session blocks."""
    lines = []
    for s in sessions:
        lines.append(f"### Session — {s.get('ts', '2026-08-01 00:00 UTC')}")
        if "project" in s:
            lines.append(f"Project: {s['project']}")
        if "categories" in s:
            lines.append(f"FindingCategories: {','.join(s['categories'])}")
        lines.append("")
    (audit_dir / filename).write_text("\n".join(lines))


class TestScanEdgeCases:
    def test_missing_audit_dir_returns_empty(self, tmp_path):
        result = fpd.scan_failure_patterns(audit_dir=tmp_path / "nonexistent")
        assert result == []

    def test_empty_audit_dir_returns_empty(self, audit_dir):
        result = fpd.scan_failure_patterns(audit_dir=audit_dir)
        assert result == []

    def test_sessions_without_categories_returns_empty(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "ts": "2026-08-01"},
            {"project": "youk", "ts": "2026-08-02"},
            {"project": "youk", "ts": "2026-08-03"},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=1)
        assert result == []


class TestThreshold:
    def test_below_threshold_returns_empty(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": []},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        assert result == []

    def test_at_threshold_returns_alert(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": []},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        assert len(result) == 1
        assert result[0]["domain"] == "auth"
        assert result[0]["count"] == 3

    def test_two_categories_both_at_threshold(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth", "idempotency"]},
            {"project": "youk", "categories": ["auth", "idempotency"]},
            {"project": "youk", "categories": ["auth", "idempotency"]},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        domains = {a["domain"] for a in result}
        assert "auth" in domains
        assert "idempotency" in domains

    def test_duplicate_category_in_same_session_counts_once(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth", "auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        assert result[0]["count"] == 3


class TestSlugFilter:
    def test_only_matching_slug_counted(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "canopy", "categories": ["auth"]},
            {"project": "canopy", "categories": ["auth"]},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, slug="canopy", threshold=3)
        assert result == []

    def test_no_slug_filter_counts_all(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["auth"]},
            {"project": "canopy", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "canopy", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        assert len(result) == 1
        assert result[0]["domain"] == "auth"
        assert result[0]["count"] == 5


class TestLookback:
    def test_lookback_limits_sessions_scanned(self, audit_dir):
        # Oldest sessions written first (top of file), newest last.
        # After reversal, lookback=3 takes the 3 newest (bottom of file).
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": []},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
            {"project": "youk", "categories": ["auth"]},
        ])
        # lookback=3 reads the 3 newest sessions (last in file) which all have auth.
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, lookback_sessions=3, threshold=3)
        assert len(result) == 1
        assert result[0]["sessions_scanned"] == 3


class TestAlertFields:
    def test_alert_message_contains_domain_and_count(self, audit_dir):
        _write_month(audit_dir, "2026-08.md", [
            {"project": "youk", "categories": ["security"]},
            {"project": "youk", "categories": ["security"]},
            {"project": "youk", "categories": ["security"]},
        ])
        result = fpd.scan_failure_patterns(audit_dir=audit_dir, threshold=3)
        assert len(result) == 1
        msg = result[0]["message"]
        assert "security" in msg
        assert "3" in msg
        assert result[0]["sessions_scanned"] == 3
        assert result[0]["count"] == 3
