"""Self-revision meta-loop registry (Task 2).

The load-bearing tests are the SAFETY ones: a frozen safety/fact set must be hard-blocked
from enrollment by construction, no matter what a caller passes. The rest prove the
grow/prune/revert loop works and is versioned (revert floor).
"""
from __future__ import annotations

import pytest

from revisable_sets import (
    EnrollmentError,
    enroll,
    get_set,
    learn_add,
    list_enrolled,
    revert,
    unlearn_prune,
)


@pytest.fixture
def reg(tmp_path):
    return tmp_path / "revisable-sets.json"


# ── SAFETY BOUNDARY (the non-negotiable part) ──────────────────────────────

@pytest.mark.parametrize("frozen_name", [
    "_ALLOWED_WRITE_ROOTS", "_CODE_EXTS", "_SKIP_DIRS", "SECRET_SAFETY",
    "CONTRACT_VERBATIM", "_STOP_WORDS",
])
def test_frozen_sets_are_hard_blocked_from_enrollment(frozen_name, reg):
    """A safety wall or mechanical-fact set can NEVER be enrolled — by construction,
    regardless of caller intent."""
    with pytest.raises(EnrollmentError, match="hard-blocked"):
        enroll(frozen_name, "both", ["x"], path=reg)


def test_frozen_block_cannot_be_bypassed_by_policy(reg):
    for policy in ("grow", "prune", "both"):
        with pytest.raises(EnrollmentError):
            enroll("_ALLOWED_WRITE_ROOTS", policy, ["/etc"], path=reg)


# ── enrollment ─────────────────────────────────────────────────────────────

def test_enroll_a_judgment_set(reg):
    result = enroll("_SEVEN_CONVERGENCE", "both",
                    ["structural", "operational", "semantic"], path=reg)
    assert result["enrolled"] == "_SEVEN_CONVERGENCE"
    assert result["element_count"] == 3
    assert "_SEVEN_CONVERGENCE" in list_enrolled(path=reg)


def test_invalid_policy_rejected(reg):
    with pytest.raises(ValueError, match="policy must be"):
        enroll("_FOUR_LENSES", "sometimes", ["framing"], path=reg)


def test_unenrolled_set_is_frozen_by_default(reg):
    # A set that was never enrolled is simply absent — the default is frozen.
    assert get_set("_NEVER_ENROLLED", path=reg) is None


# ── LEARN (grow) ───────────────────────────────────────────────────────────

def test_learn_add_grows_the_set(reg):
    enroll("_SEVEN_CONVERGENCE", "grow", ["structural"], path=reg)
    result = learn_add("_SEVEN_CONVERGENCE", "ethical", driver="recurring_gap", path=reg)
    assert result["ok"]
    s = get_set("_SEVEN_CONVERGENCE", path=reg)
    assert "ethical" in s["elements"]
    assert s["elements"]["ethical"]["added_by"] == "recurring_gap"


def test_learn_add_blocked_when_policy_is_prune_only(reg):
    enroll("s", "prune", ["a", "b"], path=reg)
    result = learn_add("s", "c", driver="x", path=reg)
    assert not result["ok"]
    assert "does not allow grow" in result["reason"]


def test_learn_add_rejects_duplicate(reg):
    enroll("s", "grow", ["a"], path=reg)
    result = learn_add("s", "a", driver="x", path=reg)
    assert not result["ok"]


# ── UNLEARN (prune) — the anti-bloat mechanism ─────────────────────────────

def test_unlearn_prune_removes_element(reg):
    enroll("s", "both", ["a", "b", "c"], path=reg)
    result = unlearn_prune("s", "b", driver="never_fired", path=reg)
    assert result["ok"]
    assert "b" not in get_set("s", path=reg)["elements"]


def test_unlearn_refuses_to_empty_the_set(reg):
    enroll("s", "prune", ["only"], path=reg)
    result = unlearn_prune("s", "only", driver="x", path=reg)
    assert not result["ok"]
    assert "last element" in result["reason"]


# ── versioning + revert (the human veto / revert floor) ────────────────────

def test_mutations_bump_version(reg):
    enroll("s", "both", ["a"], path=reg)
    v0 = get_set("s", path=reg)["version"]
    learn_add("s", "b", driver="x", path=reg)
    v1 = get_set("s", path=reg)["version"]
    assert v1 == v0 + 1


def test_revert_restores_prior_snapshot(reg):
    enroll("s", "both", ["a", "b"], path=reg)
    learn_add("s", "c", driver="x", path=reg)
    assert "c" in get_set("s", path=reg)["elements"]
    result = revert("s", path=reg)
    assert result["ok"]
    assert "c" not in get_set("s", path=reg)["elements"]
    assert set(get_set("s", path=reg)["elements"]) == {"a", "b"}


def test_revert_with_no_history_is_safe(reg):
    enroll("s", "both", ["a"], path=reg)
    result = revert("s", path=reg)
    assert not result["ok"]
