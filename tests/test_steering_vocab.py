"""Steering vocabulary (Task 3) — youk learns behavior decompositions of quality labels,
tagged by confidence, filtered at read time.

Load-bearing properties:
- Nothing is rejected at write time (vocab fills fast — no cold-start starvation).
- Strictness is a READ-TIME weight (the tunable knob), not a write-time gate.
- A correction is a veto (weight → 0), always winning over prior positive signal.
- An unlearned label returns learned=False so the caller elicits fresh, not a stereotype.
"""
from __future__ import annotations

import pytest

from steering_vocab import get_steering, record_decomposition


@pytest.fixture
def vf(tmp_path):
    return tmp_path / "steering-vocab.json"


def test_records_and_reads_back(vf):
    record_decomposition("rigorous", "trace the failure class not the instance",
                          "code review", confidence="verified", path=vf)
    result = get_steering("rigorous", path=vf)
    assert result["learned"]
    assert result["behaviors"][0]["behavior"] == "trace the failure class not the instance"
    assert result["behaviors"][0]["confidence"] == "verified"


def test_verified_outweighs_approved(vf):
    record_decomposition("rigorous", "A", "ctx", confidence="approved", path=vf)
    record_decomposition("rigorous", "B", "ctx", confidence="verified", path=vf)
    behaviors = get_steering("rigorous", path=vf)["behaviors"]
    # verified B ranks above approved A
    assert behaviors[0]["behavior"] == "B"
    assert behaviors[0]["weight"] > behaviors[1]["weight"]


def test_confidence_upgrades_to_strongest(vf):
    record_decomposition("thorough", "check edges", "ctx", confidence="approved", path=vf)
    record_decomposition("thorough", "check edges", "ctx2", confidence="verified", path=vf)
    b = get_steering("thorough", path=vf)["behaviors"][0]
    assert b["confidence"] == "verified"   # upgraded
    assert b["count"] == 2                  # observed twice


def test_correction_is_a_veto(vf):
    record_decomposition("elite", "over-engineer everything", "ctx", confidence="verified", path=vf)
    # user corrects this decomposition — it must drop out of steering
    record_decomposition("elite", "over-engineer everything", "ctx", confidence="corrected", path=vf)
    result = get_steering("elite", path=vf)
    assert result["learned"] is False   # corrected -> weight 0 -> excluded
    assert result["behaviors"] == []


def test_unlearned_label_returns_not_learned(vf):
    result = get_steering("never_seen", path=vf)
    assert result["learned"] is False
    assert result["behaviors"] == []


def test_nothing_rejected_at_write_time(vf):
    # even a purely-approved (unverified) decomposition is recorded and usable
    r = record_decomposition("principal", "own the decision surface", "ctx",
                             confidence="approved", path=vf)
    assert r["ok"]
    assert get_steering("principal", path=vf)["learned"]


def test_repeat_observations_strengthen_weight(vf):
    record_decomposition("x", "b1", "c1", confidence="verified", path=vf)
    w1 = get_steering("x", path=vf)["behaviors"][0]["weight"]
    for i in range(3):
        record_decomposition("x", "b1", f"c{i}", confidence="verified", path=vf)
    w2 = get_steering("x", path=vf)["behaviors"][0]["weight"]
    assert w2 > w1   # more observations -> higher weight


def test_invalid_confidence_rejected(vf):
    r = record_decomposition("x", "b", "c", confidence="maybe", path=vf)
    assert not r["ok"]


def test_strictness_knob_is_read_time(vf):
    """The same recorded data yields different steering under different min_weight — proving
    strictness is applied at read, not baked into what's stored."""
    record_decomposition("q", "approved-behavior", "c", confidence="approved", path=vf)
    lenient = get_steering("q", path=vf, min_weight=0.1)   # 0.4 weight passes
    strict = get_steering("q", path=vf, min_weight=0.5)    # 0.4 weight excluded
    assert lenient["learned"] is True
    assert strict["learned"] is False
    # data unchanged — only the read filter differs
