"""Drift sentinel for the coverage-tree SKILL.md.

Contract: specification files with named behavioral properties need drift-sentinel tests that
assert on content structure, so CI catches an edit that silently removes a quality bar. The
load-bearing bar here is spawn-don't-fake — the property that keeps the adversary genuinely
independent. If that phrasing is ever removed, the surface silently degrades to false-green.
"""
from __future__ import annotations

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "coverage-tree" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_skill_exists():
    assert SKILL.exists()


def test_spawn_dont_fake_bar_present():
    t = _text().lower()
    assert "spawn-don't-fake" in t
    # the independence rationale must survive edits
    assert "stripped context" in t
    assert "inline self-critique is not the adversary" in t


def test_stakes_gate_and_safety_floor_present():
    t = _text().lower()
    assert "must_spawn_adversary" in t
    assert "safety floor" in t
    assert "unverified" in t  # the honest degraded state must stay documented


def test_adversary_raises_not_rules_present():
    assert "raises, it does not rule" in _text().lower()


def test_self_revision_documented():
    assert "add_concept_to_template" in _text()


def test_completeness_not_correctness_framing():
    t = _text().lower()
    assert "completeness before correctness" in t
