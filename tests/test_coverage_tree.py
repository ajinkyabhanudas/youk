"""Tests for coverage_tree — the completeness surface.

Load-bearing guarantees:
  1. FALSE-GREEN IMPOSSIBLE: no adversary (or a raising adversary) → UNVERIFIED, never clean.
  2. Independence pays off: an adversary adds a concept the builder missed, and it surfaces.
  3. MECE is checkable: exhaustive + non-overlapping against the template.
  4. Review order puts cheap-to-find gaps first.
  5. Template self-revises on a human-caught miss.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "servers" / "core" / "src"))

from coverage_tree import (  # noqa: E402
    _SEED_TEMPLATES,
    TEMPLATES,
    AdversaryStatus,
    Branch,
    Coverage,
    Node,
    add_concept_to_template,
    build_tree,
    check_mece,
    must_spawn_adversary,
)


def _full_populator(task, domain, template):
    """Builder that marks every template concept COVERED — the optimistic self-claim."""
    return [Node(concept=c, covered=Coverage.COVERED) for c in template]


def _populator_missing_secrets(task, domain, template):
    """Builder that omits 'secrets handling' entirely — the blind spot the adversary catches."""
    return [
        Node(concept=c, covered=Coverage.COVERED)
        for c in template
        if c != "secrets handling"
    ]


def _adversary_flags_secrets(task, branch, template):
    """Stripped adversary: notices 'secrets handling' is absent and raises it as MISSING."""
    concepts = [n.concept for n in branch.nodes]
    if "secrets handling" in template and "secrets handling" not in concepts:
        return [Node(concept="secrets handling", covered=Coverage.MISSING,
                     detail="no secrets path considered")]
    return []


def _adversary_clean(task, branch, template):
    return []


def _adversary_explodes(task, branch, template):
    raise RuntimeError("no API — subagent could not run")


# --- 1. false-green prevention (the load-bearing test) ------------------------------------

def test_no_adversary_is_unverified_never_clean():
    tree = build_tree("x", ["security"], _full_populator, adversary=None)
    assert tree.adversary_status is AdversaryStatus.NOT_RUN
    assert tree.unverified
    assert "UNVERIFIED" in tree.render()


def test_raising_adversary_degrades_to_unverified():
    # Adversary blows up (no API) → tree must NOT claim verification.
    tree = build_tree("x", ["security"], _full_populator, adversary=_adversary_explodes)
    assert tree.adversary_status is AdversaryStatus.NOT_RUN
    assert tree.unverified
    assert "UNVERIFIED" in tree.render()


def test_clean_adversary_is_verified_clean():
    tree = build_tree("x", ["security"], _full_populator, adversary=_adversary_clean)
    assert tree.adversary_status is AdversaryStatus.CLEAN
    assert not tree.unverified


# --- 2. independence pays off -------------------------------------------------------------

def test_adversary_adds_concept_builder_missed():
    tree = build_tree("x", ["security"], _populator_missing_secrets,
                      adversary=_adversary_flags_secrets)
    assert tree.adversary_status is AdversaryStatus.FOUND_GAPS
    gaps = [n.concept for _, n in tree.all_gaps()]
    assert "secrets handling" in gaps
    added = next(n for _, n in tree.all_gaps() if n.concept == "secrets handling")
    assert added.added_by_adversary
    assert "secrets handling" in tree.render()


# --- 3. MECE checkable --------------------------------------------------------------------

def test_mece_passes_when_exhaustive_and_unique():
    template = ["a", "b", "c"]
    branch = Branch("d", [Node(c, Coverage.COVERED) for c in template])
    ok, problems = check_mece(branch, template)
    assert ok and problems == []


def test_mece_fails_on_overlap():
    branch = Branch("d", [Node("a", Coverage.COVERED), Node("a", Coverage.COVERED)])
    ok, problems = check_mece(branch, ["a"])
    assert not ok
    assert any("overlap" in p for p in problems)


def test_mece_fails_when_not_exhaustive():
    branch = Branch("d", [Node("a", Coverage.COVERED)])
    ok, problems = check_mece(branch, ["a", "b"])
    assert not ok
    assert any("not exhaustive" in p for p in problems)


# --- 4. review order: cheap gaps first ----------------------------------------------------

def test_review_order_puts_gaps_before_partials():
    def pop(task, domain, template):
        return [
            Node("happy path", Coverage.COVERED),
            Node("edge cases", Coverage.PARTIAL),
            Node("error states", Coverage.MISSING),
            Node("concurrency / races", Coverage.COVERED),
        ]
    tree = build_tree("x", ["correctness"], pop, adversary=_adversary_clean)
    order = tree.review_order()
    gap_idx = next(i for i, s in enumerate(order) if s.startswith("GAP"))
    partial_idx = next(i for i, s in enumerate(order) if s.startswith("~"))
    assert gap_idx < partial_idx


def test_review_order_security_gap_ranks_before_nfr_gap():
    def pop(task, domain, template):
        return [Node(template[0], Coverage.MISSING)] if template else []
    tree = build_tree("x", ["nfr", "security"], pop, adversary=_adversary_clean)
    order = [s for s in tree.review_order() if s.startswith("GAP")]
    assert "[security]" in order[0]  # safety domain first even though nfr listed first


# --- 5. template self-revision ------------------------------------------------------------

def test_human_caught_miss_updates_template(tmp_path):
    before = list(TEMPLATES["nfr"])
    overlay = tmp_path / "coverage-templates.json"
    added = add_concept_to_template("nfr", "backpressure", path=overlay)
    assert added
    assert "backpressure" in TEMPLATES["nfr"]
    # idempotent
    assert add_concept_to_template("nfr", "backpressure", path=overlay) is False
    # restore in-memory view for other tests (persistence covered separately below)
    TEMPLATES["nfr"] = before


def test_addition_persists_to_overlay(tmp_path):
    from coverage_tree import _load_overlay, _merged_templates
    overlay = tmp_path / "coverage-templates.json"
    add_concept_to_template("security", "supply-chain / deps", path=overlay)
    # written to disk
    assert overlay.exists()
    assert "supply-chain / deps" in _load_overlay(overlay)["security"]
    # a fresh merge (simulating next-session restart) includes the addition
    merged = _merged_templates(overlay)
    assert "supply-chain / deps" in merged["security"]
    # ...and the seed concepts are still there (overlay augments, never replaces)
    assert "authn / identity" in merged["security"]
    TEMPLATES["security"] = list(_SEED_TEMPLATES["security"])


# --- W1 spawn decision: stakes-gated + unrationed safety floor ----------------------------

def test_safety_floor_forces_spawn_even_when_budget_spent():
    # security in scope → spawn, even if low stakes AND no budget. The floor is unrationed.
    assert must_spawn_adversary(["security"], high_stakes=False, budget_available=False)
    assert must_spawn_adversary(["data"], high_stakes=False, budget_available=False)


def test_high_stakes_with_budget_spawns():
    assert must_spawn_adversary(["correctness"], high_stakes=True, budget_available=True)


def test_high_stakes_without_budget_does_not_spawn():
    # discretionary spawn respects the budget — this is where UNVERIFIED is honest.
    assert not must_spawn_adversary(["correctness"], high_stakes=True, budget_available=False)


def test_low_stakes_non_safety_does_not_spawn():
    assert not must_spawn_adversary(["nfr"], high_stakes=False, budget_available=True)


def test_corrupt_overlay_does_not_crash(tmp_path):
    from coverage_tree import _load_overlay, _merged_templates
    overlay = tmp_path / "coverage-templates.json"
    overlay.write_text("{ not valid json")
    assert _load_overlay(overlay) == {}          # bad file → empty, no raise
    assert _merged_templates(overlay) == {        # falls back to seed cleanly
        k: list(v) for k, v in _SEED_TEMPLATES.items()
    }
