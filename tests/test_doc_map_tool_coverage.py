"""
Drift sentinel: every @mcp.tool() must appear in docs/doc-map.yaml.

session_start already surfaces unmapped tools, but only as an advisory line in the
session plan. Six tools accumulated behind that warning before anyone acted on it,
so the check is repeated here as a test that fails the build instead.

This runs against the real repo files rather than a fixture. A fixture would test
the parsing and let the actual drift through, which is the failure mode being
guarded against.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parent.parent
SERVERS = {
    "youk-core": REPO / "servers" / "core" / "src" / "server.py",
    "youk-code": REPO / "servers" / "code" / "src" / "server.py",
}
TOOL_DEF = re.compile(r"@mcp\.tool\(\)\s*\ndef (\w+)")


def _declared_tools() -> dict[str, set[str]]:
    return {
        name: set(TOOL_DEF.findall(path.read_text()))
        for name, path in SERVERS.items()
        if path.exists()
    }


def _mapped_tools() -> set[str]:
    doc_map = yaml.safe_load((REPO / "docs" / "doc-map.yaml").read_text())
    return {
        entry["tool"]
        for entries in (doc_map.get("mcp_tools") or {}).values()
        for entry in entries
    }


def test_every_tool_is_in_doc_map():
    mapped = _mapped_tools()
    missing = {
        server: sorted(tools - mapped)
        for server, tools in _declared_tools().items()
        if tools - mapped
    }
    assert not missing, (
        f"tools missing from docs/doc-map.yaml: {missing}. "
        "Add an entry alongside the code change that introduced the tool."
    )


def test_doc_map_does_not_reference_removed_tools():
    """A stale entry is the mirror failure — it claims coverage for code that is gone."""
    declared = set().union(*_declared_tools().values())
    stale = sorted(_mapped_tools() - declared)
    assert not stale, (
        f"docs/doc-map.yaml lists tools that no longer exist: {stale}. "
        "Remove the entry alongside the code change that dropped the tool."
    )


def test_every_ref_path_exists():
    """A ref pointing at a deleted file makes the map useless as a change checklist."""
    doc_map = yaml.safe_load((REPO / "docs" / "doc-map.yaml").read_text())
    broken = []
    for server, entries in (doc_map.get("mcp_tools") or {}).items():
        for entry in entries:
            for ref in entry.get("refs") or []:
                if not (REPO / ref).exists():
                    broken.append(f"{server}/{entry['tool']} -> {ref}")
    assert not broken, f"doc-map refs point at missing files: {broken}"


def test_tool_definitions_were_actually_found():
    """Guards the regex itself — a rename of the decorator would silently pass everything."""
    declared = _declared_tools()
    assert declared, "no server.py found — the sentinel is not running against anything"
    for server, tools in declared.items():
        assert len(tools) > 5, f"{server}: found only {len(tools)} tools, regex likely stale"
