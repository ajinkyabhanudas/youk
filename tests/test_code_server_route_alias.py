"""Contract coverage for the youk-code route_to_skill MCP wrapper."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp")


def _code_server():
    path = Path(__file__).parent.parent / "servers" / "code" / "src" / "server.py"
    spec = importlib.util.spec_from_file_location("youk_code_server_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_route_to_skill_accepts_documented_skill_name_alias(monkeypatch):
    server = _code_server()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        server,
        "_route_to_skill",
        lambda skill, task, context: captured.update(
            skill=skill, task=task, context=context
        )
        or {"skill_name": skill},
    )

    result = server.route_to_skill(task="test", skill_name="challenge")

    assert result == {"skill_name": "challenge"}
    assert captured == {"skill": "challenge", "task": "test", "context": None}


def test_route_to_skill_rejects_conflicting_aliases():
    server = _code_server()

    result = server.route_to_skill(task="test", skill="challenge", skill_name="dev-loop")

    assert result["blocked"] is True
