"""NFR gate — blocks M+ dev-loop when no NFR Decision Block is present."""
from __future__ import annotations

_BLOCKED_SIZES = {"M", "L", "XL"}
_PASS_REASON = ""
_BLOCK_REASON = (
    "Size {size} task requires an NFR Decision Block before implementation. "
    "Run `/nfr-check` first, then pass the output as `nfr_decision_block`."
)


def check_nfr_gate(task: str, size: str, nfr_decision_block: str | None) -> dict:
    """
    Return {"blocked": bool, "reason": str}.

    Blocks when size is M/L/XL AND nfr_decision_block is absent or empty.
    Passes for XS/S unconditionally, and for M+ when a non-empty block is supplied.
    """
    if size not in _BLOCKED_SIZES:
        return {"blocked": False, "reason": _PASS_REASON}

    content = (nfr_decision_block or "").strip()
    if content:
        return {"blocked": False, "reason": _PASS_REASON}

    return {"blocked": True, "reason": _BLOCK_REASON.format(size=size)}
