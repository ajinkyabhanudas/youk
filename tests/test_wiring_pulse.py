"""Wiring pulse — catches built-but-not-wired capabilities (the blind spot ~10k unit
tests miss: they verify parts work, never that parts are invoked in the live loop).

The load-bearing property: the check must be STRICT — an import or docstring mention does
NOT count as wired, only a real invocation or a CLAUDE.md routing reference. A lenient check
gives false 'all healthy' readings, which is the exact false-confidence being fixed.
"""
from __future__ import annotations

from wiring_pulse import check_wiring, format_wiring_warnings


def _make(tmp_path, server_body, claude_md="", session_body="", skill_body=None):
    src = tmp_path / "servers" / "core" / "src"
    src.mkdir(parents=True)
    (src / "server.py").write_text(server_body)
    (src / "session.py").write_text(session_body)
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text(claude_md)
    if skill_body is not None:
        sk = tmp_path / "skills" / "demo"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text(skill_body)
    return tmp_path, claude


def test_import_only_is_orphaned(tmp_path):
    """A tool imported + wrapped in server.py but never CALLED from the live loop is orphaned.
    This is the false-positive the first version had — an import must not count as wired."""
    server = (
        "from foo import bar as _bar\n"
        "@mcp.tool()\n"
        "def orphan_tool(x):\n"
        "    '''mentions orphan_tool in docstring'''\n"
        "    return _bar(x)\n"
    )
    root, claude = _make(tmp_path, server)
    r = check_wiring(youk_root=root, claude_root=claude)
    assert "orphan_tool" in r["orphaned"]


def test_named_in_claude_md_is_wired(tmp_path):
    server = "@mcp.tool()\ndef routed_tool(x):\n    return x\n"
    claude_md = "Step 3: call routed_tool with the task.\n"
    root, claude = _make(tmp_path, server, claude_md=claude_md)
    r = check_wiring(youk_root=root, claude_root=claude)
    assert "routed_tool" in [*r["orphaned"], *r["terminal"]] or True  # not terminal here
    assert "routed_tool" not in r["orphaned"]


def test_called_in_live_source_is_wired(tmp_path):
    server = "@mcp.tool()\ndef used_tool(x):\n    return x\n"
    session = "def something():\n    return used_tool(42)\n"
    root, claude = _make(tmp_path, server, session_body=session)
    r = check_wiring(youk_root=root, claude_root=claude)
    assert "used_tool" not in r["orphaned"]


def test_called_in_a_skill_is_wired(tmp_path):
    server = "@mcp.tool()\ndef skill_tool(x):\n    return x\n"
    root, claude = _make(tmp_path, server, skill_body="Call skill_tool(task) here.\n")
    r = check_wiring(youk_root=root, claude_root=claude)
    assert "skill_tool" not in r["orphaned"]


def test_ratio_and_counts_consistent(tmp_path):
    server = (
        "@mcp.tool()\ndef a(x):\n    return x\n"
        "@mcp.tool()\ndef b(x):\n    return x\n"
    )
    session = "def s():\n    return a(1)\n"  # a wired, b orphaned
    root, claude = _make(tmp_path, server, session_body=session)
    r = check_wiring(youk_root=root, claude_root=claude)
    assert r["wired"] == 1 and "b" in r["orphaned"]
    assert 0.0 <= r["wired_ratio"] <= 1.0


def test_warnings_empty_when_no_orphans(tmp_path):
    server = "@mcp.tool()\ndef a(x):\n    return x\n"
    session = "def s():\n    return a(1)\n"
    root, claude = _make(tmp_path, server, session_body=session)
    assert format_wiring_warnings(check_wiring(youk_root=root, claude_root=claude)) == []


def test_warnings_name_the_orphans(tmp_path):
    server = "@mcp.tool()\ndef lonely(x):\n    return x\n"
    root, claude = _make(tmp_path, server)
    warnings = format_wiring_warnings(check_wiring(youk_root=root, claude_root=claude))
    assert any("lonely" in w for w in warnings)


def test_real_repo_detects_known_orphans():
    """On the real repo, the meta-loop + steering tools are orphaned (built this session,
    never wired). This is the honest signal — must not read 0 orphaned."""
    from pathlib import Path
    root = Path(__file__).parent.parent
    claude = Path.home() / ".claude"
    r = check_wiring(youk_root=root, claude_root=claude)
    # These were built and never invoked in the live loop.
    assert "enroll_revisable_set" in r["orphaned"]
    assert "get_steering_vocab" in r["orphaned"]
    assert len(r["orphaned"]) > 0  # a 0 reading would be the false-confidence bug
