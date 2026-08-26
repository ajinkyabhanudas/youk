"""
Tests for inline overengineering detection in route_task (Change 4).

Verifies that scope-expanding language in the task description sets
overengineering_flag=True and populates overengineering_note, without
blocking or changing the size/skills routing.
"""
from __future__ import annotations

from pathlib import Path


from routing import route_task as _routing_route_task


ROUTES_FILE = Path(__file__).parent.parent / "config" / "routes.yaml"


def _route(task: str, size_override: str = "M") -> dict:
    """Run route_task with a minimal intent brief that forces a specific size."""
    intent_brief = {
        "ambiguity_detected": False,
        "estimated_size": size_override,
        "goal_translation": {},
    }
    decision = _routing_route_task(task, skills_already_invoked=[], intent_brief=intent_brief, slug="")
    return decision.to_dict()


class TestOverengineeringFlag:
    def test_flag_set_for_extensible_task(self):
        result = _route("build an extensible plugin system for skill loading", "M")
        assert result["overengineering_flag"] is True
        assert result["overengineering_note"] is not None
        assert "extensible" in result["overengineering_note"]

    def test_flag_set_for_pluggable_task(self):
        result = _route("create a pluggable auth middleware", "M")
        assert result["overengineering_flag"] is True

    def test_flag_set_for_generic_task(self):
        result = _route("write a generic retry handler for all future api calls", "L")
        assert result["overengineering_flag"] is True

    def test_flag_not_set_for_plain_task(self):
        result = _route("fix the session_start breadcrumb path bug", "S")
        assert result["overengineering_flag"] is False
        assert "overengineering_note" not in result

    def test_flag_not_set_for_xs_tasks(self):
        result = _route("rename variable extensible_config to config", "XS")
        assert result["overengineering_flag"] is False

    def test_flag_not_set_for_s_tasks(self):
        # overengineering flag only fires for M+
        result = _route("add extensible field to the response dict", "S")
        assert result["overengineering_flag"] is False

    def test_note_contains_abc_approval_instruction(self):
        result = _route("build a scalable multi-tenant caching layer", "M")
        assert result["overengineering_flag"] is True
        note = result["overengineering_note"]
        assert "A" in note and "B" in note and "C" in note

    def test_flag_does_not_change_size(self):
        result = _route("add a flexible configuration system", "M")
        assert result["size"] == "M"

    def test_flag_does_not_block(self):
        result = _route("build a reusable graph traversal framework", "L")
        assert result["blocked"] is False

    def test_multiple_terms_listed_in_note(self):
        result = _route("design a pluggable extensible modular auth system", "M")
        assert result["overengineering_flag"] is True
        # note should mention at least one of the matched terms
        note = result["overengineering_note"]
        assert any(t in note for t in ("pluggable", "extensible", "modular"))


class TestIntakeGateInCLAUDEMd:
    """Structural test: check_intake_gate appears in the CLAUDE.md gate sequence."""

    def test_intake_gate_in_hard_rules(self):
        claude_md = Path(__file__).parent.parent / "docs" / "claude-md-template.md"
        content = claude_md.read_text()
        assert "check_intake_gate=unblocked" in content, (
            "check_intake_gate must be listed in the M+ hard rules in docs/claude-md-template.md"
        )

    def test_intake_gate_in_routing_steps(self):
        claude_md = Path(__file__).parent.parent / "docs" / "claude-md-template.md"
        content = claude_md.read_text()
        assert "check_intake_gate(task, size, intake_required=true)" in content, (
            "check_intake_gate call must appear in the task routing steps"
        )

    def test_overengineering_flag_in_routing_steps(self):
        claude_md = Path(__file__).parent.parent / "docs" / "claude-md-template.md"
        content = claude_md.read_text()
        assert "overengineering_flag" in content, (
            "overengineering_flag must appear in the task routing steps (step 4b)"
        )
