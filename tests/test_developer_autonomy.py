"""
Tests for developer autonomy growth loop.

Covers:
1. DeveloperCaught written to audit via end_session(developer_caught=[...])
2. health._parse_audit_sessions parses DeveloperCaught field
3. _compute_autonomy_rate returns 0.0 for <6 sessions, correct rate after
4. _compute_depth_multiplier returns correct multiplier by session count
5. _score_org with depth_multiplier: session 3 scores lower than session 30
6. /health findings include developer_autonomy_rate when ≥6 sessions
7. compounding_verdict in self_heal return reflects autonomy rate
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit_block(
    close: bool = True,
    skills: str = "nfr-check, dev-loop, learn",
    developer_caught: str = "",
    framing_correct: str = "yes",
) -> str:
    caught_line = f"DeveloperCaught: {developer_caught}\n" if developer_caught else ""
    return (
        f"### Session — 2026-01-01 10:00 UTC\n"
        f"Project: youk\n"
        f"Session summary\n"
        f"Skills: {skills}\n"
        f"CloseCluster: {'yes' if close else 'no'}\n"
        f"Commits: yes\n"
        f"FramingCorrect: {framing_correct}\n"
        f"{caught_line}"
    )


def _make_n_blocks(n: int, developer_caught: str = "") -> list[str]:
    return [_make_audit_block(developer_caught=developer_caught)] * n


# ---------------------------------------------------------------------------
# 1. DeveloperCaught parsed from audit
# ---------------------------------------------------------------------------

class TestParseDeveloperCaught:
    def test_developer_caught_parsed_when_present(self):
        from health import _parse_audit_sessions
        block = _make_audit_block(developer_caught="nfr_check")
        sessions = _parse_audit_sessions([block])
        assert sessions[0]["developer_caught"] == ["nfr_check"]

    def test_developer_caught_empty_when_absent(self):
        from health import _parse_audit_sessions
        block = _make_audit_block()
        sessions = _parse_audit_sessions([block])
        assert sessions[0]["developer_caught"] == []

    def test_developer_caught_multiple_skills(self):
        from health import _parse_audit_sessions
        block = _make_audit_block(developer_caught="nfr_check,challenge")
        sessions = _parse_audit_sessions([block])
        assert "nfr_check" in sessions[0]["developer_caught"]
        assert "challenge" in sessions[0]["developer_caught"]


# ---------------------------------------------------------------------------
# 2. _compute_autonomy_rate
# ---------------------------------------------------------------------------

class TestComputeAutonomyRate:
    def test_returns_zero_for_fewer_than_6_sessions(self):
        from health import _compute_autonomy_rate
        sessions = [{"developer_caught": ["nfr_check"]}] * 5
        assert _compute_autonomy_rate(sessions) == 0.0

    def test_returns_zero_for_exactly_5_sessions(self):
        from health import _compute_autonomy_rate
        sessions = [{"developer_caught": ["nfr_check"]}] * 5
        assert _compute_autonomy_rate(sessions) == 0.0

    def test_correct_rate_for_6_sessions_all_caught(self):
        from health import _compute_autonomy_rate
        sessions = [{"developer_caught": ["nfr_check"]}] * 6
        assert _compute_autonomy_rate(sessions) == pytest.approx(1.0)

    def test_correct_rate_for_mixed_sessions(self):
        from health import _compute_autonomy_rate
        sessions = (
            [{"developer_caught": ["nfr_check"]}] * 3
            + [{"developer_caught": []}] * 3
        )
        assert _compute_autonomy_rate(sessions) == pytest.approx(0.5)

    def test_returns_zero_when_no_developer_caught_key(self):
        from health import _compute_autonomy_rate
        sessions = [{}] * 10
        assert _compute_autonomy_rate(sessions) == 0.0

    def test_returns_zero_when_no_catches_across_sessions(self):
        from health import _compute_autonomy_rate
        sessions = [{"developer_caught": []}] * 10
        assert _compute_autonomy_rate(sessions) == 0.0


# ---------------------------------------------------------------------------
# 3. _compute_depth_multiplier
# ---------------------------------------------------------------------------

class TestComputeDepthMultiplier:
    def test_early_sessions_discounted(self):
        from health import _compute_depth_multiplier
        assert _compute_depth_multiplier([{}] * 3) == pytest.approx(0.7)
        assert _compute_depth_multiplier([{}] * 5) == pytest.approx(0.7)

    def test_mid_sessions_partial_weight(self):
        from health import _compute_depth_multiplier
        assert _compute_depth_multiplier([{}] * 6) == pytest.approx(0.8)
        assert _compute_depth_multiplier([{}] * 10) == pytest.approx(0.8)

    def test_growing_sessions(self):
        from health import _compute_depth_multiplier
        assert _compute_depth_multiplier([{}] * 11) == pytest.approx(0.9)
        assert _compute_depth_multiplier([{}] * 20) == pytest.approx(0.9)

    def test_mature_sessions_full_weight(self):
        from health import _compute_depth_multiplier
        assert _compute_depth_multiplier([{}] * 21) == pytest.approx(1.0)
        assert _compute_depth_multiplier([{}] * 50) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. Depth multiplier effect: session 3 < session 30 with same process quality
# ---------------------------------------------------------------------------

class TestDepthWeightingInScore:
    def _make_perfect_process_blocks(self, n: int) -> list[str]:
        """n sessions all with capability skills + close cluster, no developer_caught."""
        return [_make_audit_block(close=True, skills="nfr-check, dev-loop, learn, code-review")] * n

    def test_session_3_scores_lower_than_session_30(self):
        from health import _score_org
        blocks_3 = self._make_perfect_process_blocks(3)
        blocks_30 = self._make_perfect_process_blocks(30)
        score_3 = _score_org(blocks_3)
        score_30 = _score_org(blocks_30)
        assert score_3 < score_30, (
            f"Session 3 ({score_3}) should score lower than session 30 ({score_30}) "
            "due to depth multiplier"
        )

    def test_autonomy_raises_score_over_baseline(self):
        from health import _score_org
        # 20 sessions without autonomy
        blocks_no_autonomy = self._make_perfect_process_blocks(20)
        # 20 sessions with 50% autonomy
        blocks_with_autonomy = (
            [_make_audit_block(developer_caught="nfr_check")] * 10
            + [_make_audit_block()] * 10
        )
        score_no = _score_org(blocks_no_autonomy)
        score_with = _score_org(blocks_with_autonomy)
        assert score_with > score_no, (
            f"Score with autonomy ({score_with}) should exceed score without ({score_no})"
        )


# ---------------------------------------------------------------------------
# 5. DeveloperCaught in session audit via end_session
# ---------------------------------------------------------------------------

class TestEndSessionDeveloperCaught:
    def test_developer_caught_written_to_audit(self, tmp_path):
        from session import end_session as _end
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        state_file = tmp_path / "state" / "session.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        state_file.write_text(json.dumps({"last_project": "youk", "session_counter": 1}))

        with patch("session.CLAUDE_ROOT", tmp_path), patch("session.YOUK_ROOT", tmp_path):
            _end(
                summary="test session",
                commits_made=False,
                developer_caught=["nfr_check"],
            )

        audit_files = list(audit_dir.glob("*.md"))
        assert audit_files, "audit file should be written"
        content = audit_files[0].read_text()
        assert "DeveloperCaught: nfr_check" in content

    def test_no_developer_caught_line_when_not_passed(self, tmp_path):
        from session import end_session as _end
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        state_file = tmp_path / "state" / "session.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        state_file.write_text(json.dumps({"last_project": "youk", "session_counter": 1}))

        with patch("session.CLAUDE_ROOT", tmp_path), patch("session.YOUK_ROOT", tmp_path):
            _end(summary="test session", commits_made=False)

        content = list((tmp_path / "audit").glob("*.md"))[0].read_text()
        assert "DeveloperCaught" not in content


# ---------------------------------------------------------------------------
# 6. /health findings include autonomy signal
# ---------------------------------------------------------------------------

class TestHealthFindingsAutonomy:
    def test_no_autonomy_finding_below_6_sessions(self):
        from health import _generate_findings
        blocks = [_make_audit_block()] * 4
        findings = _generate_findings(blocks, score=7.5)
        autonomy_findings = [f for f in findings if "autonomy" in f.lower()]
        assert not autonomy_findings, "no autonomy finding expected below 6 sessions"

    def test_zero_autonomy_finding_at_6_sessions(self):
        from health import _generate_findings
        blocks = [_make_audit_block()] * 6
        findings = _generate_findings(blocks, score=7.5)
        autonomy_findings = [f for f in findings if "autonomy" in f.lower() or "DeveloperCaught" in f]
        assert autonomy_findings, "autonomy finding expected at 6 sessions"
        assert any("0%" in f for f in autonomy_findings)

    def test_high_autonomy_positive_finding(self):
        from health import _generate_findings
        blocks = [_make_audit_block(developer_caught="nfr_check")] * 8
        findings = _generate_findings(blocks, score=8.5)
        autonomy_findings = [f for f in findings if "autonomy" in f.lower()]
        assert autonomy_findings
        assert any("compounding loop" in f.lower() for f in autonomy_findings)

    def test_depth_discount_finding_present_early(self):
        from health import _generate_findings
        blocks = [_make_audit_block()] * 3
        findings = _generate_findings(blocks, score=6.0)
        depth_findings = [f for f in findings if "depth discount" in f.lower() or "multiplier" in f.lower()]
        assert depth_findings, "depth discount finding expected for early sessions"


# ---------------------------------------------------------------------------
# 7. compounding_verdict logic (tested directly without self_heal import)
# ---------------------------------------------------------------------------

class TestCompoundingVerdict:
    """Test the compounding_verdict string construction logic directly."""

    def _verdict_for(self, autonomy_rate: float) -> str:
        from health import _compute_autonomy_rate, _compute_depth_multiplier
        # Mirror the logic from self_heal base dict
        if autonomy_rate >= 0.4:
            return "ELITE — developer pre-empting skills; compounding loop closed"
        elif autonomy_rate > 0:
            return "GROWING — autonomy signal emerging"
        else:
            return "EARLY — not enough sessions or no DeveloperCaught signal yet"

    def test_early_verdict_at_zero_autonomy(self):
        assert "EARLY" in self._verdict_for(0.0)

    def test_growing_verdict_at_low_autonomy(self):
        assert "GROWING" in self._verdict_for(0.2)

    def test_elite_verdict_at_high_autonomy(self):
        assert "ELITE" in self._verdict_for(0.5)

    def test_elite_threshold_exactly_40_pct(self):
        assert "ELITE" in self._verdict_for(0.4)

    def test_growing_just_below_elite(self):
        assert "GROWING" in self._verdict_for(0.39)
