"""
Ceremony sequencer — tracks gate order per session slug.

Records which gates fired and when. Warns when ordering rules are violated:
- nfr must not fire before challenge on M+ tasks
- challenge_gate must not fire before nfr on M+ tasks

All functions are fail-silent so a sequencer failure never blocks routing.
State written to state/{slug}/ceremony-sequence.json (array of {gate, fired_at}).
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

_DEFAULT_ROOT = Path("/youk")

_SMALL_SIZES = {"XS", "S"}

_ORDER_RULES: dict[str, str] = {
    # gate_about_to_fire -> prerequisite gate
    "nfr": "challenge",
    "challenge_gate": "nfr",
}

_WARNINGS: dict[str, str] = {
    "nfr": (
        "nfr_check fired before challenge — "
        "ceremony order should be challenge → nfr → gates → dev-loop. "
        "Run challenge first."
    ),
    "challenge_gate": (
        "challenge_gate fired before nfr_check — "
        "ceremony order should be challenge → nfr → gates → dev-loop. "
        "Run nfr_check first."
    ),
}


def _seq_file(slug: str, youk_root: Path) -> Path:
    return youk_root / "state" / "sessions" / slug / "ceremony-sequence.json"


def _load_sequence(slug: str, youk_root: Path) -> list[dict]:
    f = _seq_file(slug, youk_root)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text())
    except Exception:
        return []


def _save_sequence(seq: list[dict], slug: str, youk_root: Path) -> None:
    f = _seq_file(slug, youk_root)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(seq))
    except Exception:
        pass


def record_gate(
    gate_name: str,
    slug: str,
    youk_root: Path | None = None,
) -> None:
    """Append gate_name to the ceremony sequence for this slug (idempotent)."""
    if not slug:
        return
    root = youk_root or _DEFAULT_ROOT
    seq = _load_sequence(slug, root)
    if any(e.get("gate") == gate_name for e in seq):
        return
    seq.append({"gate": gate_name, "fired_at": datetime.utcnow().isoformat()})
    _save_sequence(seq, slug, root)


def check_order(
    gate_about_to_fire: str,
    slug: str,
    size: str,
    youk_root: Path | None = None,
) -> dict:
    """
    Check whether the prerequisite gate has already fired for this slug.

    Returns {"ok": True, "warning": None} when ordering is satisfied.
    Returns {"ok": False, "warning": str} when the prerequisite is missing.
    XS/S tasks always return ok=True (no ceremony required).
    """
    if size.upper() in _SMALL_SIZES or not slug:
        return {"ok": True, "warning": None}

    prereq = _ORDER_RULES.get(gate_about_to_fire)
    if prereq is None:
        return {"ok": True, "warning": None}

    root = youk_root or _DEFAULT_ROOT
    seq = _load_sequence(slug, root)
    fired_gates = {e.get("gate") for e in seq}

    if prereq in fired_gates:
        return {"ok": True, "warning": None}

    return {"ok": False, "warning": _WARNINGS.get(gate_about_to_fire, f"Prerequisite '{prereq}' has not fired.")}


def dev_loop_registered(
    slug: str,
    youk_root: Path | None = None,
) -> bool:
    """Return True if dev-loop has been recorded in the ceremony sequence."""
    if not slug:
        return False
    root = youk_root or _DEFAULT_ROOT
    seq = _load_sequence(slug, root)
    return any(e.get("gate") == "dev-loop" for e in seq)


def get_sequence(
    slug: str,
    youk_root: Path | None = None,
) -> list[str]:
    """Return ordered list of gate names recorded for this slug."""
    if not slug:
        return []
    root = youk_root or _DEFAULT_ROOT
    return [e.get("gate", "") for e in _load_sequence(slug, root)]
