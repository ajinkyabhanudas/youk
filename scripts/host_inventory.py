#!/usr/bin/env python3
"""
Structural scanner (CIR-154 item 1): inventories every host-differentiated
mechanism in the youk codebase and whether it is actually wired for each
agent host that declares support for it.

Why this exists: CIR-152's post-mortem on the "youk is agent-agnostic" claim
found it was verified too narrowly — context handoff was tested, enforcement-
layer parity never was, and nobody caught the gap because nothing enumerated
the domain (every host x every mechanism) before the claim was decomposed by
hand. This scanner makes that enumeration mechanical.

The capability vocabulary it enumerates comes directly from
servers/shared/agent_host.py's HostCapability enum and each *Host class's
`capabilities = HostCapabilities(..., supported=frozenset({...}))`
declaration — parsed via `ast`, not retyped here — so the domain a claim gets
checked against is never narrower than what the codebase actually declares.

"Declared" (agent_host.py's own HostCapabilities.supported) and "wired" (this
module's independent grep+AST evidence search) are deliberately two separate
signals: a capability can be declared supported for a host and still come
back wired=False here. That mismatch is the exact shape of CIR-152's miss —
agent_host.py's CodexHost declares PRE_TOOL_GUARD supported, but nothing in
the codebase ever calls the underlying gate (check_m_plus_write_gate) from a
Codex-reachable boundary. Re-running this scanner is how that gap becomes a
real JSON row instead of something only caught by the founder asking directly.
"""
from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

AGENT_HOST_PATH = REPO_ROOT / "servers" / "shared" / "agent_host.py"
HOOKS_JSON_PATH = REPO_ROOT / "plugin" / "hooks" / "hooks.json"

# The literal hook-event name each capability corresponds to in this
# codebase's own vocabulary. Not invented for this scanner: PreCompact /
# UserPromptSubmit / PreToolUse are the exact top-level keys
# plugin/hooks/hooks.json already uses, and SessionStart is the exact
# hookEventName servers/core/src/server.py's session_start_hook emits for
# Codex (see CodexHost.render_session_context in agent_host.py).
CAPABILITY_HOOK_EVENT: dict[str, str] = {
    "session_context": "SessionStart",
    "compaction_context": "PreCompact",
    "prompt_context": "UserPromptSubmit",
    "pre_tool_guard": "PreToolUse",
}

# Extra grep terms that count as real wiring evidence for a capability even
# when a host has no hook literally named after the event above (e.g. Codex
# has no PreCompact-equivalent event; its compaction context instead rides
# inside the SessionStart payload via verbatim_lines — see
# CodexHost.render_session_context).
CAPABILITY_EXTRA_TERMS: dict[str, list[str]] = {
    "session_context": ["session_start"],
    "compaction_context": ["verbatim_lines"],
    "prompt_context": [],
    "pre_tool_guard": ["check_m_plus_write_gate"],
}

PY_SCAN_DIRS = ["servers", "plugin"]
EXCLUDE_DIR_NAMES = {"__pycache__", ".git", "node_modules"}

# Structural evidence that a piece of code branches on which agent host it is
# running under, for the broader "every host-conditional branch" inventory
# (item 1's fuller ask) — informational, not consumed by the checker.
_BRANCH_PATTERNS = [
    re.compile(r'\bhost_id\s*==\s*["\']'),
    re.compile(r'\bhost\s*==\s*["\'](claude-code|codex)["\']'),
    re.compile(r'isinstance\([^)]*,\s*(ClaudeCodeHost|CodexHost)\)'),
    re.compile(r'CLAUDE_PLUGIN_ROOT'),
]


@dataclass
class ScopeSpan:
    name: str
    lineno: int
    end_lineno: int
    text_lower: str  # name + docstring, lowercased, for host-mention checks


def _iter_py_files() -> list[Path]:
    files = []
    for d in PY_SCAN_DIRS:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in EXCLUDE_DIR_NAMES for part in p.parts):
                continue
            files.append(p)
    return sorted(files)


def _blank_span(mask: list[list[str]], start: tuple[int, int], end: tuple[int, int]) -> None:
    (sl, sc), (el, ec) = start, end
    if sl == el:
        for i in range(sc, min(ec, len(mask[sl - 1]))):
            mask[sl - 1][i] = " "
        return
    for i in range(sc, len(mask[sl - 1])):
        mask[sl - 1][i] = " "
    for ln in range(sl, el - 1):
        mask[ln] = [" "] * len(mask[ln])
    for i in range(0, min(ec, len(mask[el - 1]))):
        mask[el - 1][i] = " "


def _code_only_lines(path: Path, raw_lines: list[str]) -> list[str]:
    """raw_lines with comments and triple-quoted string literals (this
    codebase's docstring/comment-block convention) blanked out, same line
    count and positions preserved.

    Exists because a docstring can *describe* a mechanism without the code
    actually implementing it — e.g. agent_host.py's CodexHost docstring says
    "whatever the host's PreToolUse-equivalent event is" while explicitly
    disclaiming that no such wiring has been exercised. Matching that prose
    as "PreToolUse wiring evidence" would be exactly the kind of narrative-
    not-mechanical false positive this scanner exists to avoid. Falls back to
    raw_lines unchanged if the file fails to tokenize.
    """
    mask = [list(line) for line in raw_lines]
    try:
        source = "\n".join(raw_lines) + "\n"
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except Exception:
        return raw_lines
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            _blank_span(mask, tok.start, tok.end)
        elif tok.type == tokenize.STRING and tok.string.lstrip("rRbBuU").startswith(('"""', "'''")):
            _blank_span(mask, tok.start, tok.end)
    return ["".join(row) for row in mask]


def _scopes_in_file(path: Path) -> list[ScopeSpan]:
    """Every function/class definition in a file, with its docstring, so a
    matched line can be attributed to the scope that contains it. Best-effort:
    a file that fails to parse yields no scopes rather than raising."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception:
        return []
    scopes: list[ScopeSpan] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node) or ""
            end = getattr(node, "end_lineno", node.lineno)
            scopes.append(ScopeSpan(
                name=node.name,
                lineno=node.lineno,
                end_lineno=end,
                text_lower=(node.name + " " + doc).lower(),
            ))
    return scopes


def _enclosing_scope(scopes: list[ScopeSpan], lineno: int) -> ScopeSpan | None:
    """The smallest scope whose span contains lineno (innermost def/class)."""
    best = None
    for s in scopes:
        if s.lineno <= lineno <= s.end_lineno:
            if best is None or (s.end_lineno - s.lineno) < (best.end_lineno - best.lineno):
                best = s
    return best


def _all_capability_names(tree: ast.Module) -> set[str]:
    """Every member of the HostCapability enum, lowercased — parsed from its
    own class body so `frozenset(HostCapability)` (ClaudeCodeHost's "supports
    everything" declaration) can be expanded without hardcoding the member
    list a second time in this scanner."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "HostCapability":
            names: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id.lower())
            return names
    return set()


def extract_declared_capabilities() -> dict[str, set[str]]:
    """Parse agent_host.py's *Host classes for their declared capability set.

    Real AST parse of each
    `capabilities = HostCapabilities(host_id=..., supported=frozenset({...}))`
    assignment — the declared domain comes from the code, never from a guess
    hardcoded into this scanner. Handles both the explicit-set form
    (`frozenset({HostCapability.X, ...})`, e.g. CodexHost) and the "supports
    every known capability" form (`frozenset(HostCapability)`, ClaudeCodeHost).
    """
    tree = ast.parse(AGENT_HOST_PATH.read_text(encoding="utf-8"), filename=str(AGENT_HOST_PATH))
    all_capabilities = _all_capability_names(tree)
    declared: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "capabilities" for t in stmt.targets):
                continue
            call = stmt.value
            if not isinstance(call, ast.Call):
                continue
            host_id = None
            supported: set[str] = set()
            for kw in call.keywords:
                if kw.arg == "host_id" and isinstance(kw.value, ast.Constant):
                    host_id = kw.value.value
                if kw.arg == "supported":
                    value = kw.value
                    is_bare_enum = (
                        isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "frozenset"
                        and len(value.args) == 1
                        and isinstance(value.args[0], ast.Name)
                        and value.args[0].id == "HostCapability"
                    )
                    if is_bare_enum:
                        supported |= all_capabilities
                    else:
                        for sub in ast.walk(value):
                            if (isinstance(sub, ast.Attribute)
                                    and isinstance(sub.value, ast.Name)
                                    and sub.value.id == "HostCapability"):
                                supported.add(sub.attr.lower())
            if host_id:
                declared[host_id] = supported
    return declared


def _hooks_json_claude_wiring() -> dict[str, str | None]:
    """hook_event -> "plugin/hooks/hooks.json:<line>" when that event is a
    real top-level key in the Claude Code plugin hook manifest, else None."""
    evidence: dict[str, str | None] = {}
    if not HOOKS_JSON_PATH.exists():
        return {event: None for event in CAPABILITY_HOOK_EVENT.values()}
    raw = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    events = data.get("hooks", {})
    lines = raw.splitlines()
    for event in CAPABILITY_HOOK_EVENT.values():
        if event not in events:
            evidence[event] = None
            continue
        evidence[event] = None
        for i, line in enumerate(lines, start=1):
            if re.match(rf'\s*"{re.escape(event)}"\s*:', line):
                rel = HOOKS_JSON_PATH.relative_to(REPO_ROOT)
                evidence[event] = f"{rel}:{i}"
                break
    return evidence


def _codex_wiring_evidence(capability: str) -> str | None:
    """file:line if some function/class scope in the codebase both mentions
    "codex" and references this capability's hook event or mechanism terms,
    else None. Real grep + AST enclosing-scope match — not a lookup table of
    pre-decided answers."""
    terms = [CAPABILITY_HOOK_EVENT[capability]] + CAPABILITY_EXTRA_TERMS.get(capability, [])
    term_res = [re.compile(re.escape(t), re.IGNORECASE) for t in terms]
    for path in _iter_py_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        code_lines = _code_only_lines(path, lines)
        scopes = _scopes_in_file(path)
        for i, code_line in enumerate(code_lines, start=1):
            if not any(r.search(code_line) for r in term_res):
                continue
            scope = _enclosing_scope(scopes, i)
            scope_text = scope.text_lower if scope else ""
            window = "\n".join(lines[max(0, i - 15):i]).lower()
            if "codex" in scope_text or "codex" in window:
                rel = path.relative_to(REPO_ROOT)
                line_no = scope.lineno if scope else i
                return f"{rel}:{line_no}"
    return None


def _wiring_evidence(host: str, capability: str, claude_hook_evidence: dict[str, str | None]) -> str | None:
    if host == "claude-code":
        return claude_hook_evidence.get(CAPABILITY_HOOK_EVENT[capability])
    if host == "codex":
        return _codex_wiring_evidence(capability)
    return None


def scan_iter():
    """Yield (mechanism, {"mechanism": ..., "hosts": {...}}) one capability at
    a time, so a caller can persist live progress without recomputing."""
    declared = extract_declared_capabilities()
    claude_hook_evidence = _hooks_json_claude_wiring()
    for capability in CAPABILITY_HOOK_EVENT:
        hosts_declaring = {h for h, caps in declared.items() if capability in caps}
        hosts: dict[str, dict] = {}
        for host in sorted(hosts_declaring):
            evidence = _wiring_evidence(host, capability, claude_hook_evidence)
            hosts[host] = {"wired": evidence is not None, "evidence": evidence}
        yield capability, {"mechanism": capability, "hosts": hosts}


def scan() -> dict:
    """{mechanism: {"mechanism": str, "hosts": {host: {wired, evidence}}}}."""
    return dict(scan_iter())


def scan_host_conditional_branches() -> list[dict]:
    """Every line in the scanned tree that structurally branches on host
    identity — the broader "every host-conditional branch" inventory item 1
    asks for, alongside the four-capability graph above."""
    hits: list[dict] = []
    paths = _iter_py_files()
    if HOOKS_JSON_PATH.exists():
        paths = paths + [HOOKS_JSON_PATH]
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        code_lines = lines if path.suffix != ".py" else _code_only_lines(path, lines)
        for i, (line, code_line) in enumerate(zip(lines, code_lines), start=1):
            if any(p.search(code_line) for p in _BRANCH_PATTERNS):
                rel = path.relative_to(REPO_ROOT)
                hits.append({"file": str(rel), "line": i, "text": line.strip()})
    return hits


def _atomic_write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    staged.replace(path)


def main() -> None:
    out_dir = REPO_ROOT / "state" / "verification-contracts"
    graph_path = out_dir / "host-inventory-graph.json"
    branches_path = out_dir / "host-conditional-branches.json"

    graph: dict[str, dict] = {}
    for mechanism, entry in scan_iter():
        graph[mechanism] = entry
        _atomic_write(graph_path, graph)  # live: a viewer sees partial progress mid-scan

    _atomic_write(branches_path, scan_host_conditional_branches())

    print(json.dumps(graph, indent=2, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main() or 0)
