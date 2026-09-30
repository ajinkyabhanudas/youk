"""Tests for CIR-150 item 2 / CIR-151: the ESCALATE disposition and its real
call-site wiring into route_task.

CIR-150 found challenge Lens 1 and intake's GAP SYNTHESIS could both detect that
the stated problem is a symptom of something bigger, but nothing downstream acted
on that as a scope-widening event — task_contract.py's disposition vocabulary was
IN-SCOPE | DEFER | ACCEPT-RISK | N/A, with no ESCALATE option, and the one codified
rule in the area (challenge's ITERATE minimum-revision check) actively suppresses
widening, for a DIFFERENT case (revising a direction to fix an objection within its
existing scope).

This proves the real mechanism: write_scope_escalation persists a one-shot signal
that route_task's very next call for that slug cannot route below, closing the gap
between "a finding was made" and "the finding changed what gets built."
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def patch_routes(tmp_path, monkeypatch):
    routes = tmp_path / "config" / "routes.yaml"
    routes.parent.mkdir(parents=True)
    routes.write_text("""\
task_sizes:
  XS:
    signals: [typo]
    negative_signals: []
    ceremony: none
    skills: []
  S:
    signals: [hotfix]
    negative_signals: []
    ceremony: minimal
    skills: []
  M:
    signals: [feature, add]
    negative_signals: []
    ceremony: standard
    skills: [nfr_check, dev_loop]
  L:
    signals: [system]
    negative_signals: []
    ceremony: full
    skills: [nfr_check, write_spec, dev_loop]
  XL:
    signals: [platform]
    negative_signals: []
    ceremony: full
    skills: [nfr_check, write_spec, stress_test, dev_loop]
token_budgets:
  XS: 2000
  S: 5000
  M: 15000
  L: 40000
  XL: 80000
""")
    import routing
    monkeypatch.setattr(routing, "ROUTES_FILE", routes)
    monkeypatch.setattr(routing, "YOUK_ROOT", tmp_path / "youk")
    return tmp_path / "youk"


class TestWriteScopeEscalation:
    def test_valid_m_size_escalates(self):
        from routing import write_scope_escalation
        result = write_scope_escalation("myproj", "fix the login bug", "symptom of a deeper auth redesign", "M", "challenge_lens1")
        assert result["escalated"] is True
        assert result["suggested_size"] == "M"
        assert "route_task" in result["instruction"]

    def test_valid_l_and_xl_sizes_escalate(self):
        from routing import write_scope_escalation
        for size in ("L", "XL"):
            result = write_scope_escalation("myproj", "task", "reason", size, "intake_gap_synthesis")
            assert result["escalated"] is True
            assert result["suggested_size"] == size

    def test_xs_size_rejected(self):
        from routing import write_scope_escalation
        result = write_scope_escalation("myproj", "task", "reason", "XS", "challenge_lens1")
        assert result["escalated"] is False
        assert "M, L, or XL" in result["reason"]

    def test_s_size_rejected(self):
        from routing import write_scope_escalation
        result = write_scope_escalation("myproj", "task", "reason", "S", "challenge_lens1")
        assert result["escalated"] is False

    def test_invalid_size_string_rejected_not_crashed(self):
        from routing import write_scope_escalation
        result = write_scope_escalation("myproj", "task", "reason", "GIGANTIC", "challenge_lens1")
        assert result["escalated"] is False
        assert "invalid suggested_size" in result["reason"]

    def test_writes_the_slug_scoped_file(self, patch_routes):
        from routing import write_scope_escalation
        write_scope_escalation("myproj", "fix the login bug", "reason text", "L", "challenge_lens1")
        f = patch_routes / "state" / "sessions" / "myproj" / "scope-escalation.json"
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["suggested_size"] == "L"
        assert data["source"] == "challenge_lens1"
        assert data["consumed"] is False


class TestConsumeScopeEscalationIsOneShot:
    def test_first_consume_returns_the_size(self):
        from routing import write_scope_escalation, _consume_scope_escalation
        from models import TaskSize
        write_scope_escalation("myproj", "task", "reason", "L", "challenge_lens1")
        assert _consume_scope_escalation("myproj") == TaskSize.L

    def test_second_consume_returns_none(self):
        from routing import write_scope_escalation, _consume_scope_escalation
        write_scope_escalation("myproj", "task", "reason", "L", "challenge_lens1")
        _consume_scope_escalation("myproj")
        assert _consume_scope_escalation("myproj") is None

    def test_wrong_slug_returns_none(self):
        from routing import write_scope_escalation, _consume_scope_escalation
        write_scope_escalation("myproj", "task", "reason", "L", "challenge_lens1")
        assert _consume_scope_escalation("otherproj") is None

    def test_no_pending_escalation_returns_none(self):
        from routing import _consume_scope_escalation
        assert _consume_scope_escalation("myproj") is None


class TestRouteTaskAppliesEscalation:
    def test_escalation_raises_size_above_keyword_scoring(self):
        """'fix the typo' alone routes XS -- a pending L escalation must win."""
        from routing import route_task, write_scope_escalation
        write_scope_escalation("myproj", "fix the typo", "symptom of a deeper problem", "L", "challenge_lens1")
        result = route_task("fix the typo", slug="myproj")
        assert result.size.value == "L"
        assert result.scope_escalated is True
        assert "original problem framing was found to be wrong" in result.scope_escalation_reason

    def test_escalation_never_lowers_a_bigger_organic_size(self):
        """An M-scored task with a pending L escalation still ends at L (escalation
        applies), but an XL-scored task with a pending M escalation must NOT be
        lowered to M -- escalation only ever raises the floor."""
        from routing import route_task, write_scope_escalation
        write_scope_escalation("myproj", "big platform rewrite", "reason", "M", "challenge_lens1")
        result = route_task("big platform rewrite", slug="myproj")
        assert result.size.value == "XL"
        assert result.scope_escalated is False

    def test_no_pending_escalation_is_a_no_op(self):
        from routing import route_task
        result = route_task("fix the typo", slug="myproj")
        assert result.size.value == "XS"
        assert result.scope_escalated is False
        assert result.scope_escalation_reason == ""

    def test_escalation_is_consumed_after_one_route_task_call(self):
        """The next call this session escalates; the call after that does not --
        proves the one-shot contract holds through route_task itself, not just
        through the lower-level _consume_scope_escalation function."""
        from routing import route_task, write_scope_escalation
        write_scope_escalation("myproj", "fix the typo", "reason", "L", "challenge_lens1")
        first = route_task("fix the typo", slug="myproj")
        second = route_task("fix the typo", slug="myproj")
        assert first.size.value == "L"
        assert second.size.value == "XS"
        assert second.scope_escalated is False

    def test_to_dict_surfaces_the_new_fields(self):
        from routing import route_task, write_scope_escalation
        write_scope_escalation("myproj", "fix the typo", "reason", "L", "challenge_lens1")
        result = route_task("fix the typo", slug="myproj").to_dict()
        assert result["scope_escalated"] is True
        assert result["scope_escalation_reason"]
