"""Self-revision meta-loop — the revisable-sets registry (Task 2, ADR self-revision-meta-loop).

youk holds ~30 enumerated sets (challenge angles, NFR questions, risk tiers, trigger words).
Each ASSERTS completeness but each can be wrong. This registry lets a set be REVISED — grown
at its frontier, pruned of dead weight — gated by youk's own challenge discipline, with a human
veto after the fact. Built once, applied only to sets that encode a revisable JUDGMENT.

THE SAFETY BOUNDARY (non-negotiable, enforced here by construction):
Enrollment is opt-in and default-frozen. A set is revisable ONLY if explicitly registered with
a policy. Safety walls and mechanical facts are HARD-BLOCKED — attempting to enroll one raises,
regardless of any caller's intent. `.py` being a code extension is not an opinion; _ALLOWED_WRITE_ROOTS
self-revising is a breach, not learning. A human learns new things but never unlearns that fire burns.

Storage: versioned. Every mutation (add/prune) snapshots the prior state so a human can revert.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

YOUK_ROOT = Path("/youk")
_REGISTRY_FILE = YOUK_ROOT / "state" / "revisable-sets.json"


class EnrollmentError(ValueError):
    """Raised when a set that must stay frozen is offered for enrollment."""


# ── Eligibility boundary (design-time safety; NEVER a runtime/user decision) ──
# These names are hard-blocked from enrollment. Membership here is a wall, not a default.
FROZEN_HARD_BLOCKED: frozenset[str] = frozenset({
    # mechanical facts — not opinions that can be wrong
    "_CODE_EXTS", "_DOC_EXTS", "_CONFIG_EXTS", "_ALL_EXTS", "_SKIP_DIRS", "_STOP_WORDS",
    # safety walls — self-revision here is a breach
    "_ALLOWED_WRITE_ROOTS", "SECRET_SAFETY", "CONTRACT_VERBATIM",
})

# Revision policies a registered set may declare.
_VALID_POLICIES = frozenset({"grow", "prune", "both"})


@dataclass
class RevisableSet:
    """A registered, revisable judgment-set with per-element provenance."""

    name: str
    policy: str                       # grow | prune | both
    elements: dict[str, dict]         # element -> {added_by, added_at, fires: int}
    version: int = 0
    history: list[dict] = field(default_factory=list)  # prior snapshots (revert floor)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "policy": self.policy,
            "elements": self.elements,
            "version": self.version,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RevisableSet:
        return cls(
            name=d["name"],
            policy=d["policy"],
            elements=d.get("elements", {}),
            version=d.get("version", 0),
            history=d.get("history", []),
        )


def _load_registry(path: Path = _REGISTRY_FILE) -> dict[str, RevisableSet]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        return {k: RevisableSet.from_dict(v) for k, v in raw.items()}
    except Exception:
        return {}


def _save_registry(reg: dict[str, RevisableSet], path: Path = _REGISTRY_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v.to_dict() for k, v in reg.items()}, indent=1))


def _assert_enrollable(name: str) -> None:
    """The safety gate. Raises if `name` is a hard-blocked frozen set."""
    if name in FROZEN_HARD_BLOCKED:
        raise EnrollmentError(
            f"'{name}' is a frozen safety/fact set — enrollment is hard-blocked by "
            f"construction. Self-revision here would be a breach, not learning."
        )


def enroll(name: str, policy: str, initial_elements: list[str],
           path: Path = _REGISTRY_FILE) -> dict:
    """Register a judgment-set as revisable. Opt-in; default is frozen (unregistered).

    Raises EnrollmentError if the set is hard-blocked (safety/fact). Idempotent per name:
    re-enrolling updates policy but preserves existing element provenance.
    """
    _assert_enrollable(name)
    if policy not in _VALID_POLICIES:
        raise ValueError(f"policy must be one of {sorted(_VALID_POLICIES)}, got '{policy}'")

    reg = _load_registry(path)
    now = time.time()
    if name in reg:
        reg[name].policy = policy
    else:
        reg[name] = RevisableSet(
            name=name,
            policy=policy,
            elements={
                e: {"added_by": "enroll", "added_at": now, "fires": 0}
                for e in initial_elements
            },
        )
    _save_registry(reg, path)
    return {"enrolled": name, "policy": policy, "element_count": len(reg[name].elements)}


def _snapshot(rs: RevisableSet) -> None:
    """Record the current state into history before mutating (revert floor)."""
    rs.history.append({
        "version": rs.version,
        "elements": list(rs.elements.keys()),
        "at": time.time(),
    })
    rs.version += 1


def learn_add(name: str, element: str, driver: str,
              path: Path = _REGISTRY_FILE) -> dict:
    """LEARN (grow): add an element to an enrolled set. Requires policy grow|both.

    Returns {"ok": bool, "reason": str, "version": int}. Caller is responsible for having
    run the candidate through challenge first (challenge_cleared is asserted by the tool
    wrapper, not here — this is the storage primitive).
    """
    reg = _load_registry(path)
    if name not in reg:
        return {"ok": False, "reason": f"'{name}' is not enrolled", "version": -1}
    rs = reg[name]
    if rs.policy not in ("grow", "both"):
        return {"ok": False, "reason": f"policy '{rs.policy}' does not allow grow", "version": rs.version}
    if element in rs.elements:
        return {"ok": False, "reason": "element already present", "version": rs.version}

    _snapshot(rs)
    rs.elements[element] = {"added_by": driver, "added_at": time.time(), "fires": 0}
    _save_registry(reg, path)
    return {"ok": True, "reason": f"added '{element}' (driver: {driver})", "version": rs.version}


def unlearn_prune(name: str, element: str, driver: str,
                  path: Path = _REGISTRY_FILE) -> dict:
    """UNLEARN (prune): remove an element from an enrolled set. Requires policy prune|both.

    The anti-bloat mechanism — a set that only grows becomes rigid ceremony. Never removes
    the last element (a set pruned to empty is a bug, not learning).
    """
    reg = _load_registry(path)
    if name not in reg:
        return {"ok": False, "reason": f"'{name}' is not enrolled", "version": -1}
    rs = reg[name]
    if rs.policy not in ("prune", "both"):
        return {"ok": False, "reason": f"policy '{rs.policy}' does not allow prune", "version": rs.version}
    if element not in rs.elements:
        return {"ok": False, "reason": "element not present", "version": rs.version}
    if len(rs.elements) <= 1:
        return {"ok": False, "reason": "refusing to prune the last element", "version": rs.version}

    _snapshot(rs)
    del rs.elements[element]
    _save_registry(reg, path)
    return {"ok": True, "reason": f"pruned '{element}' (driver: {driver})", "version": rs.version}


def revert(name: str, path: Path = _REGISTRY_FILE) -> dict:
    """Roll a set back to its previous snapshot (the human veto / revert floor)."""
    reg = _load_registry(path)
    if name not in reg or not reg[name].history:
        return {"ok": False, "reason": "nothing to revert"}
    rs = reg[name]
    prior = rs.history.pop()
    # Restore element keys from the snapshot; keep provenance for surviving elements.
    restored = {
        e: rs.elements.get(e, {"added_by": "revert", "added_at": time.time(), "fires": 0})
        for e in prior["elements"]
    }
    rs.elements = restored
    rs.version = prior["version"]
    _save_registry(reg, path)
    return {"ok": True, "reason": f"reverted to version {rs.version}", "elements": list(restored)}


def get_set(name: str, path: Path = _REGISTRY_FILE) -> dict | None:
    reg = _load_registry(path)
    return reg[name].to_dict() if name in reg else None


def list_enrolled(path: Path = _REGISTRY_FILE) -> list[str]:
    return sorted(_load_registry(path).keys())
