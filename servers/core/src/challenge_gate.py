"""Challenge gate — blocks M+ dev-loop when challenge skill has not run for this task."""
from __future__ import annotations

_BLOCKED_SIZES = {"M", "L", "XL"}
_PASS_REASON = ""
_BLOCK_REASON = (
    "Size {size} task requires challenge skill before implementation. "
    "Run challenge (route_to_skill('challenge', task)) first, then call "
    "mark_challenge_ran(), then re-call check_challenge_gate."
)


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
