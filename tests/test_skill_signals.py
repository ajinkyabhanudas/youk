"""Tests for skill self-improvement signal detector (skill_signals.py).

All tests use tmp_path-scoped state directories so they are fully isolated.
The module is imported directly — no MCP dependency.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_signals import (
    _parse_examination_surfaces,
    _extract_downstream_findings,
    compute_signals_for_session,
    detect_patterns,
    update_points,
    get_fork_candidates,
    get_skill_health_summary,
    record_session_signals,
    POINT_WEIGHTS,
    _STARTING_POINTS,
    _FORK_THRESHOLD,
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
        lines.append(f"Retrospectives: 1 (VALIDATED=1)")
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
        pf = self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": 1, "skill": "dev-loop", "signal_type": "GAP",
                    "dimension": "auth", "weight": POINT_WEIGHTS["GAP"], "recorded_at": ""}]
        touched = update_points(signals)
        assert touched["dev-loop"] == _STARTING_POINTS + POINT_WEIGHTS["GAP"]

    def test_stable_recovers_points(self, tmp_path, monkeypatch):
        pf = self._with_state_dir(tmp_path, monkeypatch)
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
        pf = self._with_state_dir(tmp_path, monkeypatch)
        # Many deductions
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "SCOPE_MISS",
                    "dimension": "auth", "weight": POINT_WEIGHTS["SCOPE_MISS"], "recorded_at": ""}
                   for i in range(1, 30)]  # 29 × -6 = -174 → floored at 0
        touched = update_points(signals)
        assert touched["dev-loop"] == 0.0

    def test_points_capped_at_starting(self, tmp_path, monkeypatch):
        pf = self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "STABLE",
                    "dimension": "overall", "weight": POINT_WEIGHTS["STABLE"], "recorded_at": ""}
                   for i in range(1, 20)]  # many recoveries → cap at 100
        touched = update_points(signals)
        assert touched["dev-loop"] == _STARTING_POINTS

    def test_fork_candidate_below_threshold(self, tmp_path, monkeypatch):
        pf = self._with_state_dir(tmp_path, monkeypatch)
        signals = [{"session_n": i, "skill": "dev-loop", "signal_type": "SCOPE_MISS",
                    "dimension": "auth", "weight": POINT_WEIGHTS["SCOPE_MISS"], "recorded_at": ""}
                   for i in range(1, 12)]  # 11 × -6 = -66 → 34 points → below 40
        update_points(signals)
        candidates = get_fork_candidates(points_file=tmp_path / "skill-points.json")
        assert any(c["skill"] == "dev-loop" for c in candidates)

    def test_healthy_skill_not_in_fork_candidates(self, tmp_path, monkeypatch):
        pf = self._with_state_dir(tmp_path, monkeypatch)
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
        lines = [json.loads(l) for l in signals_file.read_text().splitlines() if l.strip()]
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
    _IMPROVEMENT_QUEUE,
    _APPLIED_PROPOSALS,
    _SKILL_ROOT,
    _load_signal_evidence,
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
        result = generate_improvement_proposal("dev-loop")
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
    _CANDIDATES_FILE,
    _FORK_THRESHOLD,
    _STARTING_POINTS,
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
        arm_template = lambda: {
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
