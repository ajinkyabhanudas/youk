"""Tests for sizing_decision.py: the real record route_task now logs every
call to, and the retrieval half that grounds a future judgment in real
precedent instead of a cold guess.
"""
from __future__ import annotations

import pytest

from sizing_decision import (
    SizingDecision,
    SizingDecisionValidationError,
    log_sizing_decision,
    find_similar_sizing_precedents,
)


def _valid_kwargs(**overrides) -> dict:
    kwargs = dict(
        id="sz-1",
        task="fix the login bug",
        deterministic_size="S",
        llm_estimated_size="",
        resolved_size="S",
        mismatch_flag=False,
        timestamp="2026-10-04T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return kwargs


def test_valid_decision_constructs():
    decision = SizingDecision(**_valid_kwargs())
    assert decision.resolved_size == "S"


def test_invalid_size_raises():
    with pytest.raises(SizingDecisionValidationError, match="deterministic_size"):
        SizingDecision(**_valid_kwargs(deterministic_size="HUGE"))


def test_empty_task_raises():
    with pytest.raises(SizingDecisionValidationError, match="task"):
        SizingDecision(**_valid_kwargs(task=""))


def test_mismatch_flag_rejects_non_bool():
    with pytest.raises(SizingDecisionValidationError, match="mismatch_flag"):
        SizingDecision(**_valid_kwargs(mismatch_flag="yes"))


def test_log_sizing_decision_writes_a_real_entry(tmp_path):
    log_path = tmp_path / "sizing.jsonl"
    decision = log_sizing_decision(
        task="implement new feature",
        deterministic_size="M",
        llm_estimated_size="M",
        resolved_size="M",
        mismatch_flag=False,
        log_path=log_path,
    )
    assert log_path.exists()
    assert decision.resolved_size == "M"


def test_find_similar_sizing_precedents_returns_empty_with_no_history(tmp_path):
    assert find_similar_sizing_precedents("anything", log_path=tmp_path / "none.jsonl") == []


def test_find_similar_sizing_precedents_ranks_the_real_closest_match(tmp_path):
    log_path = tmp_path / "sizing.jsonl"
    log_sizing_decision(
        task="fix a typo in the README",
        deterministic_size="XS", llm_estimated_size="XS", resolved_size="XS",
        mismatch_flag=False, log_path=log_path,
    )
    log_sizing_decision(
        task="design a new architecture for the payment system",
        deterministic_size="L", llm_estimated_size="L", resolved_size="L",
        mismatch_flag=False, log_path=log_path,
    )
    results = find_similar_sizing_precedents(
        "redesign the architecture for the billing system", limit=1, log_path=log_path,
    )
    assert len(results) == 1
    assert results[0]["resolved_size"] == "L"
