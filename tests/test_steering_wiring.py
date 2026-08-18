"""Steering-loop wiring tests — route_task attaches learned steering context.

Load-bearing properties verified:
- steering_context present when a known quality label with learned decompositions is in the task
- steering_context absent (not an empty list, just missing) when no quality label in the task
- steering_context absent when label is present but has no learned decompositions (cold-start honest)
- correction-vetoed labels do not surface in steering_context (weight-0 excluded)
- record_steering_decomposition → get_steering round-trip (the update path callers use post-task)
"""
from __future__ import annotations

import pytest

from steering_vocab import get_steering, record_decomposition


@pytest.fixture
def vf(tmp_path):
    return tmp_path / "steering-vocab.json"


# ── Simulate the label-detection + _get_steering logic from server.py's route_task ──
# Extracted here so we can unit-test the wiring without importing the full MCP server.

_QUALITY_LABELS = {
    "rigorous", "thorough", "careful", "elite", "principal", "l9", "l10",
    "exhaustive", "skeptical", "adversarial", "precise",
}


def _extract_steering_context(task: str, vocab_path) -> list[dict]:
    """Mirror of the steering-context extraction logic in server.py route_task."""
    task_words = set(task.lower().split())
    result = []
    for label in _QUALITY_LABELS & task_words:
        sv = get_steering(label, path=vocab_path)
        if sv.get("learned"):
            result.append(sv)
    return result


class TestSteeringContextAttachment:
    def test_learned_label_in_task_attaches_context(self, vf):
        record_decomposition("rigorous", "trace the failure class", "ctx",
                             confidence="verified", path=vf)
        ctx = _extract_steering_context("do a rigorous code review", vf)
        assert len(ctx) == 1
        assert ctx[0]["label"] == "rigorous"
        assert ctx[0]["learned"] is True
        assert ctx[0]["behaviors"][0]["behavior"] == "trace the failure class"

    def test_no_quality_label_yields_no_context(self, vf):
        ctx = _extract_steering_context("fix the broken import in routing.py", vf)
        assert ctx == []

    def test_cold_label_not_in_context(self, vf):
        # "thorough" is a known quality label but nothing has been recorded for it
        ctx = _extract_steering_context("do a thorough review", vf)
        assert ctx == []  # cold-start honest — not a stub, just absent

    def test_corrected_label_excluded_from_context(self, vf):
        record_decomposition("elite", "over-engineer everything", "ctx",
                             confidence="verified", path=vf)
        record_decomposition("elite", "over-engineer everything", "ctx",
                             confidence="corrected", path=vf)
        ctx = _extract_steering_context("build an elite system", vf)
        assert ctx == []  # corrected -> weight 0 -> learned=False -> not attached

    def test_multiple_labels_each_attach_independently(self, vf):
        record_decomposition("careful", "check invariants first", "ctx",
                             confidence="approved", path=vf)
        record_decomposition("precise", "name every assumption", "ctx",
                             confidence="verified", path=vf)
        ctx = _extract_steering_context("careful and precise implementation", vf)
        labels = {c["label"] for c in ctx}
        assert "careful" in labels
        assert "precise" in labels

    def test_case_insensitive_label_detection(self, vf):
        record_decomposition("thorough", "cover edge cases", "ctx",
                             confidence="verified", path=vf)
        # task has "thorough" in mixed case after split+lower — should match
        ctx = _extract_steering_context("write a THOROUGH test suite", vf)
        assert any(c["label"] == "thorough" for c in ctx)


class TestPostTaskRecordingRoundTrip:
    """Callers record decompositions after work completes — verify the update path."""

    def test_approved_confidence_recorded_and_readable(self, vf):
        record_decomposition("careful", "validate preconditions", "task-123",
                             confidence="approved", path=vf)
        sv = get_steering("careful", path=vf)
        assert sv["learned"] is True
        assert sv["behaviors"][0]["confidence"] == "approved"

    def test_verified_upgrades_prior_approved(self, vf):
        record_decomposition("skeptical", "demand evidence", "c1",
                             confidence="approved", path=vf)
        record_decomposition("skeptical", "demand evidence", "c2",
                             confidence="verified", path=vf)
        b = get_steering("skeptical", path=vf)["behaviors"][0]
        assert b["confidence"] == "verified"

    def test_corrected_after_verified_is_still_a_veto(self, vf):
        record_decomposition("precise", "never guess types", "c",
                             confidence="verified", path=vf)
        record_decomposition("precise", "never guess types", "c",
                             confidence="corrected", path=vf)
        sv = get_steering("precise", path=vf)
        assert sv["learned"] is False  # corrected always wins
