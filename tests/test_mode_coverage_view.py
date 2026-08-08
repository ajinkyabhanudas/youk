"""Tests for mode_coverage_view — the coverage tree generalized across modes.

Guarantees: a mode's pass renders as the uniform coverage view; an angle the pass never
reached shows as a MISSING gap (cheap to find); the view never implies self-verification.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from coverage_tree import AdversaryStatus, Coverage  # noqa: E402
from mode_coverage_view import MODE_ANGLES, view_from_outcomes  # noqa: E402


def test_challenge_pass_renders_as_tree():
    outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
    tree = view_from_outcomes("challenge", "add feature X", outcomes)
    assert tree.branches[0].domain == "challenge"
    assert "COVERAGE · challenge" in tree.render()


def test_unreached_angle_is_a_gap():
    # Only two of stress-test's three lenses reasoned about → the third is a MISSING gap.
    outcomes = {"scale": Coverage.COVERED, "edge cases": Coverage.COVERED}
    tree = view_from_outcomes("stress-test", "the plan", outcomes)
    gaps = [n.concept for _, n in tree.all_gaps()]
    assert "hidden assumptions" in gaps


def test_view_does_not_imply_self_verification():
    # No independent adversary run → status stays NOT_RUN (no false-green self-verify).
    outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["nfr-check"]}
    tree = view_from_outcomes("nfr-check", "endpoint Y", outcomes)
    assert tree.adversary_status is AdversaryStatus.NOT_RUN
    assert tree.unverified


def test_all_three_modes_share_the_view():
    for mode in ("challenge", "stress-test", "nfr-check"):
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES[mode]}
        tree = view_from_outcomes(mode, "t", outcomes)
        # same primitives → same review_order machinery available to every mode
        assert hasattr(tree, "review_order")
        assert tree.render().startswith("COVERAGE ·")


def test_details_attach_to_nodes():
    outcomes = {"scale": Coverage.PARTIAL}
    details = {"scale": "only tested to 10x, not 100x"}
    tree = view_from_outcomes("stress-test", "t", outcomes, details=details)
    scale_node = next(n for n in tree.branches[0].nodes if n.concept == "scale")
    assert scale_node.detail == "only tested to 10x, not 100x"
