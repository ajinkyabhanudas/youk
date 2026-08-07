"""Wiring pulse — is every capability youk BUILT actually WIRED into the live loop?

The blind spot this closes: ~10k unit tests verify that each part does what its code says.
NONE verify that the part is actually invoked in the live system. So a tool can pass every
test, ship, and be dead on arrival — never called by CLAUDE.md routing, session code, or
another tool. This is how "we planned X, and sessions later found X was never wired" happens,
and it is invisible to unit tests by construction (a unit test of an orphan still passes).

This checks reachability, not correctness: for every @mcp.tool(), is it referenced anywhere
in the live loop? A tool referenced only in its own definition and its tests is ORPHANED —
built but not connected. Orphans are surfaced loudly, at every session_start (autorun — not
"due in N sessions"), so built-but-not-wired fails fast instead of becoming late tech debt.

A tool is WIRED if it is referenced in ANY of:
  - CLAUDE.md (the routing loop the model executes),
  - a live source module (session.py, intent.py, etc. — not its own server.py definition),
  - another tool's body in server.py (cross-tool call),
  - a skill's SKILL.md (a skill invokes it).
Some tools are legitimately terminal (called only by the user via slash-command). Those can
be allow-listed so they don't read as false orphans.
"""
from __future__ import annotations

import re
from pathlib import Path

YOUK_ROOT = Path("/youk")
CLAUDE_ROOT = Path("/claude")

# Tools invoked directly by the user/model via slash-commands or docs, not by other code.
# Allow-listed so they don't count as orphans. Keep this SMALL and justified — every entry
# is a claim that "nothing calls this, and that's correct."
_TERMINAL_TOOLS: frozenset[str] = frozenset({
    "session_start", "session_end", "route_task", "optimize_intent",
    "compact_context", "self_heal", "track_tokens", "check_command",
    "request_external_review", "index_project", "rebuild_knowledge_index",
    # Read-only stat/query tools: called ad-hoc by the model or developer when they want
    # the number, not wired into a loop. Flagging these as orphans cries wolf — a health
    # check that reports legitimate utilities as debt is itself dishonest.
    "get_concept_graph_stats", "get_file_index_stats", "get_skill_signals",
    "check_loop_dry", "mark_task_done",
})


def _defined_tools(server_py: Path) -> list[str]:
    """Every @mcp.tool() function name in server.py."""
    if not server_py.exists():
        return []
    text = server_py.read_text()
    return re.findall(r"@mcp\.tool\(\)\s*\ndef\s+(\w+)\s*\(", text)


def _routing_loop_text(claude_root: Path) -> str:
    """CLAUDE.md — the routing loop the model actually executes. A tool NAMED here (the model
    is instructed to call it) counts as wired, even without a '(' since the model calls it."""
    claude_md = claude_root / "CLAUDE.md"
    return claude_md.read_text() if claude_md.exists() else ""


def _live_call_corpus(youk_root: Path) -> str:
    """Source where a wired tool is actually CALLED. We look for `name(` — an invocation, not
    an import or a docstring mention. Excludes server.py's own tool DEFINITIONS + their wrapper
    bodies would be legitimate cross-tool calls, so we keep server.py but only invocation form
    is matched. Excludes tests (a tool called only by its test is still orphaned)."""
    parts: list[str] = []
    src = youk_root / "servers" / "core" / "src"
    for py in src.glob("*.py"):
        text = py.read_text()
        # Strip import lines and the wrapper def signature so `from X import name` /
        # `def name(` don't read as calls. What remains: actual `name(...)` invocations.
        text = re.sub(r"^\s*(from|import)\s.*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*def\s+\w+\s*\(", "", text, flags=re.MULTILINE)
        parts.append(text)
    # skills invoke tools by name in prose
    skills = youk_root / "skills"
    if skills.is_dir():
        for skill_md in skills.glob("*/SKILL.md"):
            parts.append(skill_md.read_text())
    return "\n".join(parts)


def check_wiring(youk_root: Path = YOUK_ROOT, claude_root: Path = CLAUDE_ROOT) -> dict:
    """Return which defined MCP tools are wired vs orphaned.

    A tool is WIRED only if:
      - it is NAMED in CLAUDE.md (the model is instructed to call it in the routing loop), OR
      - it is CALLED as `name(` in live source or a skill (an actual invocation),
    NOT merely imported or mentioned in a docstring. This strictness is the point — a lenient
    check that counts imports gives false "all healthy" readings, which is the exact
    false-confidence that let 6 tools ship orphaned this session.

    Returns {"total", "wired", "orphaned": [names], "terminal": [names], "wired_ratio"}.
    """
    server_py = youk_root / "servers" / "core" / "src" / "server.py"
    tools = _defined_tools(server_py)
    routing = _routing_loop_text(claude_root)
    calls = _live_call_corpus(youk_root)

    wired: list[str] = []
    orphaned: list[str] = []
    terminal: list[str] = []
    for t in tools:
        if t in _TERMINAL_TOOLS:
            terminal.append(t)
            continue
        named_in_routing = re.search(rf"\b{re.escape(t)}\b", routing) is not None
        # invocation: `name(` — with optional alias-underscore prefix used in server wrappers
        called = re.search(rf"\b_?{re.escape(t)}\s*\(", calls) is not None
        if named_in_routing or called:
            wired.append(t)
        else:
            orphaned.append(t)

    checked = len(wired) + len(orphaned)
    return {
        "total": len(tools),
        "wired": len(wired),
        "orphaned": sorted(orphaned),
        "terminal": sorted(terminal),
        "wired_ratio": round(len(wired) / checked, 3) if checked else 1.0,
    }


def format_wiring_warnings(result: dict, cap: int = 5) -> list[str]:
    """Session-start lines for orphaned tools — built but never invoked in the live loop."""
    orphaned = result.get("orphaned", [])
    if not orphaned:
        return []
    lines = [
        f"⚠ WIRING: {len(orphaned)} capability(ies) built but NOT invoked in the live loop "
        f"(orphaned — passing tests ≠ wired):"
    ]
    for name in orphaned[:cap]:
        lines.append(f"    · {name} — defined + tested, but nothing calls it. Wire it or remove it.")
    if len(orphaned) > cap:
        lines.append(f"    · …and {len(orphaned) - cap} more.")
    return lines
