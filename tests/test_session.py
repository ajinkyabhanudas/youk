"""Tests for session.py — pending count, project type detection, task_checkpoint."""
from __future__ import annotations
from pathlib import Path
import pytest


# ── Pending proposals count ──────────────────────────────────────────────────

class TestCountPendingProposals:
    def test_excludes_applied(self, youk_root):
        """APPLIED entries must not count toward pending_proposals_count."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "# Proposals\n\n"
            "## PENDING-001 — 2026-07-01\n"
            "**Target:** foo\n**Status:** APPLIED — 2026-07-02\n\n"
            "## PENDING-002 — 2026-07-01\n"
            "**Target:** bar\n**Status:** PENDING\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 1

    def test_all_applied_returns_zero(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "## PENDING-001 — 2026-07-01\n**Status:** APPLIED — 2026-07-02\n"
            "## PENDING-002 — 2026-07-01\n**Status:** APPLIED — 2026-07-02\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 0

    def test_no_file_returns_zero(self, youk_root):
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 0

    def test_multiple_pending(self, youk_root):
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "## PENDING-001 — 2026-07-01\n**Status:** PENDING\n"
            "## PENDING-002 — 2026-07-01\n**Status:** APPLIED — 2026-07-02\n"
            "## PENDING-003 — 2026-07-01\n**Status:** PENDING\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 2


# ── Project type detection ───────────────────────────────────────────────────

class TestDetectProjectType:
    def test_python_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"

    def test_python_pyproject_toml(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"

    def test_python_nested_one_level(self, tmp_path):
        """requirements.txt inside servers/ detected as python."""
        (tmp_path / "servers").mkdir()
        (tmp_path / "servers" / "requirements.txt").write_text("mcp\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"

    def test_python_nested_two_levels(self, tmp_path):
        """requirements.txt inside servers/code/ detected as python (youk pattern)."""
        (tmp_path / "servers" / "code").mkdir(parents=True)
        (tmp_path / "servers" / "code" / "requirements.txt").write_text("mcp\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"

    def test_python_dockerfile(self, tmp_path):
        """Dockerfile FROM python: detected when no requirements.txt anywhere."""
        (tmp_path / "servers" / "core").mkdir(parents=True)
        (tmp_path / "servers" / "core" / "Dockerfile").write_text(
            "FROM python:3.13-slim\nWORKDIR /app\n"
        )
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"

    def test_dockerfile_non_python_not_detected(self, tmp_path):
        """Dockerfile with non-Python base image should not trigger python detection."""
        (tmp_path / "Dockerfile").write_text("FROM node:20-slim\nWORKDIR /app\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "unknown"

    def test_go_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module example.com/foo\ngo 1.21\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "go"

    def test_rust_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "foo"\n')
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "rust"

    def test_unknown_empty_dir(self, tmp_path):
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "unknown"

    def test_nonexistent_dir_returns_unknown(self, tmp_path):
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path / "nonexistent")) == "unknown"


# ── Session plan generation ──────────────────────────────────────────────────

class TestGenerateSessionPlan:
    def _plan(self, **kwargs):
        from session import _generate_session_plan
        defaults = dict(
            slug="test",
            resume_point="Fix the login bug",
            contracts=[],
            pending_proposals=0,
            close_cluster_missed=False,
            project_type="python",
            session_counter=10,
        )
        defaults.update(kwargs)
        return _generate_session_plan(**defaults)

    def test_stale_resume_point_tagged_when_old_and_many_commits(self):
        plan = self._plan(days_since_last=20, new_commits=15)
        assert any("20d stale" in item and "15 commits since" in item for item in plan)

    def test_resume_point_not_tagged_when_recent(self):
        plan = self._plan(days_since_last=3, new_commits=5)
        assert not any("stale" in item.lower() for item in plan)

    def test_resume_point_not_tagged_when_few_commits(self):
        plan = self._plan(days_since_last=20, new_commits=5)
        assert not any("stale" in item.lower() for item in plan)

    def test_close_cluster_missed_plain_english_for_early_session(self):
        plan = self._plan(close_cluster_missed=True, session_counter=2)
        assert any("Type /done" in item for item in plan)
        assert not any("org score" in item.lower() for item in plan)

    def test_close_cluster_missed_mentions_org_score_for_veteran(self):
        plan = self._plan(close_cluster_missed=True, session_counter=15)
        assert any("org score" in item.lower() for item in plan)

    def test_pending_proposals_plain_english_for_early_session(self):
        plan = self._plan(pending_proposals=3, session_counter=2)
        assert any("/health" in item for item in plan)
        assert not any("self-heal" in item.lower() for item in plan)

    def test_pending_proposals_technical_for_veteran(self):
        plan = self._plan(pending_proposals=3, session_counter=10)
        assert any("self-heal" in item.lower() or "get_proposals" in item for item in plan)


# ── Mid-session adaptations audit line ───────────────────────────────────────

class TestMidSessionAdaptations:
    @pytest.fixture(autouse=True)
    def patch_claude_root(self, tmp_path, monkeypatch):
        import session
        claude_root = tmp_path / "claude"
        (claude_root / "audit").mkdir(parents=True)
        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)
        self._audit_dir = claude_root / "audit"

    def _write_state(self, youk_root, slug="testslug"):
        (youk_root / "state" / "session.json").write_text(
            f'{{"session_counter": 5, "last_project": "{slug}", "last_seen": "2026-07-01"}}'
        )

    def test_adaptations_written_to_audit_when_nonzero(self, youk_root):
        """MidSessionAdaptations: N line appears in audit when adaptations were applied."""
        import session
        self._write_state(youk_root)
        session.end_session(
            summary="Test session",
            commits_made=False,
            close_cluster=False,
            mid_session_adaptations_applied=3,
        )
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        content = (self._audit_dir / f"{month}.md").read_text()
        assert "MidSessionAdaptations: 3" in content

    def test_adaptations_line_absent_when_zero(self, youk_root):
        """MidSessionAdaptations line is omitted entirely when count is 0."""
        import session
        self._write_state(youk_root, slug="testslug2")
        session.end_session(
            summary="Test session no adaptations",
            commits_made=False,
            close_cluster=False,
            mid_session_adaptations_applied=0,
        )
        from datetime import datetime
        month = datetime.utcnow().strftime("%Y-%m")
        content = (self._audit_dir / f"{month}.md").read_text()
        assert "MidSessionAdaptations: 0" not in content


# ── task_checkpoint ──────────────────────────────────────────────────────────

class TestTaskCheckpoint:
    """task_checkpoint: compact brief + proportional audit write."""

    def test_xs_does_not_write_checkpoint(self, youk_root, tmp_path):
        """XS tasks skip the .jsonl write — brief rebuild only."""
        import session
        result = session.task_checkpoint(str(tmp_path), "fix typo", size="XS")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        assert not cp_file.exists()
        assert result["checkpoint_written"] is False

    def test_s_does_not_write_checkpoint(self, youk_root, tmp_path):
        """S tasks also skip the .jsonl write."""
        import session
        result = session.task_checkpoint(str(tmp_path), "small fix", size="S")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        assert not cp_file.exists()
        assert result["checkpoint_written"] is False

    def test_m_writes_checkpoint(self, youk_root, tmp_path):
        """M tasks write one line to task-checkpoints.jsonl."""
        import json
        import session
        result = session.task_checkpoint(str(tmp_path), "add login endpoint", size="M")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        assert cp_file.exists()
        assert result["checkpoint_written"] is True
        entries = [json.loads(l) for l in cp_file.read_text().splitlines() if l.strip()]
        assert len(entries) == 1
        assert entries[0]["task"] == "add login endpoint"
        assert entries[0]["size"] == "M"

    def test_l_writes_checkpoint(self, youk_root, tmp_path):
        """L tasks also write to .jsonl."""
        import session
        session.task_checkpoint(str(tmp_path), "refactor auth module", size="L")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        assert cp_file.exists()

    def test_multiple_checkpoints_accumulate(self, youk_root, tmp_path):
        """Multiple task_checkpoint calls append lines; rollup reads all of them."""
        import json
        import session
        session.task_checkpoint(str(tmp_path), "task one", size="M")
        session.task_checkpoint(str(tmp_path), "task two", size="L")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        entries = [json.loads(l) for l in cp_file.read_text().splitlines() if l.strip()]
        assert len(entries) == 2
        assert entries[0]["task"] == "task one"
        assert entries[1]["task"] == "task two"

    def test_returns_brief_key(self, youk_root, tmp_path):
        """Result always contains a 'brief' key (may be empty if no context files)."""
        import session
        result = session.task_checkpoint(str(tmp_path), "any task", size="M")
        assert "brief" in result

    def test_label_truncated_to_200(self, youk_root, tmp_path):
        """Labels longer than 200 chars are truncated in the checkpoint entry."""
        import json
        import session
        long_label = "x" * 300
        session.task_checkpoint(str(tmp_path), long_label, size="M")
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        entry = json.loads(cp_file.read_text().splitlines()[0])
        assert len(entry["task"]) <= 200


class TestEndSessionCheckpointRollup:
    """end_session rolls up task-checkpoints.jsonl into the audit entry."""

    def setup_method(self, method):
        pass

    def test_rollup_appears_in_audit(self, youk_root, tmp_path, monkeypatch):
        """TaskCheckpoints line written to audit when .jsonl exists."""
        import json
        import session
        from datetime import datetime

        claude_root = tmp_path / "claude"
        (claude_root / "audit").mkdir(parents=True)
        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

        # Pre-write two checkpoint entries
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        cp_file.write_text(
            json.dumps({"timestamp": "2026-07-02T10:00:00", "task": "implement login", "size": "M"}) + "\n"
            + json.dumps({"timestamp": "2026-07-02T11:00:00", "task": "add tests", "size": "S"}) + "\n"
        )

        (youk_root / "state" / "session.json").write_text(
            '{"session_counter": 1, "last_project": "proj", "last_seen": "2026-07-01"}'
        )
        session.end_session(summary="session done", commits_made=False)

        month = datetime.utcnow().strftime("%Y-%m")
        audit_text = (claude_root / "audit" / f"{month}.md").read_text()
        assert "TaskCheckpoints: 2" in audit_text
        assert "implement login" in audit_text

    def test_checkpoint_file_deleted_after_rollup(self, youk_root, tmp_path, monkeypatch):
        """task-checkpoints.jsonl is cleared after session_end reads it."""
        import json
        import session

        claude_root = tmp_path / "claude"
        (claude_root / "audit").mkdir(parents=True)
        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        cp_file.write_text(
            json.dumps({"timestamp": "2026-07-02T10:00:00", "task": "do thing", "size": "M"}) + "\n"
        )
        (youk_root / "state" / "session.json").write_text(
            '{"session_counter": 1, "last_project": "proj2", "last_seen": "2026-07-01"}'
        )
        session.end_session(summary="done", commits_made=False)
        assert not cp_file.exists()

    def test_no_checkpoint_file_no_error(self, youk_root, tmp_path, monkeypatch):
        """end_session works normally when no task-checkpoints.jsonl exists."""
        import session

        claude_root = tmp_path / "claude"
        (claude_root / "audit").mkdir(parents=True)
        monkeypatch.setattr(session, "CLAUDE_ROOT", claude_root)

        (youk_root / "state" / "session.json").write_text(
            '{"session_counter": 1, "last_project": "proj3", "last_seen": "2026-07-01"}'
        )
        result = session.end_session(summary="no checkpoints session", commits_made=False)
        assert result["audit_written"] is True
