"""Tests for session.py — pending count, project type detection."""
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
