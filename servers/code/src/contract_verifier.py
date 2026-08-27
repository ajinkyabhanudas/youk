"""MCP contract verifier — detect drift between tool signatures and call sites."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

# Repo root is 3 levels up from this file (servers/code/src/contract_verifier.py).
# This works in CI (repo checkout), in Docker (/claude/youk/servers/...), and locally.
_REPO_ROOT = Path(__file__).resolve().parents[3]

# CLAUDE.md and skills live either in the Docker mount (/claude) or the host ~/.claude.
# We resolve from YOUK_CLAUDE_ROOT env var first, then Docker, then host ~/.claude.
_env_root = os.environ.get("YOUK_CLAUDE_ROOT")
_docker_root = Path("/claude")
if _env_root:
    CLAUDE_ROOT = Path(_env_root)
elif _docker_root.exists():
    CLAUDE_ROOT = _docker_root
else:
    CLAUDE_ROOT = Path.home() / ".claude"

SKILLS_ROOT = CLAUDE_ROOT / "skills"

# Server files: always resolve from repo root — works in CI, Docker, and local dev.
_SERVER_FILES = {
    "youk-core": _REPO_ROOT / "servers" / "core" / "src" / "server.py",
    "youk-code": _REPO_ROOT / "servers" / "code" / "src" / "server.py",
}

# Server-prefixed call sites: `youk-core.tool_name(...)`. Parens optional.
_CALL_SITE_PATTERN = re.compile(
    r"`(youk-core|youk-code)\.([\w]+)(?:\(([^`]*)\))?`"
)

# Unprefixed call sites: `route_task(...)`, which is how CLAUDE.md writes most of them.
# The prefixed pattern alone covered 6 of 35 references across CLAUDE.md and the skills;
# the other 29 named 18 real tools and were invisible, so renaming any of them reported
# CLEAN. Matching on shape rather than syntax is deliberate: the registered tool list is
# already extracted from the servers by AST and is ground truth, so a name only has to be
# checked for membership. Widening the prefixed regex instead would just move the blind
# spot to whatever spelling the next author uses.
_BARE_CALL_SITE_PATTERN = re.compile(r"`([a-z_][a-z0-9_]{3,})\s*\(([^`]*)\)`")

# Prose that looks like a call but is not a tool reference. Checked against the
# registered-tool set first, so this only needs to catch names that collide.
_NOT_TOOLS = frozenset({
    "print", "len", "open", "range", "str", "int", "list", "dict", "set",
    "make", "cd", "git", "run", "pytest", "ruff", "docker", "pip", "npm",
})


def _extract_tools(server_file: Path) -> dict[str, list[str]]:
    """Return {tool_name: [param_names]} for all @mcp.tool()-decorated functions."""
    if not server_file.exists():
        return {}
    try:
        tree = ast.parse(server_file.read_text())
    except SyntaxError:
        return {}

    tools: dict[str, list[str]] = {}
    prev_is_tool = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if prev_is_tool:
                params = [
                    a.arg for a in node.args.args
                    if a.arg not in ("self",)
                ]
                tools[node.name] = params
        # Track whether the previous node at the top level was @mcp.tool()
    # Walk top-level only (not nested) to avoid false positives
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            decorated = any(
                (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                or (isinstance(d, ast.Attribute) and d.attr == "tool")
                for d in node.decorator_list
            )
            if decorated:
                params = [a.arg for a in node.args.args if a.arg != "self"]
                tools[node.name] = params
    return tools


def _extract_call_sites(
    path: Path, known_tools: frozenset[str] | None = None
) -> list[tuple[str, str, str]]:
    """Return [(server, tool_name, raw_args)] for tool references in a file.

    Two forms are collected. Server-prefixed references carry their own server, so they
    are attributed directly. Unprefixed references (`route_task(...)`) carry no server,
    so they are only treated as tool references when the name is in known_tools, and are
    attributed with an empty server string. That keeps ordinary prose and shell snippets
    out of the results without needing to enumerate everything that is not a tool.

    known_tools=None disables bare matching, which is what callers wanting the old
    prefixed-only behaviour should pass.
    """
    if not path.exists():
        return []
    text = path.read_text(errors="ignore")
    sites = [
        (m.group(1), m.group(2), (m.group(3) or "").strip())
        for m in _CALL_SITE_PATTERN.finditer(text)
    ]
    if known_tools:
        seen = {(s, t) for s, t, _ in sites}
        for m in _BARE_CALL_SITE_PATTERN.finditer(text):
            name = m.group(1)
            if name in _NOT_TOOLS or name not in known_tools:
                continue
            if any(t == name for _, t in seen):
                continue  # already counted in its prefixed form
            sites.append(("", name, m.group(2).strip()))
    return sites


def _collect_skill_files() -> list[Path]:
    if not SKILLS_ROOT.exists():
        return []
    return list(SKILLS_ROOT.rglob("SKILL.md"))


def verify_contracts() -> dict:
    """
    Compare registered MCP tool signatures against call sites in CLAUDE.md and SKILL.md files.

    Returns a findings dict with:
      - tools: {server: {name: [params]}}
      - missing_tools: call sites that reference a tool not registered in the server
      - removed_references: registered tools never referenced (informational, not an error)
      - findings: list of {severity, server, tool, file, detail}
      - verdict: CLEAN | DRIFT_DETECTED
    """
    # 1 — extract live tool registry
    registered: dict[str, dict[str, list[str]]] = {}
    for server, path in _SERVER_FILES.items():
        registered[server] = _extract_tools(path)

    # 2 — collect all call sites
    call_sources: list[Path] = []
    claude_md = CLAUDE_ROOT / "CLAUDE.md"
    if claude_md.exists():
        call_sources.append(claude_md)
    call_sources.extend(_collect_skill_files())

    # Every registered name across both servers, so unprefixed references can be
    # recognised by membership rather than by matching a particular prose syntax.
    known_tools = frozenset(
        name for tools in registered.values() for name in tools
    )

    all_call_sites: list[tuple[str, str, str, Path]] = []
    for src in call_sources:
        for server, tool, args in _extract_call_sites(src, known_tools):
            all_call_sites.append((server, tool, args, src))

    # 3 — cross-reference
    findings: list[dict] = []
    missing_tools: list[dict] = []

    seen_tools: set[tuple[str, str]] = set()
    for server, tool, args, src in all_call_sites:
        # An unprefixed reference names no server, so mark it seen on whichever server
        # registers it. Without this, every bare reference would also count its tool as
        # unreferenced, inverting the informational list.
        if not server:
            for s, tools in registered.items():
                if tool in tools:
                    seen_tools.add((s, tool))
            continue  # membership was already proven when it was collected
        seen_tools.add((server, tool))
        server_tools = registered.get(server, {})
        if tool not in server_tools:
            detail = f"Tool `{server}.{tool}` referenced but not registered in server"
            findings.append({
                "severity": "HIGH",
                "server": server,
                "tool": tool,
                "file": str(src.relative_to(CLAUDE_ROOT) if src.is_relative_to(CLAUDE_ROOT) else src),
                "detail": detail,
            })
            missing_tools.append({"server": server, "tool": tool, "referenced_in": str(src)})

    # 4 — find registered tools never referenced (informational)
    unreferenced: list[dict] = []
    for server, tools in registered.items():
        for name in tools:
            if (server, name) not in seen_tools:
                unreferenced.append({"server": server, "tool": name})

    verdict = "DRIFT_DETECTED" if findings else "CLEAN"
    return {
        "verdict": verdict,
        "tools_registered": {s: list(t.keys()) for s, t in registered.items()},
        "call_sites_scanned": len(call_sources),
        "findings": findings,
        "missing_tools": missing_tools,
        "unreferenced_tools": unreferenced,
        "summary": (
            f"{len(findings)} drift finding(s) across {len(call_sources)} scanned files"
            if findings else
            f"CLEAN — {sum(len(t) for t in registered.values())} tools verified across {len(call_sources)} files"
        ),
    }
