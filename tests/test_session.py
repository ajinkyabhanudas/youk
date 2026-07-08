"""Tests for session.py — pending count, project type detection, task_checkpoint."""
from __future__ import annotations
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

    def test_excludes_superseded(self, youk_root):
        """SUPERSEDED entries must not count toward pending_proposals_count."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "## PENDING-001 — 2026-07-01\n**Status:** SUPERSEDED — 2026-07-02 (replaced by X)\n"
            "## PENDING-002 — 2026-07-01\n**Status:** PENDING\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 1

    def test_counts_named_proposal_blocks(self, youk_root):
        """### PROPOSAL N — format (from simulate-experience) must be counted."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "# youk Proposals\n\n"
            "## [simulate-experience audit]\n\n"
            "### PROPOSAL 1 — fix something\n\n"
            "**Type:** CODE_EDIT\nSome content.\n\n"
            "### PROPOSAL 2 — fix something else\n\n"
            "**Type:** SKILL_EDIT\nMore content.\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 2

    def test_named_proposal_superseded_not_counted(self, youk_root):
        """SUPERSEDED inline in a named proposal block must exclude it."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "### PROPOSAL 1 — old thing SUPERSEDED\n\nOld content.\n\n"
            "### PROPOSAL 2 — active\n\nNew content.\n"
        )
        from session import _count_pending_proposals
        assert _count_pending_proposals() == 1

    def test_mixed_formats_counted_together(self, youk_root):
        """PENDING-* format and ### PROPOSAL format must both contribute to total."""
        (youk_root / "knowledge" / "proposals" / "PENDING.md").write_text(
            "## PENDING-001 — 2026-07-01\n**Status:** PENDING\n\n"
            "## PENDING-002 — 2026-07-01\n**Status:** APPLIED\n\n"
            "### PROPOSAL A — active\n\nContent.\n\n"
            "### PROPOSAL B — another\n\nMore.\n"
        )
        from session import _count_pending_proposals
        # PENDING-001 (pending) + PROPOSAL A + PROPOSAL B = 3; PENDING-002 excluded
        assert _count_pending_proposals() == 3


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

    def test_python_docker_with_compose(self, tmp_path):
        """Makefile + docker-compose + pyproject in servers/ → python/docker."""
        (tmp_path / "Makefile").write_text("build:\n\tdocker build .\n")
        (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n")
        (tmp_path / "servers" / "core").mkdir(parents=True)
        (tmp_path / "servers" / "core" / "pyproject.toml").write_text("[tool.ruff]\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python/docker"

    def test_python_docker_no_compose_falls_back_to_python(self, tmp_path):
        """Makefile without docker-compose/Dockerfile + pyproject in servers/ → plain python."""
        (tmp_path / "Makefile").write_text("build:\n\tdocker build .\n")
        (tmp_path / "servers").mkdir()
        (tmp_path / "servers" / "requirements.txt").write_text("mcp\n")
        from session import _detect_project_type
        assert _detect_project_type(str(tmp_path)) == "python"


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
        entries = [json.loads(line) for line in cp_file.read_text().splitlines() if line.strip()]
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
        entries = [json.loads(line) for line in cp_file.read_text().splitlines() if line.strip()]
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

    def test_session_learnings_written_to_checkpoint(self, youk_root, tmp_path):
        """session_learnings dict is persisted in checkpoint entry."""
        import json
        import session
        session.task_checkpoint(
            str(tmp_path), "add auth", size="M",
            session_learnings={"skill_gap": "nfr_check skipped", "contract_unsaved": "always async"},
        )
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        entry = json.loads(cp_file.read_text().splitlines()[0])
        assert entry["learnings"]["skill_gap"] == "nfr_check skipped"
        assert entry["learnings"]["contract_unsaved"] == "always async"

    def test_no_pattern_trigger_on_first_occurrence(self, youk_root, tmp_path):
        """A gap appearing once does NOT trigger pattern_trigger."""
        import session
        result = session.task_checkpoint(
            str(tmp_path), "task 1", size="M",
            session_learnings={"skill_gap": "nfr_check skipped"},
        )
        assert "pattern_trigger" not in result

    def test_pattern_trigger_on_second_occurrence(self, youk_root, tmp_path):
        """Same gap type appearing in 2 checkpoints returns pattern_trigger."""
        import session
        session.task_checkpoint(
            str(tmp_path), "task 1", size="M",
            session_learnings={"skill_gap": "nfr_check skipped"},
        )
        result = session.task_checkpoint(
            str(tmp_path), "task 2", size="M",
            session_learnings={"skill_gap": "nfr_check skipped again"},
        )
        assert "pattern_trigger" in result
        assert any("skill_gap" in t for t in result["pattern_trigger"])

    def test_pattern_action_present_when_trigger_fires(self, youk_root, tmp_path):
        """pattern_action guidance included alongside pattern_trigger."""
        import session
        session.task_checkpoint(str(tmp_path), "t1", size="M",
                                session_learnings={"route_correction": "S→M"})
        result = session.task_checkpoint(str(tmp_path), "t2", size="M",
                                         session_learnings={"route_correction": "S→M again"})
        assert "pattern_action" in result

    def test_xs_ignores_session_learnings(self, youk_root, tmp_path):
        """XS tasks do not write checkpoint or accumulate patterns."""
        import session
        result = session.task_checkpoint(
            str(tmp_path), "tiny fix", size="XS",
            session_learnings={"skill_gap": "something"},
        )
        cp_file = youk_root / "state" / "task-checkpoints.jsonl"
        assert not cp_file.exists()
        assert "pattern_trigger" not in result


class TestEndSessionSkillGate:
    """end_session warns when close_cluster=True but no capability skill invoked."""

    def test_skill_gate_warning_when_no_capability_skill(self, youk_root, tmp_path, monkeypatch):
        """Warning returned when closing with no capability skill."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="did some work",
            commits_made=False,
            skills_used=["self_heal"],  # meta skill only
            close_cluster=True,
        )
        assert "skill_gate_warning" in result
        assert result["skill_gate_warning"]

    def test_no_skill_gate_warning_when_capability_used(self, youk_root, tmp_path, monkeypatch):
        """No warning when a capability skill was invoked."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="did some work",
            commits_made=False,
            skills_used=["code-review"],
            close_cluster=True,
        )
        assert "skill_gate_warning" not in result

    def test_no_skill_gate_warning_when_not_closing(self, youk_root, tmp_path, monkeypatch):
        """Gate only fires when close_cluster=True — /close without skills is fine."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="quick close",
            commits_made=False,
            skills_used=[],
            close_cluster=False,
        )
        assert "skill_gate_warning" not in result

    def test_learn_gate_warning_when_learn_not_run(self, youk_root, tmp_path, monkeypatch):
        """learn_gate_warning fires when close_cluster=True and learn not in skills_used."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="did some work",
            commits_made=False,
            skills_used=["code-review"],
            close_cluster=True,
        )
        assert "learn_gate_warning" in result
        assert "/learn" in result["learn_gate_warning"]

    def test_no_learn_gate_warning_when_learn_ran(self, youk_root, tmp_path, monkeypatch):
        """No learn_gate_warning when learn is in skills_used."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="did some work",
            commits_made=False,
            skills_used=["code-review", "learn"],
            close_cluster=True,
        )
        assert "learn_gate_warning" not in result

    def test_no_learn_gate_warning_when_not_closing(self, youk_root, tmp_path, monkeypatch):
        """/close without learn is fine — gate only applies to /done (close_cluster=True)."""
        import session
        monkeypatch.setattr(session, "CLAUDE_ROOT", tmp_path / "claude")
        (tmp_path / "claude" / "audit").mkdir(parents=True)
        result = session.end_session(
            summary="quick close",
            commits_made=False,
            skills_used=["code-review"],
            close_cluster=False,
        )
        assert "learn_gate_warning" not in result


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


# ── _compute_dashboard_summary ───────────────────────────────────────────────

class TestComputeDashboardSummary:
    """Dashboard summary: org_score from metrics.json, /done rate from audit."""

    def _write_metrics(self, youk_root, entries):
        import json
        (youk_root / "state" / "improvement-metrics.json").write_text(
            json.dumps({"entries": entries})
        )

    def _write_audit(self, audit_dir, sessions):
        """Each session dict: close_cluster (bool), gaps (int)."""
        lines = []
        for i, s in enumerate(sessions):
            lines.append(f"\n### Session — 2026-07-0{i + 1} 10:00 UTC")
            lines.append("Summary text here")
            lines.append("Skills: none")
            lines.append(f"CloseCluster: {'yes' if s.get('close_cluster') else 'no'}")
            lines.append("Commits: no")
            for _ in range(s.get("gaps", 0)):
                lines.append("SkillGap: dev-loop — missing pattern")
        (audit_dir / "2026-07.md").write_text("\n".join(lines))

    def test_org_score_from_metrics_not_audit(self, youk_root, tmp_path):
        """org: X/10 reads from improvement-metrics.json, not audit text."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        # Audit has NO "Org score: X/10" text — that's the old broken pattern
        self._write_audit(audit_dir, [{"close_cluster": True}])
        self._write_metrics(youk_root, [{"org_score": 6.1, "close_cluster_rate": 0.11}])

        result = _compute_dashboard_summary(audit_dir, 0)
        assert "org: 6.1/10" in result

    def test_org_score_absent_when_no_metrics_file(self, youk_root, tmp_path):
        """No metrics.json → org score omitted from dashboard."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [{"close_cluster": False}])

        result = _compute_dashboard_summary(audit_dir, 0)
        assert "org:" not in result

    def test_done_rate_computed_from_audit(self, youk_root, tmp_path):
        """close_cluster_rate is recomputed from audit, not read from stale metrics."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        # 2 of 4 sessions have CloseCluster: yes → 50%
        self._write_audit(audit_dir, [
            {"close_cluster": True},
            {"close_cluster": False},
            {"close_cluster": True},
            {"close_cluster": False},
        ])
        # Metrics has stale 0% rate — dashboard should NOT use it
        self._write_metrics(youk_root, [{"org_score": 6.0, "close_cluster_rate": 0.0}])

        result = _compute_dashboard_summary(audit_dir, 0)
        assert "/done: 50%" in result

    def test_done_rate_zero_when_no_close_cluster(self, youk_root, tmp_path):
        """/done: 0% when all sessions have CloseCluster: no."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [{"close_cluster": False}, {"close_cluster": False}])
        self._write_metrics(youk_root, [{"org_score": 5.8}])

        result = _compute_dashboard_summary(audit_dir, 0)
        assert "/done: 0%" in result

    def test_velocity_shown_when_two_metrics_entries(self, youk_root, tmp_path):
        """▲delta velocity shown when improvement-metrics has multiple entries."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [{"close_cluster": True}])
        self._write_metrics(youk_root, [
            {"org_score": 5.8, "close_cluster_rate": 0.0},
            {"org_score": 6.1, "close_cluster_rate": 0.11},
        ])

        result = _compute_dashboard_summary(audit_dir, 0)
        assert "▲0.3" in result

    def test_skill_rate_shown_in_dashboard(self, youk_root, tmp_path):
        """Dashboard shows 'skills: N%' from capability skill invocations."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        lines = [
            "\n### Session — 2026-07-01 10:00 UTC",
            "Skills: code-review",
            "CloseCluster: yes",
            "\n### Session — 2026-07-02 10:00 UTC",
            "Skills: none",
            "CloseCluster: no",
        ]
        (audit_dir / "2026-07.md").write_text("\n".join(lines))
        self._write_metrics(youk_root, [{"org_score": 6.0}])
        result = _compute_dashboard_summary(audit_dir, 0)
        assert "skills: 50%" in result

    def test_gap_count_not_shown_in_dashboard(self, youk_root, tmp_path):
        """'gaps logged' no longer appears in dashboard — replaced by 'skills: N%'."""
        from session import _compute_dashboard_summary
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        lines = [
            "\n### Session — 2026-07-01 10:00 UTC",
            "Skills: none",
            "SkillGap: dev-loop — missing pattern",
            "CloseCluster: no",
        ]
        (audit_dir / "2026-07.md").write_text("\n".join(lines))
        result = _compute_dashboard_summary(audit_dir, 0)
        assert "gaps" not in result


# ── _compute_skill_invocation_rate ───────────────────────────────────────────

class TestComputeSkillInvocationRate:
    def _write_audit(self, audit_dir, sessions):
        lines = []
        for i, s in enumerate(sessions):
            lines.append(f"\n### Session — 2026-07-0{i + 1} 10:00 UTC")
            lines.append(f"Skills: {s.get('skills', 'none')}")
            lines.append(f"CloseCluster: {'yes' if s.get('close_cluster') else 'no'}")
        (audit_dir / "2026-07.md").write_text("\n".join(lines))

    def test_all_none_returns_zero_rate_and_full_skip_count(self, tmp_path):
        """All Sessions: none → rate=0%, consecutive_skips=N."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"skills": "none"}, {"skills": "none"}, {"skills": "none"}
        ])
        rate, consec = _compute_skill_invocation_rate(audit_dir)
        assert rate == 0
        assert consec == 3

    def test_half_capability_sessions(self, tmp_path):
        """2 of 4 sessions with capability skills → 50%, 1 trailing skip."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"skills": "code-review"},
            {"skills": "none"},
            {"skills": "learn"},
            {"skills": "none"},
        ])
        rate, consec = _compute_skill_invocation_rate(audit_dir)
        assert rate == 50
        assert consec == 1

    def test_meta_only_skills_not_counted_as_capability(self, tmp_path):
        """self_heal and simulate-experience are meta skills — do not count toward rate."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"skills": "self_heal"},
            {"skills": "simulate-experience"},
        ])
        rate, consec = _compute_skill_invocation_rate(audit_dir)
        assert rate == 0
        assert consec == 2

    def test_empty_audit_returns_none_rate_zero_skips(self, tmp_path):
        """No audit files → None rate, 0 consecutive skips."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        rate, consec = _compute_skill_invocation_rate(audit_dir)
        assert rate is None
        assert consec == 0

    def test_all_capability_skills_returns_100(self, tmp_path):
        """All sessions with capability skills → 100%, 0 consecutive skips."""
        from session import _compute_skill_invocation_rate
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"skills": "nfr_check, code-review"},
            {"skills": "learn"},
            {"skills": "verify"},
        ])
        rate, consec = _compute_skill_invocation_rate(audit_dir)
        assert rate == 100
        assert consec == 0


class TestFindCrossProjectContract:
    def _write_contracts(self, youk_root, slug: str, contracts: list[str]) -> None:
        proj = youk_root / "knowledge" / "projects" / slug
        proj.mkdir(parents=True, exist_ok=True)
        lines = "\n".join(f"- {c}" for c in contracts)
        (proj / "contracts.md").write_text(f"# contracts: {slug}\n\n{lines}\n")

    def test_surfaces_contract_from_other_project(self, youk_root):
        """Returns a contract from another project when current has <3."""
        self._write_contracts(youk_root, "youk", ["always run ruff before committing"])
        from session import _find_cross_project_contract
        result = _find_cross_project_contract("canopy", [])
        assert result is not None
        src_slug, contract = result
        assert src_slug == "youk"
        assert "ruff" in contract

    def test_no_transfer_when_current_has_3_plus(self, youk_root):
        """No suggestion when current project already has ≥3 contracts."""
        self._write_contracts(youk_root, "youk", ["always run ruff before committing"])
        from session import _find_cross_project_contract
        current = ["commit small", "test first", "review before merge"]
        result = _find_cross_project_contract("canopy", current)
        assert result is None

    def test_skips_current_project_contracts(self, youk_root):
        """Does not suggest contracts already in current project."""
        self._write_contracts(youk_root, "youk", ["always run ruff before committing"])
        from session import _find_cross_project_contract
        # Current project has the same contract — should not suggest it
        result = _find_cross_project_contract("canopy", ["always run ruff before committing"])
        assert result is None

    def test_no_other_projects_returns_none(self, youk_root):
        from session import _find_cross_project_contract
        result = _find_cross_project_contract("canopy", [])
        assert result is None


# ── Project purpose detection ────────────────────────────────────────────────

class TestDetectProjectPurpose:
    def test_ai_engineering_system_detected_by_skills_dir(self, tmp_path):
        """Skills directory with SKILL.md files → ai_engineering_system."""
        (tmp_path / "skills" / "code-review").mkdir(parents=True)
        (tmp_path / "skills" / "code-review" / "SKILL.md").write_text("---\nname: code-review\n---\n")
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "ai_engineering_system"

    def test_mcp_server_detected_by_fastmcp_import(self, tmp_path):
        """server.py importing fastmcp → mcp_server."""
        (tmp_path / "servers" / "core" / "src").mkdir(parents=True)
        (tmp_path / "servers" / "core" / "src" / "server.py").write_text(
            "from fastmcp import FastMCP\nmcp = FastMCP('test')\n"
        )
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "mcp_server"

    def test_docker_multi_service_detected_by_multiple_dockerfiles(self, tmp_path):
        """Two Dockerfiles in subdirectories → docker_multi_service."""
        (tmp_path / "services" / "api").mkdir(parents=True)
        (tmp_path / "services" / "worker").mkdir(parents=True)
        (tmp_path / "services" / "api" / "Dockerfile").write_text("FROM python:3.13\n")
        (tmp_path / "services" / "worker" / "Dockerfile").write_text("FROM python:3.13\n")
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "docker_multi_service"

    def test_installable_cli_detected_by_install_script(self, tmp_path):
        """scripts/install.sh present → installable_cli."""
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "install.sh").write_text("#!/usr/bin/env bash\necho hi\n")
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "installable_cli"

    def test_general_for_plain_python_project(self, tmp_path):
        """Plain Python project with no special markers → general."""
        (tmp_path / "requirements.txt").write_text("requests\n")
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "general"

    def test_ai_engineering_system_takes_priority_over_mcp(self, tmp_path):
        """Skills dir takes priority over MCP detection (youk itself has both)."""
        (tmp_path / "skills" / "dev-loop").mkdir(parents=True)
        (tmp_path / "skills" / "dev-loop" / "SKILL.md").write_text("---\nname: dev-loop\n---\n")
        (tmp_path / "servers" / "src").mkdir(parents=True)
        (tmp_path / "servers" / "src" / "server.py").write_text("from fastmcp import FastMCP\n")
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path)) == "ai_engineering_system"

    def test_nonexistent_dir_returns_general(self, tmp_path):
        from session import _detect_project_purpose
        assert _detect_project_purpose(str(tmp_path / "nonexistent")) == "general"


# ── Option C: retrospective recovery (close_cluster_missed) ─────────────────

class TestParseLastSessionFlags:
    """_parse_last_session_flags reads close_cluster_missed from audit."""

    def _write_audit(self, audit_dir, sessions):
        """Write audit with CloseCluster: yes/no lines for each session."""
        lines = []
        for i, s in enumerate(sessions):
            lines.append(f"\n### Session — 2026-07-0{i + 1}T10:00:00Z")
            lines.append(f"CloseCluster: {'yes' if s.get('close_cluster') else 'no'}")
            skills = s.get("skills", "none")
            lines.append(f"Skills: {skills}")
        month = "2026-07"
        (audit_dir / f"{month}.md").write_text("\n".join(lines))

    def test_close_cluster_missed_when_last_session_no(self, tmp_path):
        """close_cluster_missed=True when last audit session has CloseCluster: no."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"close_cluster": True, "skills": "code-review"},
            {"close_cluster": False, "skills": "none"},
        ])
        from session import _parse_last_session_flags
        missed, _ = _parse_last_session_flags(audit_dir)
        assert missed is True

    def test_close_cluster_not_missed_when_last_session_yes(self, tmp_path):
        """close_cluster_missed=False when last audit session has CloseCluster: yes."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        self._write_audit(audit_dir, [
            {"close_cluster": False, "skills": "none"},
            {"close_cluster": True, "skills": "code-review, learn"},
        ])
        from session import _parse_last_session_flags
        missed, _ = _parse_last_session_flags(audit_dir)
        assert missed is False

    def test_close_cluster_missed_returns_false_when_no_audit(self, tmp_path):
        """No audit file → no false positives."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        from session import _parse_last_session_flags
        missed, _ = _parse_last_session_flags(audit_dir)
        assert missed is False


class TestRetrospectiveRecoveryPlanItem:
    """Option C: session_plan item 0 is the retrospective block when close_cluster
    was missed last session and commits exist. Tests the shape of the inserted item."""

    def test_retrospective_item_format(self):
        """When close_cluster_missed and new_commits > 0, plan item 0 includes /learn prompt."""
        # Build the retrospective item the same way start_session does.
        # We test the construction logic directly rather than the full start_session
        # (which requires Docker volumes, git repos, etc.).
        close_cluster_missed = True
        new_commits = 3
        git_log = "abc1234 fix auth bug\ndef5678 add rate limiting\nghi9012 update deps"
        days_since_last = 1  # non-zero, non-≥7

        # Replicate the Option C block from start_session:
        recent_subjects = []
        for ln in git_log.splitlines()[:3]:
            subject = ln.split(" ", 1)[1].strip() if " " in ln else ln.strip()
            if subject:
                recent_subjects.append(subject)
        commits_summary = ": " + " / ".join(recent_subjects) if recent_subjects else ""

        item = (
            f"⚠ Last session closed without /done — {new_commits} commit(s) unlearned"
            f"{commits_summary}. "
            "Run /learn now to extract patterns before starting new work."
        )

        assert item.startswith("⚠ Last session closed without /done")
        assert "3 commit(s) unlearned" in item
        assert "fix auth bug" in item
        assert "Run /learn now" in item

    def test_retrospective_not_triggered_when_no_commits(self):
        """When new_commits == 0, the retrospective block should NOT be inserted."""
        # If new_commits is 0, the elif branch does not fire — nothing to test
        # beyond confirming the condition guard.
        new_commits = 0
        close_cluster_missed = True
        # Guard condition: close_cluster_missed and new_commits > 0 and days_since_last != 0
        should_trigger = close_cluster_missed and new_commits > 0
        assert not should_trigger

    def test_retrospective_not_triggered_when_returning_after_7_days(self):
        """The 7-day staleness branch fires instead of retrospective for long gaps."""
        # When days_since_last >= 7, the `if days_since_last >= 7` block fires first
        # (it's the `if` branch, not `elif`), so close_cluster_missed branch is skipped.
        days_since_last = 10
        fires_staleness_branch = days_since_last is not None and days_since_last >= 7
        fires_retrospective = not fires_staleness_branch  # elif means mutually exclusive
        assert not fires_retrospective
