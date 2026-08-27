"""Drift sentinel for the total=False output-schema null bug.

RouteTaskResult is a `TypedDict, total=False`. FastMCP generates a JSON Schema where
every field carries `"default": null` while keeping a NON-nullable `"type"`. Any field
the implementation omits is default-filled with null by the output validator and then
fails its own type check, so route_task returns:

    Output validation error: None is not of type 'array'

This broke route_task for every task that did not contain a steering quality label,
which is nearly all of them. The fix is that every DECLARED field must always be
present in the returned dict, using an empty value ([] / {} / "") as the empty signal.

These tests fail if a future change makes a declared field conditional again, or adds
a declared field without populating it.
"""
from __future__ import annotations

from models import RoutingDecision, TaskSize
from schemas import RouteTaskResult


# Fields populated in server.py's route_task body rather than by to_dict() or
# enrich_route_result(). server.py cannot be imported here because it requires the
# `mcp` package, so they are asserted by name instead of by execution.
_SERVER_POPULATED = {"calls_since_compact", "steering_context"}


def _decision(**kw) -> RoutingDecision:
    base = dict(
        task="example task",
        size=TaskSize.M,
        ceremony="full",
        skills=["nfr_check"],
        nfr_mode="full",
    )
    base.update(kw)
    return RoutingDecision(**base)


class TestToDictAlwaysPopulatesDeclaredFields:
    def test_collapsing_question_present_when_empty(self):
        d = _decision().to_dict()
        assert "collapsing_question" in d
        assert d["collapsing_question"] == ""

    def test_collapsing_question_present_when_set(self):
        d = _decision(blocked=True, collapsing_question="Which surface?").to_dict()
        assert d["collapsing_question"] == "Which surface?"

    def test_no_declared_field_is_none(self):
        d = _decision().to_dict()
        nulls = [k for k, v in d.items() if v is None]
        assert nulls == [], f"null values fail non-nullable schema types: {nulls}"

    def test_list_fields_are_lists_not_none(self):
        d = _decision(skills=[], warnings=[]).to_dict()
        assert isinstance(d["skills"], list)
        assert isinstance(d["warnings"], list)


class TestEnrichAlwaysPopulatesDeclaredFields:
    def test_file_context_and_graph_state_always_set(self):
        from session import enrich_route_result

        result: dict = {}
        enrich_route_result(result, "some unmatched query string")
        assert "file_context" in result
        assert isinstance(result["file_context"], list)
        assert "graph_state" in result
        assert isinstance(result["graph_state"], dict)

    def test_enrich_sets_no_none_values(self):
        from session import enrich_route_result

        result: dict = {}
        enrich_route_result(result, "another unmatched query")
        nulls = [k for k, v in result.items() if v is None]
        assert nulls == [], f"null values fail non-nullable schema types: {nulls}"


class TestDeclaredFieldCoverage:
    """The actual drift sentinel: every declared field must be populated somewhere."""

    def test_every_declared_field_is_accounted_for(self):
        from session import enrich_route_result

        result = _decision().to_dict()
        enrich_route_result(result, "coverage probe")

        declared = set(RouteTaskResult.__annotations__)
        produced = set(result)
        unaccounted = declared - produced - _SERVER_POPULATED

        assert unaccounted == set(), (
            "RouteTaskResult declares fields that nothing populates: "
            f"{sorted(unaccounted)}. A total=False TypedDict default-fills omitted "
            "fields with null, which then fails their non-nullable schema type. "
            "Populate each with an empty value, or add it to _SERVER_POPULATED if "
            "server.py sets it unconditionally."
        )

    def test_server_populated_names_are_still_declared(self):
        """Guards against _SERVER_POPULATED drifting out of sync with the schema."""
        declared = set(RouteTaskResult.__annotations__)
        stale = _SERVER_POPULATED - declared
        assert stale == set(), f"_SERVER_POPULATED lists undeclared fields: {sorted(stale)}"
