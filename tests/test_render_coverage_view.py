"""Tests for the coverage view rendering contract.

mode_coverage_view existed and was well-designed, and three SKILL.md files carried a
quality bar mandating its use. It was skipped six times in one session — three
challenge runs, two nfr-checks, a stress-test — because emitting it required
remembering a prose bar and hand-rendering a tree. Prose bars are not mechanisms.

The behaviour worth guarding is the part that protects the reader: an angle the pass
never reached must render as a GAP rather than silently vanishing, and completeness
must never read as verified when no adversary ran.
"""
from __future__ import annotations

from coverage_tree import Coverage
from mode_coverage_view import MODE_ANGLES, view_from_outcomes


def _render(mode, target, outcomes, details=None):
    return view_from_outcomes(mode, target, outcomes, details=details or {}).render()


class TestUnreachedAnglesSurfaceAsGaps:
    def test_omitted_angle_renders_as_gap(self):
        """The load-bearing behaviour: silence about an angle is not coverage."""
        out = _render("challenge", "x", {"is this the right problem": Coverage.COVERED})
        assert "GAP" in out
        assert "what fixed constraints bound this" in out

    def test_all_angles_covered_shows_no_gap(self):
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        assert "GAP" not in _render("challenge", "x", outcomes)

    def test_partial_is_distinct_from_missing(self):
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        first = MODE_ANGLES["challenge"][0]
        outcomes[first] = Coverage.PARTIAL
        out = _render("challenge", "x", outcomes)
        assert "GAP" not in out
        assert "~" in out or "partial" in out

    def test_na_does_not_read_as_a_gap(self):
        """A legitimately inapplicable angle is not a miss."""
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["nfr-check"]}
        outcomes["caching"] = Coverage.NA
        assert "GAP" not in _render("nfr-check", "x", outcomes)


class TestNeverClaimsSelfVerification:
    def test_render_marks_completeness_unverified(self):
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        out = _render("challenge", "x", outcomes)
        assert "UNVERIFIED" in out

    def test_full_coverage_still_says_unverified(self):
        """A pass with every angle green must not imply it checked itself."""
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["stress-test"]}
        assert "UNVERIFIED" in _render("stress-test", "x", outcomes)


class TestModeAngleSets:
    def test_known_modes_use_their_fixed_angle_set(self):
        out = _render("nfr-check", "x", {"caching": Coverage.COVERED})
        for angle in MODE_ANGLES["nfr-check"]:
            assert angle in out

    def test_unknown_mode_falls_back_to_supplied_keys(self):
        out = _render("custom-mode", "x", {"some angle": Coverage.COVERED})
        assert "some angle" in out

    def test_details_appear_for_flagged_nodes(self):
        out = _render(
            "challenge", "x",
            {"is this the right problem": Coverage.PARTIAL},
            details={"is this the right problem": "only framing checked"},
        )
        assert "only framing" in out

    def test_target_appears_in_header(self):
        out = _render("challenge", "structural integrity cap", {})
        assert "structural integrity cap" in out


class TestReviewOrderIsActionable:
    def test_gaps_sort_ahead_of_partials(self):
        """Cheapest to check first, so the reader starts where judgement never went."""
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        outcomes[MODE_ANGLES["challenge"][0]] = Coverage.PARTIAL
        del outcomes[MODE_ANGLES["challenge"][1]]
        order = view_from_outcomes("challenge", "x", outcomes).review_order()
        assert order, "review order is empty despite a gap and a partial"
        assert order[0].startswith("GAP")

    def test_clean_pass_has_empty_review_order(self):
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        assert view_from_outcomes("challenge", "x", outcomes).review_order() == []


class TestEvidenceClassSeparatesMeasuredFromInferred:
    """The state the tree most needs to distinguish.

    Without evidence, a node established by running a test renders identically to one
    established by assuming. Across one session every wrong claim was inferred and every
    correction came from measuring, so inferred is the highest-yield thing a reader can
    be pointed at after an outright gap.

    Evidence is a fact about what was done, not a confidence rating. Confidence is
    self-reported by the model that did the work and was high on all three wrong claims.
    """

    @staticmethod
    def _tree(evidence_map):
        from coverage_tree import Evidence
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        ev = {a: Evidence(v) for a, v in evidence_map.items()}
        return view_from_outcomes("challenge", "x", outcomes, evidence=ev)

    def test_inferred_node_appears_in_review_order(self):
        first = MODE_ANGLES["challenge"][0]
        order = self._tree({first: "inferred"}).review_order()
        assert any("INFER" in line and first in line for line in order)

    def test_measured_node_does_not_appear_in_review_order(self):
        first = MODE_ANGLES["challenge"][0]
        assert self._tree({first: "measured"}).review_order() == []

    def test_read_node_does_not_appear_in_review_order(self):
        first = MODE_ANGLES["challenge"][0]
        assert self._tree({first: "read"}).review_order() == []

    def test_evidence_renders_in_the_tree_body(self):
        first = MODE_ANGLES["challenge"][0]
        out = self._tree({first: "measured"}).render()
        assert "[measured]" in out

    def test_gap_sorts_ahead_of_inferred(self):
        """Never reached beats reached-but-unverified."""
        from coverage_tree import Evidence
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        del outcomes[MODE_ANGLES["challenge"][1]]
        ev = {MODE_ANGLES["challenge"][0]: Evidence.INFERRED}
        order = view_from_outcomes("challenge", "x", outcomes, evidence=ev).review_order()
        assert order[0].startswith("GAP")
        assert any(line.startswith("INFER") for line in order)

    def test_absent_evidence_is_not_reported(self):
        """Omitting evidence must not manufacture a finding."""
        outcomes = {a: Coverage.COVERED for a in MODE_ANGLES["challenge"]}
        assert view_from_outcomes("challenge", "x", outcomes).review_order() == []
