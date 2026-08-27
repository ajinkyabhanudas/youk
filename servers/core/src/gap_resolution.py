"""Re-verify recorded gaps against current skill content before surfacing them.

The open half of youk's self-improvement loop. Gaps are recorded, proposals are
generated, and nothing ever checks whether the gap still exists. So a gap fixed in July
is still reported in August, the queue fills with things already done, and people stop
reading it. Measured on real data: 4 of 8 live gap signals were for gaps already
addressed, and 12 of 35 proposals had been closed as stale or duplicate.

youk diagnosed this about itself. A CLOSED proposal from 2026-07-15 reads: "Third in a
series of duplicate compaction proposals. Root cause: self_heal re-generates proposals
without checking existing skill content first." The finding was correct and there was no
mechanism to route it back into behaviour, so it died in a status string. This module is
that mechanism.

Deliberately asymmetric. A gap wrongly called resolved disappears silently and the real
defect persists unseen; a gap wrongly called open costs one line of noise. So the bar
for RESOLVED is high, and resolved gaps are reported in their own list rather than
dropped — the reader can disagree with the classification, which they cannot do with
something that was deleted.

Deterministic: token overlap against the skill's current text. No model call.
"""
from __future__ import annotations

import re
from pathlib import Path

# Substantive tokens only. Short words and generic verbs match everything and would push
# live gaps into RESOLVED, which is the failure direction that hides real defects.
_STOPWORDS = frozenset({
    "should", "would", "could", "there", "their", "которая", "before", "after",
    "when", "then", "than", "this", "that", "with", "from", "into", "only",
    "never", "always", "still", "which", "while", "where", "because", "about",
    "skill", "gap", "check", "checks", "checked", "session", "sessions",
})

# Fraction of a gap's distinctive tokens that must appear in the skill text before it is
# called resolved. Set high on purpose: at 0.5 unrelated gaps in the same domain matched
# each other, since skills about caching all mention caching.
_RESOLVED_THRESHOLD = 0.75

# Below this many distinctive tokens a gap carries too little signal to classify either
# way, and is left open rather than guessed at.
_MIN_TOKENS = 3


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z_][a-z_0-9]{4,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def classify_gap(gap_text: str, skill_text: str) -> tuple[str, float]:
    """Return (verdict, overlap) where verdict is RESOLVED | OPEN | UNKNOWN.

    UNKNOWN means the gap text was too thin to judge. It is reported as open, because
    the cost of a false OPEN is a line of noise and the cost of a false RESOLVED is a
    real defect nobody sees again.
    """
    gap_tokens = _tokens(gap_text)
    if len(gap_tokens) < _MIN_TOKENS:
        return "UNKNOWN", 0.0
    if not skill_text.strip():
        return "OPEN", 0.0
    present = _tokens(skill_text)
    overlap = len(gap_tokens & present) / len(gap_tokens)
    return ("RESOLVED" if overlap >= _RESOLVED_THRESHOLD else "OPEN"), round(overlap, 2)


def reverify_gap_signals(signals: list[dict], skills_dir: Path) -> dict:
    """Split recorded gap signals into still-open and likely-resolved.

    signals: [{"skill": name, "gaps": [text, ...]}] as self_heal produces.

    Returns {open_signals, resolved, unverifiable, checked}. `resolved` entries carry the
    skill, the gap and the overlap that produced the verdict, so a wrong call is visible
    and arguable rather than silent.

    Never raises: a health check must not be able to fail a session.
    """
    open_signals: list[dict] = []
    resolved: list[dict] = []
    unverifiable: list[dict] = []
    checked = 0

    for signal in signals or []:
        name = signal.get("skill", "")
        gaps = signal.get("gaps", []) or []
        skill_md = skills_dir / name / "SKILL.md"

        try:
            skill_text = skill_md.read_text(errors="ignore") if skill_md.exists() else ""
        except OSError:
            skill_text = ""

        if not skill_text:
            # No skill content to check against. Not the same as resolved: the gap may be
            # real and the skill missing entirely, which is itself worth seeing. The
            # signal stays in open_signals as well as being listed here — dropping it
            # would hide a live gap behind an inability to classify it, which is the
            # exact asymmetry this module is built to avoid.
            unverifiable.append({"skill": name, "gaps": gaps})
            open_signals.append(signal)
            continue

        still_open: list[str] = []
        for gap in gaps:
            checked += 1
            verdict, overlap = classify_gap(gap, skill_text)
            if verdict == "RESOLVED":
                resolved.append({"skill": name, "gap": gap, "overlap": overlap})
            else:
                still_open.append(gap)

        if still_open:
            open_signals.append({**signal, "gaps": still_open})

    return {
        "open_signals": open_signals,
        "resolved": resolved,
        "unverifiable": unverifiable,
        "checked": checked,
    }


def resolution_summary(result: dict) -> str:
    """One line for the health report, or empty when nothing was reclassified."""
    resolved = result.get("resolved", [])
    if not resolved:
        return ""
    names = sorted({r["skill"] for r in resolved})
    return (
        f"{len(resolved)} recorded gap(s) across {len(names)} skill(s) appear already "
        f"addressed in current skill content ({', '.join(names[:3])}"
        + (f", +{len(names) - 3} more" if len(names) > 3 else "")
        + "). Re-verified rather than re-reported; disagree by re-opening the gap."
    )
