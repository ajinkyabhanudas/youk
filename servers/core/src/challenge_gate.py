"""Challenge gate — blocks M+ dev-loop when challenge skill has not run for this task."""
from __future__ import annotations

from pathlib import Path

_BLOCKED_SIZES = {"M", "L", "XL"}
_PASS_REASON = ""
_BLOCK_REASON = (
    "Size {size} task requires challenge skill before implementation. "
    "Run challenge (route_to_skill('challenge', task)) first, then call "
    "mark_challenge_ran(task, angles_checked=[...], mode=<mode>), then re-call check_challenge_gate."
)

# Required angles per challenge mode (frozen literals — the fallback + test baseline).
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

_REGISTRY_FILE = Path("/youk/state/revisable-sets.json")


def get_convergence_angles(registry_path: Path | None = None) -> tuple[set[str], bool, bool]:
    """Return the live _SEVEN_CONVERGENCE set from the registry when enrolled.

    Returns (angles, enrolled, degraded):
      - angles: the set to use for "full" mode validation
      - enrolled: True if _SEVEN_CONVERGENCE is present in the registry
      - degraded: True if the set was enrolled but the read failed (file missing/corrupt)

    Falls back to the frozen literal when not enrolled (enrolled=False, degraded=False).
    """
    path = registry_path or _REGISTRY_FILE
    try:
        import json
        if not path.exists():
            return _SEVEN_CONVERGENCE, False, False
        raw = json.loads(path.read_text())
        if "_SEVEN_CONVERGENCE" not in raw:
            return _SEVEN_CONVERGENCE, False, False
        elements = set(raw["_SEVEN_CONVERGENCE"].get("elements", {}).keys())
        if not elements:
            # Enrolled but empty — treat as degraded (enrollment ran but something is wrong).
            return _SEVEN_CONVERGENCE, True, True
        return elements, True, False
    except Exception:
        # File exists and set was enrolled (we know because _SEVEN_CONVERGENCE was in raw
        # before the exception, or we cannot tell) — use degraded sentinel.
        return _SEVEN_CONVERGENCE, True, True


def validate_angles(angles_checked: list[str], mode: str,
                    registry_path: Path | None = None) -> dict:
    """Validate that angles_checked covers all required angles for the given mode.

    For "full" mode: reads _SEVEN_CONVERGENCE from the live registry when enrolled,
    falls back to the frozen literal otherwise. The result includes `enrolled` and
    `degraded` fields so callers can distinguish live vs. fallback.

    Returns {"valid": bool, "missing_angles": [...], "enrolled": bool, "degraded": bool}.
    Unknown modes fall back to "full" required set.
    """
    if mode == "full" or mode not in REQUIRED_ANGLES:
        live_convergence, enrolled, degraded = get_convergence_angles(registry_path)
        required = _FOUR_LENSES | live_convergence
    else:
        required = REQUIRED_ANGLES[mode]
        enrolled, degraded = False, False

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
            "enrolled": enrolled,
            "degraded": degraded,
        }
    return {"valid": True, "missing_angles": [], "enrolled": enrolled, "degraded": degraded}


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
