"""Shared test fixtures for youk unit tests.

Sets up sys.path so server modules can be imported directly without Docker,
and provides fixtures that patch module-level path constants to tmp dirs.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pytest

_GIT_ENV_KEYS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


@pytest.fixture(autouse=True)
def _clear_git_env(monkeypatch):
    """Remove git hook env vars so subprocess git calls in tests use the correct repo."""
    for key in _GIT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

_REPO = Path(__file__).parent.parent
for _p in [
    str(_REPO / "servers" / "shared"),
    str(_REPO / "servers" / "core" / "src"),
    str(_REPO / "servers" / "code" / "src"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def youk_root(tmp_path, monkeypatch):
    """Isolated YOUK_ROOT pointing to a tmp directory."""
    root = tmp_path / "youk"
    (root / "knowledge" / "proposals").mkdir(parents=True)
    (root / "knowledge" / "projects").mkdir(parents=True)
    (root / "state").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)

    import session
    import health
    import compaction
    import review
    import task_contract
    import knowledge_index

    monkeypatch.setattr(session, "YOUK_ROOT", root)
    monkeypatch.setattr(session, "STATE_FILE", root / "state" / "session.json")
    monkeypatch.setattr(health, "YOUK_ROOT", root)
    monkeypatch.setattr(health, "PROPOSALS_FILE", root / "knowledge" / "proposals" / "PENDING.md")
    monkeypatch.setattr(health, "_PROPOSALS_DB", root / "knowledge" / "shared-index.db")
    monkeypatch.setattr(compaction, "YOUK_ROOT", root)
    monkeypatch.setattr(review, "_DOC_MAP_PATH", root / "docs" / "doc-map.yaml")
    monkeypatch.setattr(task_contract, "YOUK_ROOT", root)
    monkeypatch.setattr(task_contract, "_CONTRACTS_DIR", root / "state" / "task-contracts")
    monkeypatch.setattr(task_contract, "_RISK_LEDGER", root / "state" / "risk-ledger.jsonl")
    monkeypatch.setattr(task_contract, "_AUDIT_DIR", root / "audit")
    # Frames file — point to the real repo file for frame-source tests
    _real_frames = Path(__file__).parent.parent / "skills" / "adversarial-planning" / "references" / "frames.md"
    if _real_frames.exists():
        monkeypatch.setattr(task_contract, "_FRAMES_FILE", _real_frames)
    # Routes file — point to real config
    _real_routes = Path(__file__).parent.parent / "config" / "routes.yaml"
    if _real_routes.exists():
        monkeypatch.setattr(task_contract, "_ROUTES_FILE", _real_routes)
    # knowledge_index patching
    monkeypatch.setattr(knowledge_index, "YOUK_ROOT", root)
    monkeypatch.setattr(knowledge_index, "_INDEX_FILE", root / "knowledge" / "INDEX.md")
    monkeypatch.setattr(knowledge_index, "_USAGE_LOG", root / "state" / "knowledge-usage.jsonl")
    monkeypatch.setattr(knowledge_index, "_ARCHIVE_DIR", root / "knowledge" / "archive")

    return root


@pytest.fixture
def claude_root(tmp_path, monkeypatch):
    """Isolated CLAUDE_ROOT (audit dir etc) pointing to a tmp directory."""
    root = tmp_path / "claude"
    (root / "audit").mkdir(parents=True)

    import health
    monkeypatch.setattr(health, "CLAUDE_ROOT", root)
    monkeypatch.setattr(health, "AUDIT_DIR", root / "audit")

    return root
