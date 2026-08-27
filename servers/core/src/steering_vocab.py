"""Steering vocabulary — youk learns how to talk to Claude in Claude's own terms (Task 3).

A quality label ("rigorous", "thorough", "L9", "principal") is a compressed pointer to a
region of behavior. Prompting with the label asks the model to reconstruct that region from
a stereotype — lossy. This module records the CONCRETE BEHAVIORS a label decomposes into,
learned from what actually produced verified-good work, so youk can steer with the behaviors
instead of the adjective.

Built ON the self-revision meta-loop (revisable_sets) — steering-vocabulary is its second
enrolled instance, not new machinery. Each label is a set; its elements are behavior
decompositions with a CONFIDENCE tag.

CONFIDENCE MODEL (the tagged-by-confidence design — strictness is read-time, not write-time):
  verified  — the work this decomposition steered passed an objective check (tests/bug real)
  approved  — the user accepted the result, but it wasn't objectively verified
  corrected — the user corrected this decomposition (negative signal; weight → 0)
Nothing is rejected at write time (so the vocab fills fast, no cold-start problem). Strictness
lives in the read-time weight, which keeps the strict-vs-loose knob TUNABLE with real data
rather than baking an irreversible reject into the write path.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

YOUK_ROOT = Path("/youk")
_VOCAB_FILE = YOUK_ROOT / "state" / "steering-vocab.json"

# Read-time weights per confidence tier. This is the strictness knob — change these to make
# the vocabulary stricter (down-weight approved) or looser, WITHOUT losing any recorded data.
_CONFIDENCE_WEIGHT = {
    "verified": 1.0,
    "approved": 0.4,
    "corrected": 0.0,
}


def _load(path: Path | None = None) -> dict:
    path = path if path is not None else _VOCAB_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save(vocab: dict, path: Path | None = None) -> None:
    path = path if path is not None else _VOCAB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vocab, indent=1))


def record_decomposition(
    label: str,
    behavior: str,
    task_context: str,
    confidence: str = "approved",
    path: Path | None = None,
) -> dict:
    """Record that `label` decomposed into `behavior` for a task like `task_context`.

    confidence: verified | approved | corrected. Nothing is rejected — a decomposition is
    always recorded with its provenance; quality is applied at read time via the weight.
    A repeat of the same (label, behavior) UPGRADES confidence to the best seen and bumps
    its observation count (a decomposition seen verified twice is stronger evidence).
    """
    path = path if path is not None else _VOCAB_FILE
    if confidence not in _CONFIDENCE_WEIGHT:
        return {"ok": False, "reason": f"confidence must be one of {list(_CONFIDENCE_WEIGHT)}"}

    vocab = _load(path)
    label_entry = vocab.setdefault(label, {})
    existing = label_entry.get(behavior)
    now = time.time()

    if existing is None:
        label_entry[behavior] = {
            "confidence": confidence,
            "count": 1,
            "contexts": [task_context],
            "updated_at": now,
        }
    else:
        # Upgrade confidence to the strongest observed (verified > approved > corrected),
        # unless the new signal is a correction — a correction always wins (it's the veto).
        order = {"corrected": 0, "approved": 1, "verified": 2}
        if confidence == "corrected":
            existing["confidence"] = "corrected"
        elif order[confidence] > order[existing["confidence"]]:
            existing["confidence"] = confidence
        existing["count"] += 1
        if task_context not in existing["contexts"]:
            existing["contexts"].append(task_context)
        existing["updated_at"] = now

    _save(vocab, path)
    return {"ok": True, "label": label, "behavior": behavior,
            "confidence": label_entry[behavior]["confidence"]}


def get_steering(label: str, path: Path | None = None, min_weight: float = 0.1) -> dict:
    """Return the learned behavior decompositions for `label`, weighted by confidence and
    observation count, strongest first. Corrected (weight 0) and anything below min_weight
    are excluded — that is the read-time filter (the tunable strictness knob).

    Returns {"label", "behaviors": [{behavior, confidence, weight, count}], "learned": bool}.
    A label with no verified/approved decompositions returns learned=False — the caller then
    elicits a fresh decomposition from the model (point-of-use) rather than steer with a
    stereotype.
    """
    path = path if path is not None else _VOCAB_FILE
    vocab = _load(path)
    entries = vocab.get(label, {})
    scored = []
    for behavior, meta in entries.items():
        base = _CONFIDENCE_WEIGHT.get(meta["confidence"], 0.0)
        # Repeated observations strengthen a decomposition, with diminishing returns.
        weight = base * (1 + min(meta["count"] - 1, 4) * 0.1)
        if weight >= min_weight:
            scored.append({
                "behavior": behavior,
                "confidence": meta["confidence"],
                "weight": round(weight, 3),
                "count": meta["count"],
            })
    scored.sort(key=lambda s: s["weight"], reverse=True)
    return {"label": label, "behaviors": scored, "learned": bool(scored)}
