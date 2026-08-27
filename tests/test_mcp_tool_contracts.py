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

import pytest

# server.py needs the mcp package. Skip rather than error so a contributor without it
# still gets a green local run; CI installs mcp so the tests actually execute there.
pytest.importorskip("mcp", reason="mcp not installed — CI installs it")


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
