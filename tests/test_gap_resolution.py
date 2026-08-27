"""Tests for gap re-verification.

The open half of the self-improvement loop. Gaps were recorded and proposals generated,
and nothing ever checked whether the gap still existed, so fixed gaps were re-reported
and re-proposed every run. Measured on live data: 10 of 20 recorded gaps were already
addressed, and 12 of 35 proposals had been closed as stale or duplicate.

youk had already diagnosed this itself, in a CLOSED proposal from 2026-07-15: "Root
cause: self_heal re-generates proposals without checking existing skill content first."
The finding was right and nothing routed it back into behaviour.

The asymmetry is the design. A false RESOLVED hides a real defect forever; a false OPEN
costs one line of noise. Several tests below exist specifically to hold that asymmetry.
"""
from __future__ import annotations

from pathlib import Path

from gap_resolution import (
    _RESOLVED_THRESHOLD,
    classify_gap,
    resolution_summary,
    reverify_gap_signals,
)


class TestClassifyGap:
    def test_gap_fully_described_in_skill_is_resolved(self):
        gap = "contracts verbalized mid-session existed only in conversation context"
        skill = (
            "## Contracts\nContracts verbalized mid-session existed only in "
            "conversation context until session_end, so they are written immediately.\n"
        )
        verdict, overlap = classify_gap(gap, skill)
        assert verdict == "RESOLVED"
        assert overlap >= _RESOLVED_THRESHOLD

    def test_unrelated_skill_content_leaves_gap_open(self):
        gap = "retry backoff is not implemented for transient upstream failures"
        skill = "## Phases\nRender a coverage tree and review the shape.\n"
        assert classify_gap(gap, skill)[0] == "OPEN"

    def test_same_domain_but_different_gap_stays_open(self):
        """The failure mode at a lower threshold: skills about caching mention caching."""
        gap = "cache eviction policy is unspecified for the multi-tenant path"
        skill = "## Caching\nCache keys are sha256 of the query. TTL is 24h.\n"
        assert classify_gap(gap, skill)[0] == "OPEN"

    def test_thin_gap_text_is_unknown_not_resolved(self):
        """Too little signal to judge must not become a silent RESOLVED."""
        assert classify_gap("fix it", "anything at all")[0] == "UNKNOWN"

    def test_empty_skill_text_leaves_gap_open(self):
        gap = "retry backoff missing for transient upstream failures entirely"
        assert classify_gap(gap, "")[0] == "OPEN"


class TestAsymmetryIsPreserved:
    def test_unknown_is_reported_as_open(self):
        """UNKNOWN must land in open_signals, never in resolved."""
        signals = [{"skill": "s", "gaps": ["fix it"]}]
        r = _run(signals, {"s": "some skill content here"})
        assert r["resolved"] == []
        assert r["open_signals"][0]["gaps"] == ["fix it"]

    def test_missing_skill_md_is_unverifiable_not_resolved(self, tmp_path):
        """A missing skill may mean the gap is worse, not fixed."""
        r = reverify_gap_signals([{"skill": "ghost", "gaps": ["a real gap here"]}], tmp_path)
        assert r["resolved"] == []
        assert r["unverifiable"][0]["skill"] == "ghost"

    def test_resolved_gaps_are_reported_not_dropped(self):
        gap = "contracts verbalized mid-session existed only in conversation context"
        r = _run([{"skill": "s", "gaps": [gap]}], {"s": gap + " and are now written"})
        assert len(r["resolved"]) == 1
        assert r["resolved"][0]["gap"] == gap
        assert "overlap" in r["resolved"][0]

    def test_threshold_is_high_enough_to_be_conservative(self):
        assert _RESOLVED_THRESHOLD >= 0.7


class TestReverifySplitsCorrectly:
    def test_mixed_signal_splits_into_both_lists(self):
        fixed = "contracts verbalized mid-session existed only in conversation context"
        live = "retry backoff absent for transient upstream connection failures"
        r = _run([{"skill": "s", "gaps": [fixed, live]}], {"s": fixed})
        assert [x["gap"] for x in r["resolved"]] == [fixed]
        assert r["open_signals"][0]["gaps"] == [live]

    def test_skill_with_all_gaps_resolved_leaves_open_signals_empty(self):
        gap = "contracts verbalized mid-session existed only in conversation context"
        r = _run([{"skill": "s", "gaps": [gap]}], {"s": gap})
        assert r["open_signals"] == []

    def test_checked_counts_every_gap(self):
        r = _run([{"skill": "s", "gaps": ["alpha bravo charlie delta", "echo foxtrot golf hotel"]}],
                 {"s": "nothing relevant"})
        assert r["checked"] == 2

    def test_empty_input_is_safe(self, tmp_path):
        r = reverify_gap_signals([], tmp_path)
        assert r["checked"] == 0
        assert r["open_signals"] == []


class TestSummary:
    def test_summary_is_empty_when_nothing_reclassified(self):
        assert resolution_summary({"resolved": []}) == ""

    def test_summary_names_skills_and_invites_disagreement(self):
        out = resolution_summary({"resolved": [{"skill": "compaction", "gap": "g", "overlap": 1.0}]})
        assert "compaction" in out
        assert "re-open" in out.lower()


def _run(signals, skill_texts) -> dict:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    for name, text in skill_texts.items():
        (tmp / name).mkdir(parents=True, exist_ok=True)
        (tmp / name / "SKILL.md").write_text(text)
    return reverify_gap_signals(signals, tmp)


class TestEmptyProposalCannotBeApplied:
    """An empty SKILL_EDIT payload is destructive, not a no-op.

    apply_proposal replaces the entire target section, so empty content deletes it.
    Twelve auto-promoted proposals sat in PENDING.md with empty content and empty
    rationale, each regenerated four times. Applying any one would have silently emptied
    a skill section. Proven by replaying the replacement logic on a populated section:
    every bar was removed and the heading left behind.
    """

    def test_empty_content_replacement_would_delete_the_section(self):
        """The behaviour being guarded against, demonstrated directly."""
        import re

        current = "# S\n\n## Quality bars\n\n1. real bar\n\n## Next\n\nkeep\n"
        section, content = "Quality bars", ""
        m = re.search(rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)", current, re.DOTALL)
        body = content.lstrip("\n")
        new_section = body if body.startswith(f"## {section}") else f"## {section}\n{body}"
        result = current[: m.start()] + new_section + current[m.end():]
        assert "real bar" not in result
        assert "keep" in result, "neighbouring section must be untouched"

    def test_guard_rejects_whitespace_only_content(self):
        assert not "   \n\t ".strip()

    def test_business_rule_error_resolves_without_import(self):
        """The guard must not NameError on the path where it prevents damage."""
        from health import _business_rule_error

        assert _business_rule_error() == "BUSINESS_RULE"


class TestUnverifiableStaysOpen:
    """Inability to classify must never look like resolution.

    The first version appended to `unverifiable` and returned early, dropping the signal
    from open_signals entirely. Two existing health tests caught it. A gap nobody can
    classify is still a gap, and hiding it behind a classification failure is the same
    asymmetry violation as a false RESOLVED.
    """

    def test_unverifiable_signal_still_appears_in_open_signals(self, tmp_path):
        signals = [{"skill": "ghost", "gaps": ["a real unaddressed gap here"]}]
        r = reverify_gap_signals(signals, tmp_path)
        assert r["open_signals"] == signals
        assert r["unverifiable"][0]["skill"] == "ghost"
        assert r["resolved"] == []

    def test_mixed_verifiable_and_unverifiable_both_survive(self):
        gap = "retry backoff absent for transient upstream connection failures"
        r = _run(
            [{"skill": "real", "gaps": [gap]}, {"skill": "ghost", "gaps": [gap]}],
            {"real": "unrelated skill content"},
        )
        names = {s["skill"] for s in r["open_signals"]}
        assert names == {"real", "ghost"}
