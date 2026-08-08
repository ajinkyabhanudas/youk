"""Drift sentinel: the coverage view must stay wired into every mode's Quality Bars.

Contract: named behavioral properties in spec files need content-structure tests so CI catches
silent removal. The emit-the-coverage-view bar is what makes challenge/stress-test/nfr-check
render glanceable completeness; if an edit drops it from a mode, that mode silently regresses to
prose-only completeness (the original disease).
"""
from __future__ import annotations

from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"
MODES = ["challenge", "nfr-check", "stress-test"]


def test_every_mode_emits_the_coverage_view():
    for mode in MODES:
        text = (SKILLS / mode / "SKILL.md").read_text()
        assert "Emit the coverage view" in text, f"{mode} lost the coverage-view emit bar"
        assert f'view_from_outcomes("{mode}"' in text, f"{mode} emit call malformed"


def test_every_mode_keeps_the_unverified_honesty():
    for mode in MODES:
        text = (SKILLS / mode / "SKILL.md").read_text().lower()
        # the anti-false-green clause must ride along with the emit bar
        assert "unverified unless an independent adversary" in text, (
            f"{mode} lost the self-verify honesty clause"
        )
