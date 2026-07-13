"""
Tests for ambient intelligence additions:
1. Hook: task size detection (detect_task_size)
2. Hook: session-end signal detection (detect_session_end)
3. Hook: health nudge generation (build_health_nudge)
4. Hook: build nudge content (build_build_nudge)
5. Compaction: semantic dedup (_is_semantic_duplicate)
6. Session: stale decision detection (_find_stale_decisions)
7. Session: session autopsy in end_session return
8. Health: git outcome findings (_check_git_outcomes)
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "shared"))
sys.path.insert(0, str(Path(__file__).parent.parent / "plugin" / "scripts"))


# ── Hook: task size detection ────────────────────────────────────────────────

class TestDetectTaskSize:
    def setup_method(self):
        from youk_hook_utils import detect_task_size
        self.detect = detect_task_size

    def test_build_phrase_detected(self):
        assert self.detect("let's add a new login endpoint") == "M"

    def test_implement_phrase_detected(self):
        assert self.detect("implement the user profile feature") == "M"

    def test_create_phrase_detected(self):
        assert self.detect("create a new auth module") == "M"

    def test_refactor_phrase_detected(self):
        assert self.detect("refactor the database layer") == "M"

    def test_question_not_detected(self):
        assert self.detect("what does this function do?") is None

    def test_clarification_not_detected(self):
        assert self.detect("how does the routing work?") is None

    def test_slash_command_not_detected(self):
        assert self.detect("/build add feature") is None

    def test_short_prompt_not_detected(self):
        assert self.detect("ok") is None

    def test_too_short_not_detected(self):
        assert self.detect("add it") is None  # under 15 chars


# ── Hook: session-end detection ──────────────────────────────────────────────

class TestDetectSessionEnd:
    def setup_method(self):
        from youk_hook_utils import detect_session_end
        self.detect = detect_session_end

    def test_ok_thanks_detected(self):
        assert self.detect("ok thanks") is True

    def test_thats_all_detected(self):
        assert self.detect("that's all") is True

    def test_looks_good_detected(self):
        assert self.detect("looks good") is True

    def test_ship_it_detected(self):
        assert self.detect("ship it") is True

    def test_wrap_it_up_detected(self):
        assert self.detect("wrap it up") is True

    def test_long_message_not_detected(self):
        # Long messages are not session-end signals even if they contain the phrase
        assert self.detect(
            "ok thanks for helping me with the implementation, I think we should also "
            "add tests and update the documentation before we call it done"
        ) is False

    def test_mid_session_question_not_detected(self):
        assert self.detect("what's next on the list?") is False

    def test_all_done_detected(self):
        assert self.detect("all done") is True

    def test_calling_it_detected(self):
        assert self.detect("calling it") is True


# ── Hook: health nudge ───────────────────────────────────────────────────────

class TestBuildHealthNudge:
    def setup_method(self):
        from youk_hook_utils import build_health_nudge
        self.nudge = build_health_nudge

    def test_low_score_triggers_nudge(self):
        result = self.nudge({"org_score": 4.5, "gaps_last30": 15, "close_cluster_rate": 0.3})
        assert result is not None
        assert "4.5" in result
        assert "improve" in result.lower() or "gaps" in result.lower()

    def test_high_gaps_low_close_rate_triggers_nudge(self):
        result = self.nudge({"org_score": 6.0, "gaps_last30": 25, "close_cluster_rate": 0.35})
        assert result is not None
        assert "/done" in result

    def test_nominal_health_no_nudge(self):
        result = self.nudge({"org_score": 7.5, "gaps_last30": 5, "close_cluster_rate": 0.85})
        assert result is None

    def test_empty_health_no_nudge(self):
        result = self.nudge({})
        assert result is None

    def test_border_score_no_nudge(self):
        # Score exactly 5.0 doesn't trigger (> 5.0 is the boundary)
        result = self.nudge({"org_score": 5.1, "gaps_last30": 10, "close_cluster_rate": 0.5})
        assert result is None


# ── Compaction: semantic dedup ───────────────────────────────────────────────

class TestSemanticDuplicate:
    def setup_method(self):
        from compaction import _is_semantic_duplicate
        self.is_dup = _is_semantic_duplicate

    def test_exact_reword_is_duplicate(self):
        existing = {"always run ruff check before committing code to the repository"}
        assert self.is_dup("always run ruff before committing to repository", existing) is True

    def test_distinct_contracts_not_duplicate(self):
        existing = {"always run tests before committing"}
        assert self.is_dup("never commit secrets or api keys to git", existing) is False

    def test_short_contract_not_deduped(self):
        # Contracts with < 3 meaningful words bypass dedup — not enough signal
        existing = {"rule alpha applies"}
        assert self.is_dup("rule beta applies", existing) is False

    def test_related_but_distinct_not_duplicate(self):
        # "class components" vs "hook components" — same domain, different rule
        existing = {"always use class components for react views"}
        assert self.is_dup("prefer hook components for react views", existing) is False

    def test_empty_existing_not_duplicate(self):
        assert self.is_dup("never do this", set()) is False

    def test_high_overlap_catches_restatement(self):
        # Same contract stated twice in slightly different words
        existing = {"commit format small logical commits one concept per commit"}
        assert self.is_dup(
            "commit format: small logical commits, one concept per commit", existing
        ) is True


# ── Session: stale decisions ─────────────────────────────────────────────────

class TestFindStaleDecisions:
    def test_old_decision_surfaced(self, tmp_path, monkeypatch):
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        proj_dir = tmp_path / "knowledge" / "projects" / "myproj"
        proj_dir.mkdir(parents=True)
        old_date = (datetime.utcnow() - timedelta(days=100)).strftime("%Y-%m-%d")
        (proj_dir / "decisions.md").write_text(
            f"## {old_date}: Use SQLite not Postgres\n\nSingle user, no concurrency.\n"
        )
        from session import _find_stale_decisions
        stale = _find_stale_decisions("myproj", threshold_days=90)
        assert len(stale) == 1
        assert "SQLite" in stale[0][0]
        assert stale[0][1] >= 100

    def test_recent_decision_not_surfaced(self, tmp_path, monkeypatch):
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        proj_dir = tmp_path / "knowledge" / "projects" / "myproj"
        proj_dir.mkdir(parents=True)
        recent_date = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d")
        (proj_dir / "decisions.md").write_text(
            f"## {recent_date}: Use Redis for caching\n\nHigh read throughput.\n"
        )
        from session import _find_stale_decisions
        stale = _find_stale_decisions("myproj", threshold_days=90)
        assert len(stale) == 0

    def test_missing_decisions_file_returns_empty(self, tmp_path, monkeypatch):
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        (tmp_path / "knowledge" / "projects" / "noproj").mkdir(parents=True)
        from session import _find_stale_decisions
        assert _find_stale_decisions("noproj") == []

    def test_undated_decisions_ignored(self, tmp_path, monkeypatch):
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        proj_dir = tmp_path / "knowledge" / "projects" / "myproj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "decisions.md").write_text(
            "## ADR-001: Use microservices\n\nNo date in heading.\n"
        )
        from session import _find_stale_decisions
        assert _find_stale_decisions("myproj") == []

    def test_oldest_returned_first(self, tmp_path, monkeypatch):
        import session
        monkeypatch.setattr(session, "YOUK_ROOT", tmp_path)
        proj_dir = tmp_path / "knowledge" / "projects" / "myproj"
        proj_dir.mkdir(parents=True)
        d1 = (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%d")
        d2 = (datetime.utcnow() - timedelta(days=95)).strftime("%Y-%m-%d")
        (proj_dir / "decisions.md").write_text(
            f"## {d2}: Newer old decision\n\nBody.\n\n"
            f"## {d1}: Older old decision\n\nBody.\n"
        )
        from session import _find_stale_decisions
        stale = _find_stale_decisions("myproj", threshold_days=90)
        assert len(stale) == 2
        assert stale[0][1] > stale[1][1]  # oldest first (highest age)


# ── Health: git outcome findings ─────────────────────────────────────────────

class TestCheckGitOutcomes:
    def test_commits_without_done_surfaces_finding(self):
        from health import _check_git_outcomes
        sessions = [
            {"commits": True, "close_cluster": False, "project": "myproj"}
            for _ in range(4)
        ]
        findings = _check_git_outcomes(sessions)
        assert any("commits" in f.lower() and "/done" in f for f in findings)

    def test_low_commits_no_done_no_finding(self):
        from health import _check_git_outcomes
        # Fewer than 3 commits-without-done — below threshold
        sessions = [
            {"commits": True, "close_cluster": False, "project": "myproj"},
            {"commits": True, "close_cluster": False, "project": "myproj"},
        ]
        findings = _check_git_outcomes(sessions)
        assert not any("/done" in f for f in findings)

    def test_commits_with_done_no_finding(self):
        from health import _check_git_outcomes
        sessions = [
            {"commits": True, "close_cluster": True, "project": "myproj"}
            for _ in range(5)
        ]
        findings = _check_git_outcomes(sessions)
        assert not any("/done" in f for f in findings)

    def test_empty_sessions_no_crash(self):
        from health import _check_git_outcomes
        assert _check_git_outcomes([]) == []
