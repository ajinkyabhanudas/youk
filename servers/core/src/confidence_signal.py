"""Confidence/risk signal — the glanceable per-step metacognitive cue.

The blind spot this closes: youk narrates all reasoning at max depth, so the human cannot
tell which step deserves attention. This signal is the *cheap* cue — read in a glance — that
tells the human how much to trust THIS step, so they spend finite attention proportionally.
It is NOT content; it is a pointer to where content is worth reading (Amershi G2: "how well
can it do what it does"; Lee & See: trust must calibrate, not collapse to all-or-nothing).

Two layers (see BUILD-SPEC D5):
  - STRUCTURAL (day 1, always available, pure-local): blast-radius, reversibility, area
    familiarity. This is RISK — what is at stake — derivable from facts youk already has.
  - CALIBRATION (overlaid as track-record accrues): youk's measured correctness per
    decision-class vs the human's overrides. This is CONFIDENCE — how often youk was right
    at this kind of thing. Empty until >= MIN_SAMPLES; until then the signal is honestly
    `uncalibrated`, never a fabricated number.

THE NAMED ANTI-PATTERN THIS MUST NOT REPEAT (wiring_pulse.py false-green): a signal that
reads "confident" without a basis is theater and worse than no signal. Confidence is only
ever surfaced when a real track record backs it. Absent that, the signal shows risk +
`uncalibrated` and says so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Minimum decision-class samples before a calibration (confidence) number is trustworthy.
# Below this, we surface `uncalibrated` rather than a number computed from too little data.
MIN_SAMPLES = 5


class Reversibility(StrEnum):
    """How hard is this step to undo? Drives both risk and forcing-gate eligibility."""
    TRIVIAL = "trivial"        # single-commit revert, no external effect
    RECOVERABLE = "recoverable"  # undoable with effort (migration down, config rollback)
    IRREVERSIBLE = "irreversible"  # external side effect, data loss, published artifact


class Familiarity(StrEnum):
    """How well does the human know THIS module? (expertise-reversal: scaffold where new,
    fall away where expert). Legible — the human can inspect the familiarity map (OQ3)."""
    OWNED = "owned"        # human authored/edits this module regularly
    KNOWN = "known"        # human has touched it
    NOVEL = "novel"        # human-new, or agent-pioneered area


@dataclass(frozen=True)
class StructuralRisk:
    """Layer 1 — always available, pure-local, no API. This is RISK, not confidence."""
    files_touched: int
    external_callers: int          # callers OUTSIDE the changed module — blast radius
    reversibility: Reversibility
    familiarity: Familiarity

    def score(self) -> float:
        """0.0 (trivial/local/owned) .. 1.0 (wide/irreversible/novel). Monotonic in stakes.

        Deliberately simple and inspectable — the number must be explainable in one breath,
        or it becomes the vibe-number anti-pattern. Each term is a stake the human can see.
        """
        s = 0.0
        s += min(self.files_touched / 10.0, 0.3)          # breadth, capped
        s += min(self.external_callers / 5.0, 0.3)         # blast radius, capped
        s += {                                             # reversibility weight
            Reversibility.TRIVIAL: 0.0,
            Reversibility.RECOVERABLE: 0.15,
            Reversibility.IRREVERSIBLE: 0.4,
        }[self.reversibility]
        s += {                                             # familiarity weight
            Familiarity.OWNED: 0.0,
            Familiarity.KNOWN: 0.05,
            Familiarity.NOVEL: 0.15,
        }[self.familiarity]
        return round(min(s, 1.0), 2)


@dataclass(frozen=True)
class Calibration:
    """Layer 2 — track record for a decision-class. Overlaid only when it exists.

    `right` / `total` are the measured outcomes: how often youk's step of this class stood
    without the human overriding/reverting it. This is the ONLY legitimate source of a
    confidence number (BUILD-SPEC D5, anti-pattern #1).
    """
    decision_class: str
    right: int
    total: int

    @property
    def calibrated(self) -> bool:
        return self.total >= MIN_SAMPLES

    def confidence(self) -> float | None:
        """Measured confidence, or None if too few samples. None is honest; a number here
        with total < MIN_SAMPLES would be the false-green anti-pattern."""
        if not self.calibrated:
            return None
        return round(self.right / self.total, 2)


@dataclass(frozen=True)
class Signal:
    """The rendered glanceable cue. Confidence is Optional by construction — the type system
    itself forbids surfacing a confidence number that has no basis."""
    risk: float                    # 0..1, always present (structural)
    reversibility: Reversibility
    familiarity: Familiarity
    confidence: float | None       # None => uncalibrated; never fabricated
    decision_class: str | None = None
    samples: int = 0

    @property
    def uncalibrated(self) -> bool:
        return self.confidence is None

    def glance(self) -> str:
        """One line, glanceable. The whole point: read in under a second (D2).

        Examples:
          'risk 0.15 · recoverable · owned · confident 0.97 (30 samples)'
          'risk 0.72 · irreversible · novel · uncalibrated'   <- honest, no fake number
        """
        conf = (
            f"confident {self.confidence} ({self.samples} samples)"
            if self.confidence is not None
            else "uncalibrated"
        )
        return (
            f"risk {self.risk} · {self.reversibility.value} · "
            f"{self.familiarity.value} · {conf}"
        )


def build_signal(
    structural: StructuralRisk,
    calibration: Calibration | None = None,
) -> Signal:
    """Compose the layered signal. Structural is mandatory (day 1); calibration is overlaid
    only if present AND has enough samples — otherwise the signal is honestly uncalibrated.

    This is the single entry point; it is the enforcement point for anti-pattern #1: there is
    no code path here that produces a confidence number without a backing sample count.
    """
    confidence = calibration.confidence() if calibration else None
    return Signal(
        risk=structural.score(),
        reversibility=structural.reversibility,
        familiarity=structural.familiarity,
        confidence=confidence,
        decision_class=calibration.decision_class if calibration else None,
        samples=calibration.total if calibration else 0,
    )


# --- forcing-gate eligibility -------------------------------------------------------------
# Cognitive forcing (BUILD-SPEC D6) is rationed by stakes. This predicate names WHEN a step
# is stakes-worthy; the budget (max N/session) is enforced by the caller.

HIGH_RISK_THRESHOLD = 0.6


def warrants_forcing(signal: Signal) -> bool:
    """A step warrants a (budgeted) cognitive-forcing gate when the stakes justify spending
    the human's scarce germane-load attention: high structural risk, OR irreversible, OR a
    novel area. Deliberately OR, not AND — any one of these is enough to be worth a beat."""
    return (
        signal.risk >= HIGH_RISK_THRESHOLD
        or signal.reversibility is Reversibility.IRREVERSIBLE
        or signal.familiarity is Familiarity.NOVEL
    )


@dataclass
class ForcingBudget:
    """Per-session budget so forcing gates stay rare enough not to decay into skimmed
    ceremony (Buçinca: forcing works but is disliked — ration it). Default low."""
    limit: int = 2
    spent: int = field(default=0)

    def try_spend(self) -> bool:
        """Spend one gate if budget remains. Returns True if the gate should fire."""
        if self.spent >= self.limit:
            return False
        self.spent += 1
        return True

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.limit
