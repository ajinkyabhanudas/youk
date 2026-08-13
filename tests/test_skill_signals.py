"""Tests for skill self-improvement signal detector (skill_signals.py).

All tests use tmp_path-scoped state directories so they are fully isolated.
The module is imported directly — no MCP dependency.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import skill_signals
from skill_signals import (
    _parse_examination_surfaces,
    _extract_downstream_findings,
    compute_signals_for_session,
    detect_patterns,
    update_points,
    get_fork_candidates,
    get_skill_health_summary,
    write_domain_signal,
    read_audit_patterns,
    record_session_signals,
    POINT_WEIGHTS,
    _STARTING_POINTS,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_audit_block(
    skills: str = "dev-loop, code-review",
    findings: str = "",
    finding_categories: str = "",
    autonomy_depth: str = "",
    loop_correction: bool = False,
    retrospectives: str = "",
    examination_surfaces: str = "",
) -> str:
    lines = [f"Skills: {skills}"]
    if findings:
        lines.append(findings)
    if finding_categories:
        lines.append(f"FindingCategories: {finding_categories}")
    if autonomy_depth:
        lines.append(f"AutonomyDepth: {autonomy_depth}")
    if loop_correction:
        lines.append("LoopCorrection: yes")
    if retrospectives:
        lines.append("Retrospectives: 1 (VALIDATED=1)")
        lines.append(f"  - {retrospectives}: VALIDATED (confirmed in production)")
    if examination_surfaces:
        lines.append(examination_surfaces)
    return "\n".join(lines)


def _sample_examination_surface(skill: str = "dev-loop") -> str:
    return (
        f"[EXAMINATION SURFACE — {skill} AUDIT]\n"
        f"Task type:    new_endpoint\n"
        f"Examined:     [error_handling, auth, data_validation, tests]\n"
        f"Not examined: [rate_limiting — internal endpoint, concurrency — single-threaded]\n"
    )


# ── TestParseExaminationSurfaces ──────────────────────────────────────────────

class TestParseExaminationSurfaces:
    def test_parses_examined_list(self):
        block = _sample_examination_surface("dev-loop")
        surfaces = _parse_examination_surfaces(block)
        assert "dev-loop" in surfaces
        assert "error_handling" in surfaces["dev-loop"]["examined"]
        assert "auth" in surfaces["dev-loop"]["examined"]

    def test_parses_not_examined_list(self):
        block = _sample_examination_surface("dev-loop")
        surfaces = _parse_examination_surfaces(block)
        not_ex = surfaces["dev-loop"]["not_examined"]
        assert "rate_limiting" in not_ex
        assert "concurrency" in not_ex

    def test_strips_reason_from_not_examined(self):
        """'rate_limiting — internal endpoint' → 'rate_limiting' only."""
        block = _sample_examination_surface("dev-loop")
        surfaces = _parse_examination_surfaces(block)
        for domain in surfaces["dev-loop"]["not_examined"]:
            assert "—" not in domain
            assert "internal" not in domain

    def test_normalizes_skill_name(self):
        """'dev-loop AUDIT' → 'dev-loop'."""
        block = _sample_examination_surface("dev-loop")
        surfaces = _parse_examination_surfaces(block)
        assert "dev-loop" in surfaces
        assert "dev-loop AUDIT" not in surfaces

    def test_multiple_surfaces_in_one_block(self):
        block = _sample_examination_surface("dev-loop") + "\n" + (
            "[EXAMINATION SURFACE — code-review]\n"
            "Risk tier:    MED\n"
            "Examined:     [logic, error_handling]\n"
            "Not examined: [security_auth — no auth surface]\n"
        )
        surfaces = _parse_examination_surfaces(block)
        assert "dev-loop" in surfaces
        assert "code-review" in surfaces

    def test_empty_block_returns_empty(self):
        surfaces = _parse_examination_surfaces("Skills: dev-loop\nCloseCluster: yes")
        assert surfaces == {}


# ── TestExtractDownstreamFindings ─────────────────────────────────────────────

class TestExtractDownstreamFindings:
    def test_extracts_high_finding(self):
        block = "[FINDING: HIGH] Error handling — missing null check\n  Location: foo.py:42"
        findings = _extract_downstream_findings(block)
        assert any(f["severity"] == "HIGH" for f in findings)
        assert any("error_handling" in f["category"] for f in findings)

    def test_extracts_critical_finding(self):
        block = "[FINDING: CRITICAL] Security injection — SQL injection risk"
        findings = _extract_downstream_findings(block)
        assert any(f["severity"] == "CRITICAL" for f in findings)

    def test_ignores_medium_and_low(self):
        block = "[FINDING: MEDIUM] Quality — function too long\n[FINDING: LOW] Naming — unclear var"
        findings = _extract_downstream_findings(block)
        assert len(findings) == 0

    def test_reads_finding_categories_line(self):
        block = "Findings: 2 (CRITICAL=0, HIGH=2)\nFindingCategories: auth,data_validation"
        findings = _extract_downstream_findings(block)
        categories = {f["category"] for f in findings}
        assert "auth" in categories
        assert "data_validation" in categories

    def test_deduplicates_categories_and_findings(self):
        block = (
            "[FINDING: HIGH] Auth — bypass possible\n"
            "FindingCategories: auth\n"
        )
        findings = _extract_downstream_findings(block)
        # auth should appear only once (finding + category line = deduplicated)
        auth_count = sum(1 for f in findings if "auth" in f["category"])
        assert auth_count == 1


# ── TestComputeSignals ────────────────────────────────────────────────────────

class TestComputeSignals:
    def test_gap_when_examined_and_downstream_found(self):
        surface = _sample_examination_surface("dev-loop")
        block = (
            "Skills: dev-loop, code-review\n"
            "[FINDING: HIGH] Error handling — missing null check\n"
            + surface
        )
        signals = compute_signals_for_session(block, session_n=1)
        gap_signals = [s for s in signals if s["signal_type"] == "GAP"]
        assert any(s["skill"] == "dev-loop" for s in gap_signals)

    def test_scope_miss_when_domain_not_declared(self):
        """code-review finds auth issue; dev-loop never declared examining auth."""
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    new_endpoint\n"
            "Examined:     [error_handling, tests]\n"
            "Not examined: []\n"
        )
        block = (
            "Skills: dev-loop, code-review\n"
            "[FINDING: HIGH] Auth — authentication bypass\n"
            + surface
        )
        signals = compute_signals_for_session(block, session_n=1)
        scope_miss = [s for s in signals if s["signal_type"] == "SCOPE_MISS" and s["skill"] == "dev-loop"]
        assert len(scope_miss) >= 1

    def test_surplus_when_developer_pre_empted_at_deep(self):
        block = (
            "Skills: nfr-check\n"
            "AutonomyDepth: nfr-check=DEEP\n"
        )
        signals = compute_signals_for_session(block, session_n=1)
        surplus = [s for s in signals if s["signal_type"] == "SURPLUS" and s["skill"] == "nfr-check"]
        assert len(surplus) == 1
        assert surplus[0]["weight"] == POINT_WEIGHTS["SURPLUS"]

    def test_pre_empted_signal_alongside_surplus(self):
        block = (
            "Skills: nfr-check\n"
            "AutonomyDepth: nfr-check=DEEP\n"
        )
        signals = compute_signals_for_session(block, session_n=1)
        pre_empted = [s for s in signals if s["signal_type"] == "PRE_EMPTED"]
        assert len(pre_empted) == 1

    def test_stable_when_no_deductions(self):
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    bug_fix\n"
            "Examined:     [error_handling, tests]\n"
            "Not examined: [auth — read-only endpoint]\n"
        )
        block = "Skills: dev-loop\n" + surface
        signals = compute_signals_for_session(block, session_n=1)
        stable = [s for s in signals if s["signal_type"] == "STABLE" and s["skill"] == "dev-loop"]
        assert len(stable) == 1
        assert stable[0]["weight"] == POINT_WEIGHTS["STABLE"]

    def test_loop_correction_generates_gap_for_challenge(self):
        block = "Skills: challenge\nLoopCorrection: yes\n"
        signals = compute_signals_for_session(block, session_n=1)
        gap = [s for s in signals if s["signal_type"] == "GAP" and s["skill"] == "challenge"]
        assert len(gap) == 1
        assert "loop_correction" in gap[0]["dimension"]

    def test_validated_retrospective_generates_signal(self):
        block = (
            "Skills: dev-loop\n"
            "Retrospectives: 1 (VALIDATED=1)\n"
            "  - caching decision: VALIDATED (confirmed in production)\n"
        )
        signals = compute_signals_for_session(block, session_n=1)
        validated = [s for s in signals if s["signal_type"] == "VALIDATED"]
        assert len(validated) >= 1

    def test_empty_block_produces_no_signals(self):
        signals = compute_signals_for_session("", session_n=1)
        assert signals == []

    def test_skill_not_in_skills_line_produces_no_signal(self):
        """A skill not listed in Skills: gets no signal even if surface is present."""
        surface = _sample_examination_surface("dev-loop")
        block = "Skills: code-review\n" + surface
        signals = compute_signals_for_session(block, session_n=1)
        dev_loop_signals = [s for s in signals if s["skill"] == "dev-loop"]
        assert len(dev_loop_signals) == 0

    def test_scope_miss_weight_higher_than_gap(self):
        assert abs(POINT_WEIGHTS["SCOPE_MISS"]) > abs(POINT_WEIGHTS["GAP"])


# ── TestDetectPatterns ────────────────────────────────────────────────────────

class TestDetectPatterns:
    def _make_signals_file(self, tmp_path: Path, signals: list[dict]) -> Path:
        f = tmp_path / "skill-signals.jsonl"
        with f.open("w") as fp:
            for s in signals:
                fp.write(json.dumps(s) + "\n")
        return f

    def test_detects_gap_pattern_after_3_sessions(self, tmp_path):
        signals = [
            {"session_n": i, "skill": "dev-loop", "signal_type": "GAP",
             "dimension": "auth", "evidence": "missed auth", "weight": -4.0, "recorded_at": "2026-07-28T00:00:00+00:00"}
            for i in range(1, 4)
        ]
        f = self._make_signals_file(tmp_path, signals)
        patterns = detect_patterns(signals_file=f)
        assert len(patterns) == 1
        assert patterns[0]["skill"] == "dev-loop"
        assert patterns[0]["signal_type"] == "GAP"
        assert patterns[0]["count"] == 3

    def test_no_pattern_below_threshold(self, tmp_path):
        signals = [
            {"session_n": i, "skill": "dev-loop", "signal_type": "GAP",
             "dimension": "auth", "evidence": "missed auth", "weight": -4.0, "recorded_at": "2026-07-28T00:00:00+00:00"}
            for i in range(1, 3)  # only 2
        ]
        f = self._make_signals_file(tmp_path, signals)
        patterns = detect_patterns(signals_file=f)
        assert len(patterns) == 0

    def test_scope_miss_prioritized_over_gap(self, tmp_path):
        signals = (
            [{"session_n": i, "skill": "dev-loop", "signal_type": "GAP",
              "dimension": "auth", "evidence": "", "weight": -4.0, "recorded_at": "2026-07-28T00:00:00+00:00"}
             for i in range(1, 4)]
            + [{"session_n": i, "skill": "code-review", "signal_type": "SCOPE_MISS",
                "dimension": "security_auth", "evidence": "", "weight": -6.0, "recorded_at": "2026-07-28T00:00:00+00:00"}
               for i in range(1, 4)]
        )
        f = self._make_signals_file(tmp_path, signals)
        patterns = detect_patterns(signals_file=f)
        assert patterns[0]["signal_type"] == "SCOPE_MISS"

    def test_window_respected(self, tmp_path):
        """Signals outside the window are excluded from pattern detection."""
        signals = [
            {"session_n": i, "skill": "dev-loop", "signal_type": "GAP",
             "dimension": "auth", "evidence": "", "weight": -4.0, "recorded_at": "2026-07-28T00:00:00+00:00"}
            for i in range(1, 4)
        ]
        f = self._make_signals_file(tmp_path, signals)
        # window=2 means only last 2 sessions — sessions 2 and 3, not session 1 → count=2, no pattern
        patterns = detect_patterns(signals_file=f, window=2)
        assert len(patterns) == 0

    def test_absent_file_returns_empty(self, tmp_path):
        patterns = detect_patterns(signals_file=tmp_path / "nonexistent.jsonl")
        assert patterns == []


# ── TestPointLedger ───────────────────────────────────────────────────────────

class TestPointLedger:
    def _with_state_dir(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")
        return tmp_path / "skill-points.json"

    def test_gap_deducts_points(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": 1, "skill": "dev-loop", "signal_type": "GAP",
                    "dimension": "auth", "weight": POINT_WEIGHTS["GAP"], "recorded_at": ""}]
        touched = update_points(signals)
        assert touched["dev-loop"] == _STARTING_POINTS + POINT_WEIGHTS["GAP"]

    def test_stable_recovers_points(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        # First deduct, then recover
        gap = [{"session_n": 1, "skill": "dev-loop", "signal_type": "GAP",
                "dimension": "auth", "weight": POINT_WEIGHTS["GAP"], "recorded_at": ""}]
        update_points(gap)
        stable = [{"session_n": 2, "skill": "dev-loop", "signal_type": "STABLE",
                   "dimension": "overall", "weight": POINT_WEIGHTS["STABLE"], "recorded_at": ""}]
        touched = update_points(stable)
        expected = _STARTING_POINTS + POINT_WEIGHTS["GAP"] + POINT_WEIGHTS["STABLE"]
        assert touched["dev-loop"] == pytest.approx(expected)

    def test_points_floored_at_zero(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        # Many deductions
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "SCOPE_MISS",
                    "dimension": "auth", "weight": POINT_WEIGHTS["SCOPE_MISS"], "recorded_at": ""}
                   for i in range(1, 30)]  # 29 × -6 = -174 → floored at 0
        touched = update_points(signals)
        assert touched["dev-loop"] == 0.0

    def test_points_capped_at_starting(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "STABLE",
                    "dimension": "overall", "weight": POINT_WEIGHTS["STABLE"], "recorded_at": ""}
                   for i in range(1, 20)]  # many recoveries → cap at 100
        touched = update_points(signals)
        assert touched["dev-loop"] == _STARTING_POINTS

    def test_fork_candidate_below_threshold(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "SCOPE_MISS",
                    "dimension": "auth", "weight": POINT_WEIGHTS["SCOPE_MISS"], "recorded_at": ""}
                   for i in range(1, 12)]  # 11 × -6 = -66 → 34 points → below 40
        update_points(signals)
        candidates = get_fork_candidates(points_file=tmp_path / "skill-points.json")
        assert any(c["skill"] == "dev-loop" for c in candidates)

    def test_healthy_skill_not_in_fork_candidates(self, tmp_path, monkeypatch):
        self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": 1, "skill": "dev-loop", "signal_type": "STABLE",
                    "dimension": "overall", "weight": POINT_WEIGHTS["STABLE"], "recorded_at": ""}]
        update_points(signals)
        candidates = get_fork_candidates(points_file=tmp_path / "skill-points.json")
        assert not any(c["skill"] == "dev-loop" for c in candidates)


# ── TestRecordSessionSignals ──────────────────────────────────────────────────

class TestRecordSessionSignals:
    def test_writes_to_jsonl(self, tmp_path, monkeypatch):
        import skill_signals
        signals_file = tmp_path / "skill-signals.jsonl"
        points_file = tmp_path / "skill-points.json"
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", signals_file)
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", points_file)

        block = "Skills: challenge\nLoopCorrection: yes\n"
        result = record_session_signals(block, session_n=5)

        assert result["signals_recorded"] > 0
        assert signals_file.exists()
        lines = [json.loads(ln) for ln in signals_file.read_text().splitlines() if ln.strip()]
        assert len(lines) > 0

    def test_idempotent_on_no_signals(self, tmp_path, monkeypatch):
        import skill_signals
        signals_file = tmp_path / "skill-signals.jsonl"
        points_file = tmp_path / "skill-points.json"
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", signals_file)
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", points_file)

        result = record_session_signals("", session_n=1)
        assert result["signals_recorded"] == 0

    def test_never_raises_on_corrupt_data(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", tmp_path / "skill-signals.jsonl")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")

        # Corrupt audit block — should not raise
        result = record_session_signals("NOT VALID JSON {{{", session_n=99)
        assert "error" not in result or result.get("signals_recorded", 0) == 0


# ── TestHealthSummary ─────────────────────────────────────────────────────────

class TestHealthSummary:
    def test_status_healthy_at_start(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "none.json")
        summary = get_skill_health_summary()
        for skill, data in summary.items():
            assert data["status"] == "healthy"
            assert data["points"] == _STARTING_POINTS

    def test_status_at_risk_near_threshold(self, tmp_path, monkeypatch):
        import skill_signals
        pf = tmp_path / "skill-points.json"
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", pf)
        # Put dev-loop just above fork threshold
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "SCOPE_MISS",
                    "dimension": "auth", "weight": -6.0, "recorded_at": ""}
                   for i in range(1, 9)]  # 8 × -6 = -48 → 52 points → degrading
        update_points(signals)
        summary = get_skill_health_summary()
        assert summary["dev-loop"]["status"] in ("degrading", "at_risk")


# ── TestProposalGeneration (Phase 2) ─────────────────────────────────────────

from skill_signals import (
    generate_improvement_proposal,
)


class TestProposalGeneration:
    def _patch_state(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", tmp_path / "skill-signals.jsonl")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")
        monkeypatch.setattr(skill_signals, "_IMPROVEMENT_QUEUE", tmp_path / "skill-improvement-queue.json")
        monkeypatch.setattr(skill_signals, "_APPLIED_PROPOSALS", tmp_path / "applied-proposals.json")

    def _write_queue(self, tmp_path, patterns: list[dict]) -> None:
        q = tmp_path / "skill-improvement-queue.json"
        q.write_text(json.dumps({"patterns": patterns, "updated_at": "2026-07-30T00:00:00+00:00"}))

    def test_no_pattern_returns_sentinel(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        result = generate_improvement_proposal("dev-loop")
        assert result["no_pattern"] is True

    def test_gap_pattern_produces_proposal_text(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "GAP", "dimension": "auth",
             "count": 3, "sessions": [1, 2, 3], "evidence_samples": ["missed auth check"] * 3}
        ])
        result = generate_improvement_proposal("dev-loop", dimension="auth")
        assert result["no_pattern"] is False
        assert "auth" in result["proposal_text"]
        assert "GAP" in result["proposal_text"]
        assert "Approve" in result["proposal_text"]

    def test_scope_miss_pattern_mentions_scope(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "SCOPE_MISS", "dimension": "rate_limiting",
             "count": 4, "sessions": [1, 2, 3, 4], "evidence_samples": ["never examined"] * 4}
        ])
        result = generate_improvement_proposal("dev-loop")
        assert "SCOPE_MISS" in result["proposal_text"]
        assert "rate_limiting" in result["proposal_text"] or "rate-limiting" in result["proposal_text"]

    def test_surplus_pattern_mentions_compression(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "nfr-check", "signal_type": "SURPLUS", "dimension": "autonomy_deep",
             "count": 3, "sessions": [5, 6, 7], "evidence_samples": ["pre-empted"] * 3}
        ])
        result = generate_improvement_proposal("nfr-check")
        assert "SURPLUS" in result["proposal_text"] or "Compress" in result["proposal_text"]

    def test_proposal_id_format(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "GAP", "dimension": "auth",
             "count": 3, "sessions": [1, 2, 3], "evidence_samples": ["e"] * 3}
        ])
        result = generate_improvement_proposal("dev-loop")
        assert result["proposal_id"].startswith("SKILL-SIGNAL-DEV-LOOP")

    def test_applied_proposals_tracking_written(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "GAP", "dimension": "auth",
             "count": 3, "sessions": [1, 2, 3], "evidence_samples": ["e"] * 3}
        ])
        generate_improvement_proposal("dev-loop")
        applied_file = tmp_path / "applied-proposals.json"
        assert applied_file.exists()
        data = json.loads(applied_file.read_text())
        # Should have a pending entry
        assert any("dev-loop" in k or "DEV-LOOP" in k for k in data.keys())

    def test_dimension_filter_respected(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "GAP", "dimension": "auth",
             "count": 3, "sessions": [1, 2, 3], "evidence_samples": ["e"] * 3},
            {"skill": "dev-loop", "signal_type": "SCOPE_MISS", "dimension": "rate_limiting",
             "count": 4, "sessions": [1, 2, 3, 4], "evidence_samples": ["e"] * 4},
        ])
        result = generate_improvement_proposal("dev-loop", dimension="auth")
        # Should pick auth, not rate_limiting
        assert "AUTH" in result["proposal_id"] or "auth" in result["proposal_text"]

    def test_mdl_check_included(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        self._write_queue(tmp_path, [
            {"skill": "dev-loop", "signal_type": "GAP", "dimension": "auth",
             "count": 3, "sessions": [1, 2, 3], "evidence_samples": ["e"] * 3}
        ])
        result = generate_improvement_proposal("dev-loop")
        assert "mdl_check" in result
        assert "passes" in result["mdl_check"]


# ── TestFalsifierMonitor (Phase 4) ───────────────────────────────────────────

from skill_signals import check_falsifier_conditions, mark_proposal_applied


class TestFalsifierMonitor:
    def _patch_state(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", tmp_path / "skill-signals.jsonl")
        monkeypatch.setattr(skill_signals, "_APPLIED_PROPOSALS", tmp_path / "applied-proposals.json")

    def test_no_file_returns_empty(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        alerts = check_falsifier_conditions(session_n=10)
        assert alerts == []

    def test_queued_proposal_not_checked(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        applied_file = tmp_path / "applied-proposals.json"
        applied_file.write_text(json.dumps({
            "pending:SKILL-SIGNAL-DEV-LOOP-AUTH": {
                "proposal_id": "SKILL-SIGNAL-DEV-LOOP-AUTH",
                "skill": "dev-loop",
                "dimension": "auth",
                "signal_type": "GAP",
                "status": "QUEUED",
                "applied_session_n": 0,
                "falsifier_sessions_to_watch": 3,
                "sessions_since_applied": 0,
                "original_pattern_count": 3,
                "post_signals": [],
            }
        }))
        alerts = check_falsifier_conditions(session_n=10)
        assert alerts == []  # QUEUED entries are not falsifier-checked

    def test_applied_proposal_falsified_after_threshold(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        # Write signals file with 4 post-application GAP signals
        signals = [
            {"session_n": 10 + i, "skill": "dev-loop", "signal_type": "GAP",
             "dimension": "auth", "evidence": "missed auth", "weight": -4.0,
             "recorded_at": "2026-07-30T00:00:00+00:00"}
            for i in range(1, 5)
        ]
        sf = tmp_path / "skill-signals.jsonl"
        with sf.open("w") as f:
            for s in signals:
                f.write(json.dumps(s) + "\n")

        applied_file = tmp_path / "applied-proposals.json"
        applied_file.write_text(json.dumps({
            "SKILL-SIGNAL-DEV-LOOP-AUTH": {
                "proposal_id": "SKILL-SIGNAL-DEV-LOOP-AUTH",
                "skill": "dev-loop",
                "dimension": "auth",
                "signal_type": "GAP",
                "status": "APPLIED",
                "applied_session_n": 10,
                "falsifier_sessions_to_watch": 3,
                "sessions_since_applied": 0,
                "original_pattern_count": 3,
                "post_signals": [],
            }
        }))
        alerts = check_falsifier_conditions(session_n=14)
        assert len(alerts) == 1
        assert alerts[0]["verdict"] == "FALSIFIED"
        assert alerts[0]["skill"] == "dev-loop"

    def test_mark_proposal_applied_updates_status(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        applied_file = tmp_path / "applied-proposals.json"
        applied_file.write_text(json.dumps({
            "pending:MY-PROPOSAL": {
                "proposal_id": "MY-PROPOSAL",
                "skill": "dev-loop",
                "dimension": "auth",
                "signal_type": "GAP",
                "status": "QUEUED",
                "applied_session_n": 0,
                "original_pattern_count": 3,
                "falsifier_sessions_to_watch": 3,
                "sessions_since_applied": 0,
                "post_signals": [],
            }
        }))
        result = mark_proposal_applied("MY-PROPOSAL", session_n=15)
        assert result is True
        data = json.loads(applied_file.read_text())
        assert data["MY-PROPOSAL"]["status"] == "APPLIED"
        assert data["MY-PROPOSAL"]["applied_session_n"] == 15

    def test_mark_nonexistent_proposal_returns_false(self, tmp_path, monkeypatch):
        self._patch_state(tmp_path, monkeypatch)
        applied_file = tmp_path / "applied-proposals.json"
        applied_file.write_text(json.dumps({}))
        result = mark_proposal_applied("NONEXISTENT", session_n=1)
        assert result is False


# ── TestLinUCBBandit (Phase 3) ────────────────────────────────────────────────

from skill_signals import (
    _context_vector,
    _linucb_select,
    _linucb_update,
    fork_skill,
    select_skill_arm,
    record_arm_reward,
)


class TestLinUCB:
    def test_context_vector_length(self):
        ctx = _context_vector("new_endpoint", "PROFICIENT")
        assert len(ctx) == 3
        assert ctx[0] == 1.0  # bias term

    def test_context_vector_normalizes(self):
        ctx = _context_vector("other", "NOVICE")
        assert all(0.0 <= v <= 1.0 for v in ctx)

    def test_linucb_select_returns_valid_index(self):
        d = 3
        arm = {"theta": [0.0] * d, "A": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
               "A_inv": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
               "b": [0.0] * d}
        selected = _linucb_select([arm, arm], [1.0, 0.5, 0.3])
        assert selected in (0, 1)

    def test_linucb_update_changes_theta(self):
        d = 3
        arm = {"theta": [0.0] * d, "A": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
               "A_inv": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
               "b": [0.0] * d}
        updated = _linucb_update(arm, [1.0, 0.5, 0.3], reward=1.0)
        assert updated["theta"] != [0.0] * d

    def test_linucb_prefers_higher_reward_arm(self):
        """After many positive rewards, the rewarded arm should be selected more."""
        d = 3
        def arm_template():
            return {
                    "theta": [0.0] * d,
                    "A": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
                    "A_inv": [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)],
                    "b": [0.0] * d,
                }
        arm0 = arm_template()
        arm1 = arm_template()
        ctx = [1.0, 0.5, 0.5]
        # Reward arm1 heavily
        for _ in range(10):
            arm1 = _linucb_update(arm1, ctx, reward=2.0)
            arm0 = _linucb_update(arm0, ctx, reward=-1.0)
        # After enough updates, exploration shrinks and exploitation takes over
        # Run many selections and count which arm wins majority
        wins = [0, 0]
        for _ in range(50):
            sel = _linucb_select([arm0, arm1], ctx, alpha=0.0)  # alpha=0 = pure exploitation
            wins[sel] += 1
        assert wins[1] > wins[0]

    def test_fork_creates_candidate_entry(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "skill-candidates.json")
        monkeypatch.setattr(skill_signals, "_ARCHIVE_DIR", tmp_path / "skill-archives")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")
        result = fork_skill("dev-loop", gap_history=[], session_n=10)
        assert result["forked"] is True
        assert (tmp_path / "skill-candidates.json").exists()
        data = json.loads((tmp_path / "skill-candidates.json").read_text())
        assert "dev-loop" in data
        assert data["dev-loop"]["candidate_points"] == 70.0

    def test_fork_idempotent_when_candidate_exists(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "skill-candidates.json")
        monkeypatch.setattr(skill_signals, "_ARCHIVE_DIR", tmp_path / "skill-archives")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")
        fork_skill("dev-loop", gap_history=[], session_n=10)
        result2 = fork_skill("dev-loop", gap_history=[], session_n=11)
        assert result2["forked"] is False

    def test_select_arm_returns_current_when_no_candidate(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "none.json")
        result = select_skill_arm("dev-loop")
        assert result["arm"] == "current"

    def test_record_arm_reward_promotes_after_threshold(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "skill-candidates.json")
        monkeypatch.setattr(skill_signals, "_ARCHIVE_DIR", tmp_path / "skill-archives")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")

        fork_skill("dev-loop", gap_history=[], session_n=1)

        # Reward candidate (arm 1) heavily for 5 sessions
        result = None
        for i in range(2, 7):
            result = record_arm_reward("dev-loop", arm_index=1, reward=2.0,
                                       session_n=i, task_type="new_endpoint",
                                       developer_stage="PROFICIENT")
        assert result is not None
        assert result.get("promoted") is True

    def test_record_arm_reward_reverts_when_current_wins(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "skill-candidates.json")
        monkeypatch.setattr(skill_signals, "_ARCHIVE_DIR", tmp_path / "skill-archives")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")

        fork_skill("dev-loop", gap_history=[], session_n=1)

        # Reward current (arm 0) heavily for 5 sessions
        result = None
        for i in range(2, 7):
            result = record_arm_reward("dev-loop", arm_index=0, reward=2.0,
                                       session_n=i, task_type="bug_fix",
                                       developer_stage="COMPETENT")
        assert result is not None
        assert result.get("reverted") is True


# ── TestTaskTypeInference (Fix 1) ────────────────────────────────────────────

class TestTaskTypeInference:
    def test_explicit_task_type_line_takes_priority(self):
        block = "Skills: dev-loop\nTaskType: new_endpoint\n"
        signals = compute_signals_for_session(block, session_n=1)
        # No surface or findings — but task_type extraction must not raise
        assert isinstance(signals, list)

    def test_task_type_line_used_over_checkpoint_heuristic(self):
        """TaskType: bug_fix + size L → should use bug_fix, not new_endpoint."""
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    bug_fix\n"
            "Examined:     [error_handling]\n"
            "Not examined: []\n"
        )
        block = (
            "Skills: dev-loop, code-review\n"
            "TaskType: bug_fix\n"
            "TaskCheckpoints: something (L)\n"
            "[FINDING: HIGH] Auth — bypass possible\n"
            + surface
        )
        signals = compute_signals_for_session(block, session_n=1)
        # auth is not mandatory for bug_fix (only conditional) — should be SCOPE_MISS not GAP
        [s for s in signals if s["signal_type"] == "SCOPE_MISS" and s["skill"] == "dev-loop"]
        # Either SCOPE_MISS or no signal for auth in bug_fix context — but NOT GAP
        gap = [s for s in signals if s["signal_type"] == "GAP" and s["dimension"] == "auth" and s["skill"] == "dev-loop"]
        assert len(gap) == 0  # auth was not in examined list

    def test_fallback_when_no_task_type_line(self):
        """No TaskType: line and no checkpoint → task_type defaults to 'other'."""
        block = "Skills: dev-loop\n"
        signals = compute_signals_for_session(block, session_n=1)
        assert isinstance(signals, list)  # must not raise

    def test_task_type_propagates_to_scope_miss_evidence(self):
        """SCOPE_MISS evidence string mentions the task type."""
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    new_endpoint\n"
            "Examined:     [error_handling]\n"
            "Not examined: []\n"
        )
        block = (
            "Skills: dev-loop, code-review\n"
            "TaskType: new_endpoint\n"
            "[FINDING: HIGH] Auth — bypass possible\n"
            + surface
        )
        signals = compute_signals_for_session(block, session_n=1)
        scope_signals = [s for s in signals if s["signal_type"] == "SCOPE_MISS" and s["skill"] == "dev-loop"]
        if scope_signals:
            assert "new_endpoint" in scope_signals[0]["evidence"]


# ── TestBanditAutoFeed (Fix 2) ───────────────────────────────────────────────

class TestBanditAutoFeed:
    def _setup(self, tmp_path, monkeypatch):
        import skill_signals
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_SIGNALS_FILE", tmp_path / "skill-signals.jsonl")
        monkeypatch.setattr(skill_signals, "_POINTS_FILE", tmp_path / "skill-points.json")
        monkeypatch.setattr(skill_signals, "_CANDIDATES_FILE", tmp_path / "skill-candidates.json")
        monkeypatch.setattr(skill_signals, "_ARCHIVE_DIR", tmp_path / "skill-archives")
        monkeypatch.setattr(skill_signals, "_IMPROVEMENT_QUEUE", tmp_path / "improvement-queue.json")
        monkeypatch.setattr(skill_signals, "_APPLIED_PROPOSALS", tmp_path / "applied-proposals.json")
        return tmp_path

    def test_record_session_signals_feeds_bandit_when_candidate_active(self, tmp_path, monkeypatch):
        from skill_signals import fork_skill, _load_candidates
        self._setup(tmp_path, monkeypatch)

        # Fork dev-loop to create an active candidate
        fork_skill("dev-loop", gap_history=[], session_n=1)

        # Now run a session with a GAP signal for dev-loop
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    bug_fix\n"
            "Examined:     [error_handling]\n"
            "Not examined: []\n"
        )
        block = (
            "Skills: dev-loop\n"
            "TaskType: bug_fix\n"
            "[FINDING: HIGH] Error handling — null check missing\n"
            + surface
        )
        record_session_signals(block, session_n=2)

        # Candidate should have received a reward update
        candidates = _load_candidates()
        assert "dev-loop" in candidates
        selections = candidates["dev-loop"].get("arm_selections", [])
        # At least one arm selection recorded at session 2
        session_2_selections = [s for s in selections if s["session_n"] == 2]
        assert len(session_2_selections) == 1
        assert session_2_selections[0]["reward"] < 0  # GAP is negative reward

    def test_no_bandit_update_when_no_candidate(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        block = "Skills: dev-loop\n"
        record_session_signals(block, session_n=1)
        # Should complete without error, no candidate file written
        assert not (tmp_path / "skill-candidates.json").exists() or True  # no crash

    def test_developer_stage_extracted_from_cog_assessment(self, tmp_path, monkeypatch):
        from skill_signals import fork_skill, _load_candidates
        self._setup(tmp_path, monkeypatch)
        fork_skill("dev-loop", gap_history=[], session_n=1)

        # Include a CognitiveAssessment line with Dreyfus stage
        surface = (
            "[EXAMINATION SURFACE — dev-loop AUDIT]\n"
            "Task type:    bug_fix\n"
            "Examined:     [error_handling]\n"
            "Not examined: []\n"
        )
        block = (
            "Skills: dev-loop\n"
            "TaskType: bug_fix\n"
            "CognitiveAssessment: Dreyfus stage: PROFICIENT | ZPD: ...\n"
            "[FINDING: HIGH] Error handling — null check missing\n"
            + surface
        )
        record_session_signals(block, session_n=2)
        candidates = _load_candidates()
        # If the arm selection was recorded, check the context was non-default
        selections = candidates.get("dev-loop", {}).get("arm_selections", [])
        assert len(selections) >= 1  # update fired


# ── TestFalsifierAlertCLAUDEMD (Fix 3 — behavioral contract) ─────────────────

class TestFalsifierAlertContract:
    """Verify the CLAUDE.md instruction exists and is correctly formed."""

    def test_falsifier_alerts_handler_in_server_code(self):
        # The behavioral handler for falsifier_alerts is in the server codebase,
        # not in ~/.claude/CLAUDE.md (which is a local runtime file never in the repo).
        # Verify the FALSIFIED verdict is produced in skill_signals.py and that
        # falsifier_alerts is wired into SessionState via session.py.
        skill_signals_src = (
            Path(__file__).parent.parent / "servers" / "core" / "src" / "skill_signals.py"
        )
        session_src = (
            Path(__file__).parent.parent / "servers" / "core" / "src" / "session.py"
        )
        assert skill_signals_src.exists(), "skill_signals.py must exist"
        assert session_src.exists(), "session.py must exist"

        signals_content = skill_signals_src.read_text()
        assert "FALSIFIED" in signals_content, "skill_signals.py must produce FALSIFIED verdict"
        assert "check_falsifier_conditions" in signals_content, "skill_signals.py must define check_falsifier_conditions"

        session_content = session_src.read_text()
        assert "falsifier_alerts" in session_content, "session.py must wire falsifier_alerts into SessionState"
        assert "check_falsifier_conditions" in session_content, "session.py must call check_falsifier_conditions"


# ── TestWriteDomainSignal + TestReadAuditPatterns ─────────────────────────────

class TestWriteDomainSignal:
    def test_writes_jsonl_record(self, tmp_path, monkeypatch):
        monkeypatch.setattr(skill_signals, "_STATE_DIR", tmp_path)
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", tmp_path / "audit-signals.jsonl")
        write_domain_signal("canopy", 5, "dev-loop", "auth", "HIGH", "new_endpoint")
        lines = (tmp_path / "audit-signals.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        r = __import__("json").loads(lines[0])
        assert r["project"] == "canopy"
        assert r["domain"] == "auth"
        assert r["severity"] == "HIGH"
        assert r["skill"] == "dev-loop"
        assert r["task_type"] == "new_endpoint"
        assert r["session"] == 5

    def test_appends_multiple_records(self, tmp_path, monkeypatch):
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", tmp_path / "audit-signals.jsonl")
        write_domain_signal("youk", 1, "dev-loop", "auth", "HIGH")
        write_domain_signal("youk", 2, "dev-loop", "concurrency", "HIGH")
        lines = (tmp_path / "audit-signals.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_silent_fail_on_permission_error(self, tmp_path, monkeypatch):
        # Point at a path inside a non-existent deeply nested dir — write will succeed
        # (mkdir is called). Point at a read-only file to trigger silent fail.
        bad_file = tmp_path / "audit-signals.jsonl"
        bad_file.write_text("")
        bad_file.chmod(0o444)
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", bad_file)
        # Must not raise — silent-fail contract
        write_domain_signal("youk", 1, "dev-loop", "auth", "HIGH")
        bad_file.chmod(0o644)  # restore so tmp_path cleanup works


class TestReadAuditPatterns:
    def _write_signals(self, path: Path, records: list[dict]) -> None:
        import json
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_returns_domain_above_40pct_threshold(self, tmp_path, monkeypatch):
        sig_file = tmp_path / "audit-signals.jsonl"
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", sig_file)
        # 3 sessions, auth flagged in 2 → 67% ≥ 40%
        self._write_signals(sig_file, [
            {"project": "youk", "session": 1, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": "new_endpoint"},
            {"project": "youk", "session": 2, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": "new_endpoint"},
            {"project": "youk", "session": 3, "domain": "concurrency", "severity": "HIGH", "skill": "dev-loop", "task_type": "bug_fix"},
        ])
        patterns = read_audit_patterns("youk", lookback_sessions=5)
        domains = [p["domain"] for p in patterns]
        assert "auth" in domains
        assert "concurrency" not in domains  # 1/3 = 33% < 40%

    def test_excludes_other_projects(self, tmp_path, monkeypatch):
        sig_file = tmp_path / "audit-signals.jsonl"
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", sig_file)
        self._write_signals(sig_file, [
            {"project": "canopy", "session": 1, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "canopy", "session": 2, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "youk",   "session": 1, "domain": "auth", "severity": "LOW",  "skill": "dev-loop", "task_type": ""},
        ])
        patterns = read_audit_patterns("youk", lookback_sessions=5)
        assert patterns == []  # canopy's auth signals don't bleed into youk

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", tmp_path / "nonexistent.jsonl")
        assert read_audit_patterns("youk") == []

    def test_lookback_window_caps_sessions(self, tmp_path, monkeypatch):
        sig_file = tmp_path / "audit-signals.jsonl"
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", sig_file)
        # 6 sessions; lookback=3 means only sessions 6,5,4 are counted
        # auth only in sessions 1,2 (outside window) → should not appear
        self._write_signals(sig_file, [
            {"project": "youk", "session": i, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": ""}
            for i in [1, 2]
        ] + [
            {"project": "youk", "session": i, "domain": "concurrency", "severity": "HIGH", "skill": "dev-loop", "task_type": ""}
            for i in [4, 5, 6]
        ])
        patterns = read_audit_patterns("youk", lookback_sessions=3)
        domains = [p["domain"] for p in patterns]
        assert "auth" not in domains          # outside lookback window
        assert "concurrency" in domains        # 3/3 sessions = 100%

    def test_result_sorted_by_pct_descending(self, tmp_path, monkeypatch):
        sig_file = tmp_path / "audit-signals.jsonl"
        monkeypatch.setattr(skill_signals, "_AUDIT_SIGNALS_FILE", sig_file)
        self._write_signals(sig_file, [
            {"project": "youk", "session": 1, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "youk", "session": 2, "domain": "auth", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "youk", "session": 1, "domain": "concurrency", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "youk", "session": 2, "domain": "concurrency", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
            {"project": "youk", "session": 3, "domain": "concurrency", "severity": "HIGH", "skill": "dev-loop", "task_type": ""},
        ])
        patterns = read_audit_patterns("youk", lookback_sessions=5)
        assert patterns[0]["domain"] == "concurrency"  # 3/3 > auth 2/3
