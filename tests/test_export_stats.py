"""Tests for scripts/export_stats.py — stats export artifact.

15 tests covering: session parsing, metric computation, minimum-N gate,
trajectory rendering, M+ denominator proxy, process caveat presence,
first-party framing, and edge cases (empty data, missing files).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/ to path so we can import export_stats directly.
_SCRIPTS = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import export_stats as es


# ── Helpers ────────────────────────────────────────────────────────────────────

def _audit_file(tmp_path: Path, entries: list[str]) -> Path:
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    content = "# Audit Log\n\n" + "\n\n".join(entries)
    (audit_dir / "2026-07.md").write_text(content, encoding="utf-8")
    return audit_dir


def _session(
    date: str = "2026-07-01",
    commits: str = "yes",
    close: str = "no",
    skills: str = "dev-loop",
) -> str:
    return (
        f"### Session — {date} 10:00 UTC\n"
        f"Some description.\n"
        f"Skills: {skills}\n"
        f"CloseCluster: {close}\n"
        f"Commits: {commits}\n"
    )


def _metrics_file(tmp_path: Path, entries: list[dict]) -> Path:
    state_dir = tmp_path / "youk" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    f = state_dir / "improvement-metrics.json"
    f.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return f


# ── Session parsing ────────────────────────────────────────────────────────────

def test_parse_session_with_capability_skill(tmp_path):
    audit_dir = _audit_file(tmp_path, [_session(skills="dev-loop, nfr-check")])
    sessions = es._parse_sessions(audit_dir)
    assert len(sessions) == 1
    assert sessions[0].has_capability_skill is True


def test_parse_session_no_capability_skill(tmp_path):
    audit_dir = _audit_file(tmp_path, [_session(skills="self_heal")])
    sessions = es._parse_sessions(audit_dir)
    assert sessions[0].has_capability_skill is False


def test_parse_session_skills_none(tmp_path):
    audit_dir = _audit_file(tmp_path, [_session(skills="none")])
    sessions = es._parse_sessions(audit_dir)
    assert sessions[0].skills == []
    assert sessions[0].has_capability_skill is False


def test_parse_session_close_cluster_yes(tmp_path):
    audit_dir = _audit_file(tmp_path, [_session(close="yes")])
    sessions = es._parse_sessions(audit_dir)
    assert sessions[0].has_close_cluster is True


def test_parse_session_commits_no(tmp_path):
    audit_dir = _audit_file(tmp_path, [_session(commits="no")])
    sessions = es._parse_sessions(audit_dir)
    assert sessions[0].has_commits is False


# ── Skill invocation rate (M+ denominator proxy) ───────────────────────────────

def test_skill_rate_excludes_no_work_sessions(tmp_path):
    """Sessions with no commits AND no skills don't count in denominator."""
    sessions_raw = [
        _session(date="2026-07-01", commits="yes", skills="dev-loop"),  # real work, cap skill
        _session(date="2026-07-02", commits="no", skills="none"),        # no work — excluded
        _session(date="2026-07-03", commits="no", skills="none"),        # no work — excluded
    ]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    pct, num, denom = es._skill_rate_meaningful(sessions)
    assert denom == 1  # only the commits=yes session
    assert num == 1
    assert pct == 100


def test_skill_rate_includes_skills_without_commits(tmp_path):
    """Skills=non-none counts as real work even if commits=no."""
    sessions_raw = [
        _session(date="2026-07-01", commits="no", skills="code-review"),
    ]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    pct, num, denom = es._skill_rate_meaningful(sessions)
    assert denom == 1


def test_skill_rate_empty_sessions():
    pct, num, denom = es._skill_rate_meaningful([])
    assert pct == 0 and num == 0 and denom == 0


# ── Minimum-N gate ─────────────────────────────────────────────────────────────

def test_minimum_n_warning_in_output(tmp_path):
    """Output contains low-data warning when session count < MIN_SESSIONS."""
    # Create 5 sessions (below threshold of 15)
    sessions_raw = [
        _session(date=f"2026-07-0{i}", commits="yes", skills="dev-loop")
        for i in range(1, 6)
    ]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    output = es._render(sessions, [])
    assert "Early data" in output


def test_no_minimum_n_warning_above_threshold(tmp_path):
    """No warning when session count >= MIN_SESSIONS."""
    sessions_raw = [
        _session(date=f"2026-07-{i:02d}", commits="yes", skills="dev-loop")
        for i in range(1, 16)  # exactly 15
    ]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    output = es._render(sessions, [])
    assert "Early data" not in output


# ── Trajectory and content ──────────────────────────────────────────────────────

def test_trajectory_table_deduplicates_by_date(tmp_path):
    """Multiple health snapshots on the same date → only last value appears."""
    metrics_f = _metrics_file(tmp_path, [
        {"timestamp": "2026-07-10T10:00:00Z", "org_score": 6.0},
        {"timestamp": "2026-07-10T18:00:00Z", "org_score": 6.3},  # same date, higher
    ])
    metrics = es._load_metrics(metrics_f)
    traj = es._org_score_trajectory(metrics)
    assert len(traj) == 1
    assert traj[0][1] == 6.3


def test_process_caveat_present_in_output(tmp_path):
    """Output must include the process-not-outcome caveat."""
    sessions = []
    output = es._render(sessions, [])
    assert "process discipline" in output
    assert "does not measure" in output.lower() or "does not mean" in output.lower()


def test_first_party_framing_present(tmp_path):
    """Output includes honest first-party framing with make export-stats CTA."""
    output = es._render([], [])
    assert "author's own sessions" in output
    assert "make export-stats" in output


def test_target_strings_present(tmp_path):
    """Every metric section includes a Target: line."""
    sessions_raw = [_session()]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    output = es._render(sessions, [])
    assert output.count("*Target:") >= 3  # org score, skill rate, close rate


# ── Edge cases ─────────────────────────────────────────────────────────────────

def test_missing_metrics_file_produces_output(tmp_path):
    """Script doesn't crash when improvement-metrics.json is absent."""
    sessions_raw = [_session()]
    audit_dir = _audit_file(tmp_path, sessions_raw)
    sessions = es._parse_sessions(audit_dir)
    metrics = es._load_metrics(tmp_path / "nonexistent.json")
    output = es._render(sessions, metrics)
    assert "youk — session stats" in output


def test_sparkline_empty_list():
    result = es._sparkline([])
    assert result == ""


def test_sparkline_single_value():
    result = es._sparkline([5.0])
    assert len(result) == 1
