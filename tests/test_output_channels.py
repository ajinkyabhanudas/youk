"""Tests for output_channels — the two-channel view.

Guarantees under test: execution collapses to one line by default and expands losslessly;
comprehension admits only load-bearing items and paces them (digest, not per-step); empty
digest renders empty (no manufactured teaching).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from confidence_signal import (  # noqa: E402
    Calibration,
    Familiarity,
    Reversibility,
    StructuralRisk,
    build_signal,
)
from output_channels import (  # noqa: E402
    CompItem,
    ComprehensionDigest,
    ExecutionStep,
    Load,
    TaskView,
)


def _step(label: str = "edit auth.py") -> ExecutionStep:
    sig = build_signal(
        StructuralRisk(2, 1, Reversibility.RECOVERABLE, Familiarity.KNOWN),
        calibration=Calibration("edit", right=28, total=30),
    )
    return ExecutionStep(label=label, signal=sig, full_trace="line1\nline2\nline3")


# --- Channel 1: execution -----------------------------------------------------------------

def test_collapsed_is_single_line():
    assert "\n" not in _step().collapsed()


def test_collapsed_shows_signal():
    c = _step().collapsed()
    assert "risk" in c and "confident" in c


def test_expand_round_trips_full_trace():
    s = _step()
    expanded = s.expanded()
    # expanded contains the collapsed line AND the full trace, losslessly
    assert s.collapsed() in expanded
    assert "line1" in expanded and "line3" in expanded


# --- Channel 2: comprehension -------------------------------------------------------------

def test_empty_digest_renders_empty():
    # No load-bearing items → no teaching manufactured.
    assert ComprehensionDigest().render() == ""


def test_digest_groups_foreclosure_first():
    d = ComprehensionDigest()
    d.admit(CompItem(Load.PATTERN, "use factory closure for shared context"))
    d.admit(CompItem(Load.FORECLOSURE, "dropped tamper-evidence — irreversible"))
    d.admit(CompItem(Load.TRADEOFF, "chose sqlite over json for the graph"))
    out = d.render()
    # foreclosure header appears before tradeoff header before pattern header
    assert out.index("Foreclosed") < out.index("Trade-offs") < out.index("Patterns")


def test_digest_includes_context_when_present():
    d = ComprehensionDigest()
    d.admit(CompItem(Load.TRADEOFF, "budget-gated the forcing", context="signal.py"))
    assert "(signal.py)" in d.render()


# --- combined view ------------------------------------------------------------------------

def test_taskview_default_is_ledger_only_when_no_digest():
    tv = TaskView(steps=[_step("a"), _step("b")])
    out = tv.render()
    assert "comprehension digest" not in out
    assert out.count("\n") == 1  # two collapsed lines, one newline between


def test_taskview_appends_digest_when_present():
    tv = TaskView(steps=[_step("a")])
    tv.digest.admit(CompItem(Load.FORECLOSURE, "closed a door"))
    out = tv.render()
    assert "comprehension digest" in out
    assert "closed a door" in out


def test_taskview_ledger_is_all_collapsed_lines():
    tv = TaskView(steps=[_step("x"), _step("y")])
    ledger = tv.ledger()
    assert ledger.count("\n") == 1
    assert "x ·" in ledger and "y ·" in ledger
