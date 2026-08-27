"""Executable contract tests for registered MCP tools.

The gap this closes: youk had two mechanisms that looked like contract coverage and
were not. `verify_mcp_contracts` compares tool signatures to call sites, and
test_tool_contract_sentinel checks that the documentation template has the required
headings. Neither executes a tool or inspects real output, so route_task returned
schema-invalid output on nearly every call and both stayed green.

The failure was not in validation. FastMCP's convert_result accepted the dict; the
nulls appeared when pydantic serialized the declared-but-absent fields into
structuredContent, and the client rejected them against their own non-nullable types.
So these tests assert on what convert_result EMITS, which is the stage that actually
broke.

Scope is deliberately narrow. Only read-only tools are executed, against a tmp root,
because running the full gate chain would mutate the audit log and task graph that
youk's own health score reads from. That was a BLOCKING objection when this work was
challenged, and it is the reason this is not an end-to-end harness.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# server.py imports mcp.server.fastmcp specifically. Guarding on the top-level `mcp`
# package is not enough: mcp 2.x installs cleanly, renames FastMCP to MCPServer, and
# then every test here errors on import instead of skipping. Guard the exact module
# the code under test uses, not its parent package.
pytest.importorskip(
    "mcp.server.fastmcp",
    reason="mcp<2 with the FastMCP API not installed — CI installs it",
)


@pytest.fixture(autouse=True)
def _isolate_roots(tmp_path, monkeypatch):
    """Redirect every module-level YOUK_ROOT / CLAUDE_ROOT at a tmp directory.

    Not optional. route_task writes route-task-ran.json, active_task.json and a task
    graph node, so executing it against the real roots pollutes the audit and graph
    data that youk's own health score reads from. That was the BLOCKING objection when
    this work was challenged, and stating the constraint in an NFR block is not the
    same as implementing it: the first version of this file asserted tmp isolation and
    then ran against /youk, which is how CI caught it with a PermissionError.

    Patched by scanning loaded modules rather than naming them, because the roots are
    module-level constants duplicated across server, session, health, intent and
    state_paths, and a hardcoded list silently misses whichever one is added next.
    """
    import sys

    youk_root = tmp_path / "youk"
    claude_root = tmp_path / "claude"
    for sub in ("state", "knowledge/projects", "knowledge/proposals", "docs", "config"):
        (youk_root / sub).mkdir(parents=True, exist_ok=True)
    (claude_root / "skills").mkdir(parents=True, exist_ok=True)
    (claude_root / "audit").mkdir(parents=True, exist_ok=True)

    # Import everything the tools reach for BEFORE scanning. Several modules are
    # imported lazily inside functions, so they are absent from sys.modules when the
    # fixture runs and their path constants escape redirection. challenge_gate did
    # exactly that and kept writing revisable-sets.json into the real state dir.
    import server  # noqa: F401
    for _lazy in ("challenge_gate", "revisable_sets", "graph", "file_index",
                  "steering_vocab", "knowledge_index", "state_paths", "session",
                  "health", "intent", "observability"):
        try:
            __import__(_lazy)
        except Exception:
            pass

    # Patching the roots alone is not enough. Modules also derive constants from them
    # at import time, e.g. server._TOOL_CALL_COUNT_FILE = YOUK_ROOT / "state" / ...,
    # which is already baked by the time a fixture runs. Rewrite every module-level
    # Path that sits under a real root, not just the roots themselves.
    real = ((Path("/youk"), youk_root), (Path("/claude"), claude_root))

    def _redirect(value: Path) -> Path | None:
        for original, replacement in real:
            try:
                return replacement / value.relative_to(original)
            except ValueError:
                continue
        return None

    for mod in list(sys.modules.values()):
        if mod is None or not getattr(mod, "__name__", "").isidentifier():
            continue
        for attr in list(vars(mod)) if hasattr(mod, "__dict__") else []:
            try:
                current = getattr(mod, attr)
            except Exception:
                continue
            if not isinstance(current, Path):
                continue
            replacement = _redirect(current)
            if replacement is not None:
                replacement.parent.mkdir(parents=True, exist_ok=True)
                monkeypatch.setattr(mod, attr, replacement, raising=False)

    # Path defaults bound at def time, e.g. `def _save(reg, path=_REGISTRY_FILE)`.
    # Patching the module attribute cannot reach these: the default was captured when
    # the function was defined. 21 such bindings exist across revisable_sets,
    # behavioral_profile, skill_signals and steering_vocab, so rewriting __defaults__
    # is the only isolation that covers them without editing every signature.
    import types
    for mod in list(sys.modules.values()):
        if mod is None or not getattr(mod, "__name__", "").isidentifier():
            continue
        for fn in list(vars(mod).values()) if hasattr(mod, "__dict__") else []:
            if not isinstance(fn, types.FunctionType) or not fn.__defaults__:
                continue
            new_defaults = []
            changed = False
            for d in fn.__defaults__:
                repl = _redirect(d) if isinstance(d, Path) else None
                if repl is not None:
                    repl.parent.mkdir(parents=True, exist_ok=True)
                    new_defaults.append(repl)
                    changed = True
                else:
                    new_defaults.append(d)
            if changed:
                monkeypatch.setattr(fn, "__defaults__", tuple(new_defaults), raising=False)
    yield


def _core_server():
    import server as _s
    return _s


def _tool(name: str):
    return _core_server().mcp._tool_manager.get_tool(name)


def _structured(tool, result: dict) -> dict:
    """Return what FastMCP would actually put on the wire for this result."""
    out = tool.fn_metadata.convert_result(result)
    return out[1] if isinstance(out, tuple) and len(out) > 1 else out


# Tools that are safe to execute: no writes outside state youk already owns, no
# network, no destructive effects. Adding a tool here means asserting it is read-only.
_READ_ONLY_TOOLS = ["route_task", "check_command", "is_unblocked"]


class TestDeclaredFieldsNeverSerializeAsNull:
    """The route_task regression, generalized to every tool.

    A total=False TypedDict return gives every field default=None with a non-nullable
    type. Any field the implementation omits is emitted as an explicit null and fails
    its own declared type on the client.
    """

    @pytest.mark.parametrize("tool_name", _READ_ONLY_TOOLS)
    def test_no_declared_field_serializes_as_null(self, tool_name):
        tool = _tool(tool_name)
        if not getattr(tool, "output_schema", None):
            pytest.skip(f"{tool_name} declares no output schema")

        fn = tool.fn
        result = fn("probe task for contract test") if tool_name != "is_unblocked" else fn("probe")
        structured = _structured(tool, result)

        nulls = sorted(k for k, v in structured.items() if v is None)
        assert nulls == [], (
            f"{tool_name} emits null for declared field(s) {nulls}. "
            "A total=False TypedDict default-fills omitted fields with null, which then "
            "fails the field's own non-nullable schema type on the client. Populate each "
            "with an empty value ([] / {} / '')."
        )

    def test_route_task_specifically_populates_the_regressed_fields(self):
        """Named regression guard for the three fields that actually broke."""
        tool = _tool("route_task")
        structured = _structured(tool, tool.fn("fix a typo in the readme"))
        for field in ("steering_context", "collapsing_question", "graph_state"):
            assert field in structured, f"{field} missing from structuredContent"
            assert structured[field] is not None, f"{field} serialized as null"


class TestOutputSchemaShape:
    """Guards the schema-generation assumption these tests rely on."""

    def test_total_false_typeddict_yields_nullable_defaults(self):
        """Documents WHY the tests above exist.

        If FastMCP ever stops emitting `default: null` for optional fields, the whole
        bug class disappears and these tests become redundant rather than wrong. This
        test failing is the signal to re-read that assumption, not to patch around it.
        """
        schema = _tool("route_task").output_schema
        props = schema.get("properties", {})
        optional_with_null_default = [
            k for k, v in props.items()
            if v.get("default", "_sentinel") is None and v.get("type") != "null"
        ]
        assert optional_with_null_default, (
            "No field carries a null default with a non-nullable type. The bug class "
            "these tests guard may no longer exist — re-read the assumption."
        )

    def test_at_least_one_read_only_tool_declares_a_schema(self):
        """Guards against the null tests silently covering nothing.

        A tool returning a bare dict declares no schema, so it has no declared fields
        to default-fill and cannot exhibit this bug. That is weaker typing, not this
        bug, so it is not asserted here. What must not happen is every tool skipping,
        which would leave the parametrized tests green while testing nothing.
        """
        with_schema = [n for n in _READ_ONLY_TOOLS if getattr(_tool(n), "output_schema", None)]
        assert with_schema, (
            "no read-only tool declares an output schema, so every null test skipped "
            "and this file proves nothing"
        )


class TestIsolationActuallyHolds:
    """Proves the tmp-root fixture works, rather than trusting the docstring.

    The previous version of this file claimed tmp isolation in prose while executing
    against the real roots. A claim in a comment is not isolation.
    """

    def test_roots_point_at_tmp(self, tmp_path):
        import server
        assert str(server.YOUK_ROOT).startswith(str(tmp_path))
        assert str(server.CLAUDE_ROOT).startswith(str(tmp_path))

    def test_derived_path_constants_are_redirected_too(self, tmp_path):
        """The case that escaped the first fix.

        _TOOL_CALL_COUNT_FILE is computed from YOUK_ROOT at import time, so patching
        the root afterwards leaves it pointing at the real path. CI caught it as a
        FileNotFoundError on /youk/state/tool-call-count.json.
        """
        import server
        assert str(server._TOOL_CALL_COUNT_FILE).startswith(str(tmp_path))

    def test_no_module_level_path_still_points_at_a_real_root(self, tmp_path):
        """Sweeps for any Path constant the fixture missed."""
        import sys
        escaped = []
        for mod in list(sys.modules.values()):
            name = getattr(mod, "__name__", "")
            if mod is None or not name.isidentifier() or not hasattr(mod, "__dict__"):
                continue
            for attr, value in list(vars(mod).items()):
                if isinstance(value, Path) and str(value).startswith(("/youk", "/claude")):
                    escaped.append(f"{name}.{attr} = {value}")
        assert escaped == [], f"paths still resolving to real roots: {escaped}"

    def test_executing_a_tool_writes_only_under_tmp(self, tmp_path):
        """route_task has write side effects; they must all land in tmp."""
        import server
        _tool("route_task").fn("probe task for isolation check")
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert written, "route_task wrote nothing — the write path may not have run"
        assert all(str(p).startswith(str(tmp_path)) for p in written)
        assert str(server.YOUK_ROOT) != "/youk"


class TestToolRegistration:
    def test_all_registered_tools_are_callable(self):
        """A registered tool with no callable fn is a broken registration."""
        mgr = _core_server().mcp._tool_manager
        names = list(getattr(mgr, "_tools", {}))
        assert names, "no tools registered on youk-core"
        broken = [n for n in names if not callable(getattr(mgr.get_tool(n), "fn", None))]
        assert broken == [], f"registered but not callable: {broken}"

    def test_read_only_tool_list_matches_registered_names(self):
        """Catches a rename that would silently drop a tool from coverage."""
        mgr = _core_server().mcp._tool_manager
        registered = set(getattr(mgr, "_tools", {}))
        missing = [n for n in _READ_ONLY_TOOLS if n not in registered]
        assert missing == [], f"_READ_ONLY_TOOLS names no longer registered: {missing}"
