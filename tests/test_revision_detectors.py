"""LEARN/UNLEARN detectors (Task 2) — propose grow/prune candidates from signals."""
from __future__ import annotations

import pytest

from revisable_sets import enroll
from revision_detectors import detect_grow_candidates, detect_prune_candidates


@pytest.fixture
def reg(tmp_path):
    p = tmp_path / "revisable-sets.json"
    enroll("_SEVEN_CONVERGENCE", "both",
           ["structural", "operational", "semantic"], path=p)
    return p


# ── LEARN (grow) ───────────────────────────────────────────────────────────

def test_recurring_gap_becomes_grow_candidate(reg):
    gaps = ["ethical", "ethical", "structural"]  # ethical recurs, structural exists
    candidates = detect_grow_candidates("_SEVEN_CONVERGENCE", gaps, path=reg)
    assert any(c["element"] == "ethical" for c in candidates)
    # structural already an element -> not proposed
    assert not any(c["element"] == "structural" for c in candidates)


def test_single_occurrence_not_proposed(reg):
    gaps = ["ethical"]  # only once -> below threshold
    candidates = detect_grow_candidates("_SEVEN_CONVERGENCE", gaps, path=reg)
    assert candidates == []


def test_grow_candidates_ranked_by_recurrence(reg):
    gaps = ["a", "a", "b", "b", "b"]
    candidates = detect_grow_candidates("_SEVEN_CONVERGENCE", gaps, path=reg)
    assert candidates[0]["element"] == "b"  # 3 > 2


def test_grow_on_unenrolled_set_returns_empty(reg):
    assert detect_grow_candidates("_NOT_ENROLLED", ["x", "x"], path=reg) == []


# ── UNLEARN (prune) ────────────────────────────────────────────────────────

def test_never_fired_element_becomes_prune_candidate(reg):
    fire_counts = {"structural": 5, "operational": 3, "semantic": 0}
    candidates = detect_prune_candidates("_SEVEN_CONVERGENCE", fire_counts, path=reg)
    assert any(c["element"] == "semantic" and c["driver"] == "never_fired" for c in candidates)


def test_corrected_element_becomes_prune_candidate(reg):
    fire_counts = {"structural": 5, "operational": 3, "semantic": 2}
    candidates = detect_prune_candidates(
        "_SEVEN_CONVERGENCE", fire_counts, corrected=["operational"], path=reg)
    assert any(c["element"] == "operational" and c["driver"] == "repeatedly_corrected"
               for c in candidates)


def test_prune_never_proposes_all_elements(reg):
    # every element dead -> still leaves one
    fire_counts = {"structural": 0, "operational": 0, "semantic": 0}
    candidates = detect_prune_candidates("_SEVEN_CONVERGENCE", fire_counts, path=reg)
    assert len(candidates) < 3  # not all three


def test_active_element_not_pruned(reg):
    fire_counts = {"structural": 5, "operational": 3, "semantic": 2}
    candidates = detect_prune_candidates("_SEVEN_CONVERGENCE", fire_counts, path=reg)
    assert candidates == []  # all fired, none corrected
