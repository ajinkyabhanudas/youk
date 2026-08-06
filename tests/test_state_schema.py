"""Tests for the state-store-rework validation layer (Task 1, sub-task 1.1).

Governed by ADR-009: dataclasses, raise-on-malformed, no coercion. The load-bearing
tests here are the ones that would have caught the bugs that motivated the whole task:
  - a malformed write RAISES instead of silently persisting (recursive-Resume)
  - a project-ambiguous active_task (empty slug) is rejected
  - validation runs on READ (from_dict), not only on write
  - the seam registry lists every mutable-claim file

These are exit-1 assertions: a regression that reintroduces silent coercion fails CI.
"""
from __future__ import annotations

import pytest

from state_schema import (
    MUTABLE_CLAIM_SCHEMAS,
    ActiveTask,
    GateFlag,
    PendingAction,
    ResumePointer,
    SessionPlan,
    StateValidationError,
)


# --- the bug this task exists to kill: recursive wrapping --------------------


def test_resume_pointer_rejects_recursive_wrapping():
    """The exact corruption class: 'Resume: Resume: Resume: ...'."""
    with pytest.raises(StateValidationError, match="recursively wrapped"):
        ResumePointer(slug="youk", text="Resume: Resume: Resume: Last working on: x")


def test_resume_pointer_rejects_recursive_last_working_on():
    with pytest.raises(StateValidationError, match="recursively wrapped"):
        ResumePointer(
            slug="youk",
            text="Last working on: Last working on: Last working on: something",
        )


def test_resume_pointer_accepts_clean_text():
    p = ResumePointer(slug="youk", text="NEXT = Task 1 feat/state-store-rework")
    assert p.to_dict()["text"].startswith("NEXT")


def test_session_plan_item_rejects_recursive_wrapping():
    with pytest.raises(StateValidationError, match=r"plan\[1\]"):
        SessionPlan(
            plan=["clean item", "Resume: Resume: Resume: corrupted"],
            slug="youk",
        )


# --- project-ambiguity: empty slug must be rejected -------------------------


def test_active_task_rejects_empty_slug():
    """The fused-task bug: active_task must always name its project."""
    with pytest.raises(StateValidationError, match="slug"):
        ActiveTask(task="do a thing", slug="")


def test_active_task_rejects_empty_task():
    with pytest.raises(StateValidationError, match="task"):
        ActiveTask(task="   ", slug="youk")


def test_gate_flag_requires_slug():
    """A gate cleared in one project must not satisfy another's gate."""
    with pytest.raises(StateValidationError, match="slug"):
        GateFlag(slug="")


# --- no coercion: wrong types RAISE, never silently convert ------------------


def test_no_coercion_on_wrong_type():
    """ADR-009: raise, don't coerce. A dict where a str belongs must raise."""
    with pytest.raises(StateValidationError):
        ActiveTask(task={"not": "a string"}, slug="youk")


def test_files_touched_must_be_list_of_str():
    with pytest.raises(StateValidationError, match="files_touched"):
        ActiveTask(task="t", slug="youk", files_touched=[1, 2, 3])


def test_routing_context_must_be_dict():
    with pytest.raises(StateValidationError, match="routing_context"):
        ActiveTask(task="t", slug="youk", routing_context="not a dict")


# --- validation runs on READ, not only write --------------------------------


def test_from_dict_validates_on_read():
    """A corrupt file on disk is caught when read, not trusted blindly."""
    corrupt = {"plan": ["Resume: Resume: Resume: x"], "slug": "youk"}
    with pytest.raises(StateValidationError):
        SessionPlan.from_dict(corrupt)


def test_from_dict_rejects_non_object():
    with pytest.raises(StateValidationError, match="JSON object"):
        ActiveTask.from_dict(["not", "a", "dict"])


# --- round-trip integrity ---------------------------------------------------


def test_active_task_round_trips():
    original = ActiveTask(
        task="build the store",
        slug="youk",
        files_touched=["a.py"],
        routing_context={"size": "XL"},
    )
    restored = ActiveTask.from_dict(original.to_dict())
    assert restored == original


def test_pending_action_round_trips():
    original = PendingAction(action="learn", reason="close_cluster_missed")
    restored = PendingAction.from_dict(original.to_dict())
    assert restored == original


def test_pending_action_requires_action():
    with pytest.raises(StateValidationError, match="action"):
        PendingAction(action="")


# --- the seam registry (sub-task 1.5 depends on this) -----------------------


def test_seam_registry_covers_known_mutable_claim_files():
    """Every mutable-claim file must be registered with a schema. This is the
    boundary the seam test (1.5) enforces machine-checked in CI."""
    expected = {
        "active_task.json",
        "session-plan.json",
        "pending-action.json",
        "challenge-ran.json",
        "challenge-gate-passed.json",
        "nfr-check-ran.json",
        "route-task-ran.json",
        "intake-ran.json",
    }
    assert expected <= set(MUTABLE_CLAIM_SCHEMAS)


def test_seam_registry_values_are_schema_types():
    """Every registered schema must support the read/write round-trip contract."""
    for name, schema in MUTABLE_CLAIM_SCHEMAS.items():
        assert hasattr(schema, "from_dict"), f"{name} schema needs from_dict"
        assert hasattr(schema, "to_dict"), f"{name} schema needs to_dict"
