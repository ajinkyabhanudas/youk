"""Tests for contract_verifier — MCP tool signature drift detection."""
from __future__ import annotations

import textwrap
from pathlib import Path

from contract_verifier import _extract_tools, _extract_call_sites, verify_contracts


# --- _extract_tools ---

def test_extract_tools_returns_decorated_functions(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(textwrap.dedent("""\
        mcp = object()

        @mcp.tool()
        def my_tool(task: str, size: str = "M") -> dict:
            pass

        def not_a_tool(x: int) -> None:
            pass
    """))
    tools = _extract_tools(src)
    assert "my_tool" in tools
    assert tools["my_tool"] == ["task", "size"]
    assert "not_a_tool" not in tools


def test_extract_tools_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _extract_tools(tmp_path / "nonexistent.py") == {}


def test_extract_tools_syntax_error_returns_empty(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(: -> :")
    assert _extract_tools(bad) == {}


def test_extract_tools_no_params(tmp_path: Path) -> None:
    src = tmp_path / "server.py"
    src.write_text(textwrap.dedent("""\
        @mcp.tool()
        def next_task() -> dict:
            pass
    """))
    tools = _extract_tools(src)
    assert tools.get("next_task") == []


# --- _extract_call_sites ---

def test_extract_call_sites_finds_dot_notation(tmp_path: Path) -> None:
    f = tmp_path / "CLAUDE.md"
    f.write_text("Call `youk-core.session_start(project_dir)` at session open.")
    sites = _extract_call_sites(f)
    assert ("youk-core", "session_start", "project_dir") in sites


def test_extract_call_sites_finds_youk_code(tmp_path: Path) -> None:
    f = tmp_path / "SKILL.md"
    f.write_text("Call `youk-code.route_to_skill(skill, task)` here.")
    sites = _extract_call_sites(f)
    assert ("youk-code", "route_to_skill", "skill, task") in sites


def test_extract_call_sites_missing_file_returns_empty(tmp_path: Path) -> None:
    assert _extract_call_sites(tmp_path / "missing.md") == []


def test_extract_call_sites_no_matches(tmp_path: Path) -> None:
    f = tmp_path / "notes.md"
    f.write_text("No tool calls here at all.")
    assert _extract_call_sites(f) == []


# --- verify_contracts integration ---

def test_verify_contracts_returns_required_keys() -> None:
    result = verify_contracts()
    assert "verdict" in result
    assert result["verdict"] in ("CLEAN", "DRIFT_DETECTED")
    assert "findings" in result
    assert "tools_registered" in result
    assert "summary" in result
    assert "youk-core" in result["tools_registered"]
    assert "youk-code" in result["tools_registered"]


def test_verify_contracts_registered_tools_non_empty() -> None:
    result = verify_contracts()
    core_tools = result["tools_registered"].get("youk-core", [])
    code_tools = result["tools_registered"].get("youk-code", [])
    assert len(core_tools) > 10, "Expected many registered core tools"
    assert len(code_tools) > 5, "Expected several registered code tools"


def test_verify_contracts_findings_are_dicts() -> None:
    result = verify_contracts()
    for finding in result["findings"]:
        assert "severity" in finding
        assert "tool" in finding
        assert "server" in finding
        assert "detail" in finding


def test_verify_contracts_verify_mcp_contracts_registered_in_code_tools() -> None:
    result = verify_contracts()
    code_tools = result["tools_registered"].get("youk-code", [])
    assert "verify_mcp_contracts" in code_tools


def test_extract_call_sites_finds_bare_reference_without_parens(tmp_path: Path) -> None:
    # Bare backtick references (`youk-core.tool_name`) must be detected, not just paren form.
    f = tmp_path / "CLAUDE.md"
    f.write_text("Call `youk-core.session_start` to open a session.")
    sites = _extract_call_sites(f)
    assert ("youk-core", "session_start", "") in sites


def test_extract_call_sites_bare_reference_does_not_crash_on_none_args(tmp_path: Path) -> None:
    # Bare reference produces None for the optional group — must not AttributeError.
    f = tmp_path / "SKILL.md"
    f.write_text("Use `youk-code.route_to_skill` from skills.")
    sites = _extract_call_sites(f)
    # Third element is empty string, not None
    assert all(isinstance(args, str) for _, _, args in sites)
