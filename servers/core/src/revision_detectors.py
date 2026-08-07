"""LEARN/UNLEARN detectors for the self-revision meta-loop (Task 2).

Connects existing youk signals to the revisable-sets registry:
- LEARN (grow): a recurring gap/unknown_unknown that no current element covers, seen 2+
  times, proposes ADDing an element — after it survives challenge.
- UNLEARN (prune): an element that never fires across a window, or is repeatedly corrected,
  proposes REMOVING it — the anti-bloat mechanism.

These are DETECTORS (propose), not appliers. They return candidates; the caller runs each
through challenge before calling learn_add / unlearn_prune. Autonomous apply + human veto is
the registry's job (revert); this module only surfaces what should change and why.
"""
from __future__ import annotations

from collections import Counter

from revisable_sets import get_set

# A candidate must recur at least this many times before it's proposed (matches the
# existing pattern_trigger "same gap_type 2+" threshold — no new magic number).
_RECURRENCE_THRESHOLD = 2


def detect_grow_candidates(
    set_name: str, recurring_gaps: list[str], path=None
) -> list[dict]:
    """Propose elements to ADD to an enrolled set.

    recurring_gaps: gap/unknown_unknown labels observed this window (may repeat).
    A candidate is proposed when: it recurs >= threshold AND is not already an element.
    Returns [{"element", "driver", "count"}] — each still owes a challenge pass before add.
    """
    rs = get_set(set_name, path=path) if path else get_set(set_name)
    if rs is None:
        return []
    existing = set(rs["elements"])

    counts = Counter(g.strip().lower() for g in recurring_gaps if g.strip())
    candidates = []
    for gap, n in counts.items():
        if n >= _RECURRENCE_THRESHOLD and gap not in existing:
            candidates.append({
                "element": gap,
                "driver": f"recurring_gap x{n}",
                "count": n,
            })
    # Most-recurrent first.
    candidates.sort(key=lambda c: c["count"], reverse=True)
    return candidates


def detect_prune_candidates(
    set_name: str, fire_counts: dict[str, int], corrected: list[str] | None = None,
    path=None,
) -> list[dict]:
    """Propose elements to REMOVE from an enrolled set (anti-bloat).

    fire_counts: element -> times it fired/contributed this window.
    corrected: elements the developer explicitly corrected/rejected.
    A candidate is proposed when an element NEVER fired (count 0) OR was corrected.
    Never proposes pruning to empty (that's the registry's final guard, but we also
    avoid proposing the last element here).
    Returns [{"element", "driver"}] — each still owes a challenge pass before prune.
    """
    rs = get_set(set_name, path=path) if path else get_set(set_name)
    if rs is None:
        return []
    elements = list(rs["elements"])
    corrected_set = {c.strip().lower() for c in (corrected or [])}

    candidates = []
    for el in elements:
        fires = fire_counts.get(el, 0)
        if fires == 0:
            candidates.append({"element": el, "driver": "never_fired"})
        elif el.lower() in corrected_set:
            candidates.append({"element": el, "driver": "repeatedly_corrected"})

    # Don't propose pruning every element — leave at least one even if all look dead
    # (a fully-dead set is a signal to review the set, not to empty it).
    if len(candidates) >= len(elements) and elements:
        candidates = candidates[:-1]
    return candidates
