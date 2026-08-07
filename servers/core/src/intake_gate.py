"""Intake gate — blocks M+ dev-loop when intake was required but has not run.

Task 1.7. The last direction-gate that was enforced only by prose: optimize_intent
returns intake_required=True on solution-language input, and CLAUDE.md tells the model
to run intake — but nothing tool-level enforced it, so under pressure it could be skipped.
This mirrors check_nfr_gate / check_challenge_gate exactly: a machine-checkable field the
routing loop reads, not prose guidance. It is the first concrete instance of the
read-time-verification layer (the same principle applied to the intake direction-gate).
"""
from __future__ import annotations

_BLOCKED_SIZES = {"M", "L", "XL"}
_PASS_REASON = ""
_BLOCK_REASON = (
    "Size {size} task had intake_required=True from optimize_intent but intake has not "
    "run this session. Run the intake protocol (skills/intake), then call "
    "mark_intake_ran(task), then re-check this gate. Never route while intake is owed."
)


def check_intake_gate(
    task: str, size: str, intake_required: bool, intake_has_run: bool
) -> dict:
    """
    Return {"blocked": bool, "reason": str}.

    Blocks when size is M/L/XL AND intake_required is True AND intake_has_run is False.
    Passes for XS/S unconditionally, when intake was not required, or when intake already
    ran. Mirrors check_nfr_gate's shape so the routing loop treats all three gates
    identically.
    """
    if size not in _BLOCKED_SIZES:
        return {"blocked": False, "reason": _PASS_REASON}

    if not intake_required:
        return {"blocked": False, "reason": _PASS_REASON}

    if intake_has_run:
        return {"blocked": False, "reason": _PASS_REASON}

    return {"blocked": True, "reason": _BLOCK_REASON.format(size=size)}
