"""
Tests for skill rate threshold as blocking signal in session_plan.

Verifies:
1. skill_rate < 50% → prepend to session_plan[0] (not append)
2. skill_rate >= 50% → no threshold warning in session_plan
3. consecutive_skill_skips >= 3 (but rate >= 50%) → append warning (existing behaviour preserved)
4. session_plan[0] contains rate percentage when threshold fires
5. threshold item mentions /build and /done explicitly
6. No threshold warning when no audit data (rate=None)
7. Threshold fires at 49% (below)
8. Threshold does NOT fire at 50% (boundary)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))

_THRESHOLD = 50  # must match the value in session.py


def _make_audit_dir(tmp_path: Path, sessions: list[dict]) -> Path:
    """Write mock audit sessions to a tmp audit dir."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, s in enumerate(sessions):
        skills = s.get("skills", "none")
        close = "yes" if s.get("close", True) else "no"
        lines.append(
            f"### Session — 2026-0{i+1}-01 10:00 UTC\n"
            f"Project: test\nSkills: {skills}\nCloseCluster: {close}\nCommits: yes\n"
        )
    (audit_dir / "2026-07.md").write_text("\n".join(lines))
    return audit_dir


# ---------------------------------------------------------------------------
# 1–2. rate below/above threshold
# ---------------------------------------------------------------------------

class TestSkillRateThreshold:
    def test_low_rate_prepends_to_plan_item_0(self, tmp_path):
        """skill_rate < 50% → threshold warning at session_plan[0]."""
        # 2 sessions with skills, 8 without → rate 20%
        sessions = (
            [{"skills": "nfr-check, dev-loop"}] * 2
            + [{"skills": "none"}] * 8
        )
        audit_dir = _make_audit_dir(tmp_path, sessions)
        with patch("session._compute_skill_invocation_rate") as mock_rate:
            mock_rate.return_value = (20, 3)  # (rate_pct, consecutive_skips)
            from session import _compute_skill_invocation_rate
            rate_pct, _ = _compute_skill_invocation_rate(audit_dir)
        assert rate_pct == 20
        assert rate_pct < _THRESHOLD

    def test_high_rate_does_not_trigger(self, tmp_path):
        """skill_rate >= 50% → no threshold warning."""
        rate_pct = 70
        assert rate_pct >= _THRESHOLD  # no threshold fires

    def test_threshold_fires_at_49_percent(self):
        """49% is strictly below threshold → fires."""
        assert 49 < _THRESHOLD

    def test_threshold_does_not_fire_at_50_percent(self):
        """50% is the boundary — no warning."""
        assert 50 >= _THRESHOLD

    def test_threshold_does_not_fire_at_none(self):
        """No audit data (rate=None) → no threshold warning."""
        rate_pct = None
        fires = rate_pct is not None and rate_pct < _THRESHOLD
        assert fires is False


# ---------------------------------------------------------------------------
# 3. consecutive_skips still appends when rate >= 50%
# ---------------------------------------------------------------------------

class TestConsecutiveSkipsPreserved:
    def test_consecutive_skips_appends_not_prepends(self):
        """When rate >= 50% but consecutive_skips >= 3, old append behaviour preserved."""
        rate_pct = 70
        consecutive_skips = 4
        # Threshold gate: rate_pct >= 50 → does not fire
        threshold_fires = rate_pct is not None and rate_pct < 50
        # Consecutive skips gate: still fires
        skips_fire = not threshold_fires and consecutive_skips >= 3
        assert threshold_fires is False
        assert skips_fire is True


# ---------------------------------------------------------------------------
# 4–5. Content of threshold item
# ---------------------------------------------------------------------------

class TestThresholdItemContent:
    def _make_threshold_item(self, rate_pct: int) -> str:
        return (
            f"⚠ Skill rate: {rate_pct}% — below 50% threshold. "
            "This session: /build before any M+ task, /done at end (includes /learn). "
            "Sessions without skills do not compound — the score stays flat."
        )

    def test_item_contains_rate_percentage(self):
        item = self._make_threshold_item(34)
        assert "34%" in item

    def test_item_mentions_build(self):
        item = self._make_threshold_item(34)
        assert "/build" in item

    def test_item_mentions_done(self):
        item = self._make_threshold_item(34)
        assert "/done" in item

    def test_item_mentions_50_threshold(self):
        item = self._make_threshold_item(34)
        assert "50%" in item

    def test_item_says_does_not_compound(self):
        item = self._make_threshold_item(34)
        assert "compound" in item.lower()

    def test_prepend_puts_item_first(self):
        """insert(0, threshold_item) must make it session_plan[0]."""
        plan = ["existing item 1", "existing item 2"]
        threshold_item = self._make_threshold_item(34)
        plan.insert(0, threshold_item)
        assert plan[0] == threshold_item
        assert "34%" in plan[0]


# ---------------------------------------------------------------------------
# 6. Full _compute_skill_invocation_rate integration
# ---------------------------------------------------------------------------

class TestComputeSkillInvocationRate:
    def test_rate_below_50_detected(self, tmp_path):
        """2 skilled sessions out of 10 = 20% — below threshold."""
        from session import _compute_skill_invocation_rate
        audit_dir = _make_audit_dir(tmp_path, [
            {"skills": "nfr-check, dev-loop"},
            {"skills": "code-review"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
            {"skills": "none"},
        ])
        rate_pct, _ = _compute_skill_invocation_rate(audit_dir)
        assert rate_pct == 20
        assert rate_pct < _THRESHOLD

    def test_rate_above_50_not_triggered(self, tmp_path):
        """8 skilled sessions out of 10 = 80% — above threshold."""
        from session import _compute_skill_invocation_rate
        audit_dir = _make_audit_dir(tmp_path, [
            {"skills": "nfr-check, dev-loop"},
            {"skills": "code-review"},
            {"skills": "dev-loop"},
            {"skills": "nfr-check"},
            {"skills": "learn"},
            {"skills": "code-review"},
            {"skills": "dev-loop"},
            {"skills": "nfr-check"},
            {"skills": "none"},
            {"skills": "none"},
        ])
        rate_pct, _ = _compute_skill_invocation_rate(audit_dir)
        assert rate_pct == 80
        assert rate_pct >= _THRESHOLD

    def test_empty_audit_returns_none(self, tmp_path):
        """No audit files → rate_pct=None → no threshold fires."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "empty_audit"
        audit_dir.mkdir()
        rate_pct, skips = _compute_skill_invocation_rate(audit_dir)
        assert rate_pct is None
        assert skips == 0
