"""Shared test fixtures for youk unit tests.

Sets up sys.path so server modules can be imported directly without Docker,
and provides fixtures that patch module-level path constants to tmp dirs.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

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

    monkeypatch.setattr(session, "YOUK_ROOT", root)
    monkeypatch.setattr(session, "STATE_FILE", root / "state" / "session.json")
    monkeypatch.setattr(health, "YOUK_ROOT", root)
    monkeypatch.setattr(health, "PROPOSALS_FILE", root / "knowledge" / "proposals" / "PENDING.md")
    monkeypatch.setattr(compaction, "YOUK_ROOT", root)
    monkeypatch.setattr(review, "_DOC_MAP_PATH", root / "docs" / "doc-map.yaml")

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
