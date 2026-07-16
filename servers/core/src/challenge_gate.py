"""Challenge gate — blocks M+ dev-loop when challenge skill has not run for this task."""
from __future__ import annotations

_BLOCKED_SIZES = {"M", "L", "XL"}
_PASS_REASON = ""
_BLOCK_REASON = (
    "Size {size} task requires challenge skill before implementation. "
    "Run challenge (route_to_skill('challenge', task)) first, then call "
    "mark_challenge_ran(task, angles_checked=[...], mode=<mode>), then re-call check_challenge_gate."
)

# Required angles per challenge mode.
# full: 4 lenses + 7 convergence angles (quality-word tasks)
# quick/silent/plan: 4 lenses only
_FOUR_LENSES = {"framing", "scope", "assumptions", "opportunity"}
_SEVEN_CONVERGENCE = {"structural", "operational", "experiential", "adversarial", "temporal", "outcome", "semantic"}
REQUIRED_ANGLES: dict[str, set[str]] = {
    "full": _FOUR_LENSES | _SEVEN_CONVERGENCE,
    "quick": _FOUR_LENSES,
    "silent": _FOUR_LENSES,
    "plan": _FOUR_LENSES,
}


def validate_angles(angles_checked: list[str], mode: str) -> dict:
    """
    Validate that angles_checked covers all required angles for the given mode.

    Returns {"valid": True} or {"valid": False, "missing_angles": [...], "reason": str}.
    Unknown modes fall back to "full" required set.
    """
    required = REQUIRED_ANGLES.get(mode, REQUIRED_ANGLES["full"])
    checked_set = {a.strip().lower() for a in (angles_checked or [])}
    missing = sorted(required - checked_set)
    if missing:
        return {
            "valid": False,
            "missing_angles": missing,
            "reason": (
                f"Challenge loop not dry — {len(missing)} angle(s) not covered: {missing}. "
                f"Run the missing angles and call mark_challenge_ran again."
            ),
        }
    return {"valid": True, "missing_angles": []}


def check_challenge_gate(task: str, size: str, challenge_ran: bool) -> dict:
    """
    Return {"blocked": bool, "reason": str}.

    Blocks when size is M/L/XL AND challenge_ran is False.
    Passes for XS/S unconditionally, and for M+ when challenge has run.
    """
    if size not in _BLOCKED_SIZES:
        return {"blocked": False, "reason": _PASS_REASON}

    if challenge_ran:
        return {"blocked": False, "reason": _PASS_REASON}

    return {"blocked": True, "reason": _BLOCK_REASON.format(size=size)}
