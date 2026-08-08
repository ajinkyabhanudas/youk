"""Tests for confidence_signal — the layered glanceable cue.

Central guarantee under test: the FALSE-GREEN anti-pattern (a confidence number with no
basis) is impossible by construction. Plus: structural risk is monotonic in stakes, the
uncalibrated state is honest, and the forcing budget rations gates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from confidence_signal import (  # noqa: E402
    MIN_SAMPLES,
    Calibration,
    Familiarity,
    ForcingBudget,
    Reversibility,
    StructuralRisk,
    build_signal,
    warrants_forcing,
)


def _low_risk() -> StructuralRisk:
    return StructuralRisk(1, 0, Reversibility.TRIVIAL, Familiarity.OWNED)


def _high_risk() -> StructuralRisk:
    return StructuralRisk(12, 8, Reversibility.IRREVERSIBLE, Familiarity.NOVEL)


# --- structural risk ----------------------------------------------------------------------

def test_structural_risk_monotonic_in_stakes():
    assert _low_risk().score() < _high_risk().score()


def test_structural_risk_bounded_0_to_1():
    assert 0.0 <= _low_risk().score() <= 1.0
    assert 0.0 <= _high_risk().score() <= 1.0
    assert _high_risk().score() <= 1.0  # even extreme inputs cap at 1.0


def test_structural_risk_needs_no_api():
    # pure computation, no network — this is the day-1 layer
    assert isinstance(_high_risk().score(), float)


# --- false-green prevention (the load-bearing test) ---------------------------------------

def test_no_confidence_without_calibration():
    # No calibration data at all → signal MUST be uncalibrated, never a fabricated number.
    sig = build_signal(_low_risk(), calibration=None)
    assert sig.confidence is None
    assert sig.uncalibrated
    assert "uncalibrated" in sig.glance()


def test_no_confidence_below_min_samples():
    # A calibration with too few samples is NOT enough — still uncalibrated.
    thin = Calibration("refactor", right=2, total=MIN_SAMPLES - 1)
    sig = build_signal(_low_risk(), calibration=thin)
    assert sig.confidence is None
    assert sig.uncalibrated


def test_confidence_only_with_enough_samples():
    solid = Calibration("refactor", right=29, total=30)
    sig = build_signal(_low_risk(), calibration=solid)
    assert sig.confidence == round(29 / 30, 2)
    assert not sig.uncalibrated
    assert "confident" in sig.glance()
    assert "30 samples" in sig.glance()


def test_glance_is_single_line():
    sig = build_signal(_high_risk(), calibration=None)
    assert "\n" not in sig.glance()


# --- forcing eligibility + budget ---------------------------------------------------------

def test_low_stakes_does_not_warrant_forcing():
    sig = build_signal(_low_risk(), calibration=None)
    assert not warrants_forcing(sig)


def test_high_stakes_warrants_forcing():
    sig = build_signal(_high_risk(), calibration=None)
    assert warrants_forcing(sig)


def test_irreversible_alone_warrants_forcing():
    # Even small + owned, irreversibility alone is worth a beat.
    s = StructuralRisk(1, 0, Reversibility.IRREVERSIBLE, Familiarity.OWNED)
    assert warrants_forcing(build_signal(s, calibration=None))


def test_novel_alone_warrants_forcing():
    s = StructuralRisk(1, 0, Reversibility.TRIVIAL, Familiarity.NOVEL)
    assert warrants_forcing(build_signal(s, calibration=None))


def test_forcing_budget_rations_gates():
    budget = ForcingBudget(limit=2)
    assert budget.try_spend() is True
    assert budget.try_spend() is True
    assert budget.try_spend() is False  # exhausted — no ceremony-decay
    assert budget.exhausted
