"""Voice fingerprint — measure prose against a developer's voice profile.

Library API (no CLI). Ported from knowledge/imported/voice-fingerprint/stylecheck.py.
stdlib only — no external deps. Per-developer isolation enforced by callers
(profile + corpus stay machine-local, never committed).

Two entry points:
  profile_corpus(texts)       → measured_targets dict (from a list of text samples)
  check_text(text, profile)   → {tells_hard, tells_soft, target_pass, gate}

Gate values: "BLOCKED" (hard tell present) | "REVIEW" (soft tells) | "CLEAR"
"""
from __future__ import annotations

import re
import statistics as _st
from collections import Counter
from typing import Any

# ── Hard tells — one instance is one too many ──────────────────────────────────
ABSOLUTE: dict[str, str] = {
    "em_dash":          r"—",
    "curly_quote":      r"[“”‘’]",
    "chatbot_artifact": r"\b(I hope this helps|Great question|Certainly!|Of course!|feel free to reach out|let me know if you)\b",
    "cutoff_disclaimer": r"\b(as of my last|up to my last training|based on available information|while specific details are (limited|scarce))\b",
    "signposting":      r"\b(let's dive in|let's explore|let's break (this|it) down|here's what you need to know|without further ado)\b",
    "not_just_pivot":   r"\b(not just|isn't just|it's not merely|not only)\b[^.]{0,60}\b(it's|but)\b",
    "authority_trope":  r"\b(the real question is|at its core|what really matters|the heart of the matter|the deeper issue)\b",
}

# ── Graded tells — frequency-dependent; threshold = hits per 1000 words ────────
GRADED: dict[str, float] = {
    "delve": 0.3, "underscore": 0.3, "tapestry": 0.2, "testament": 0.3,
    "pivotal": 0.3, "crucial": 1.2, "key": 3.0, "robust": 0.8,
    "leverage": 0.5, "seamless": 0.4, "intricate": 0.4, "nuanced": 0.5,
    "holistic": 0.3, "transformative": 0.3, "landscape": 0.5, "vibrant": 0.4,
    "showcase": 0.4, "foster": 0.5, "enhance": 1.0, "utilize": 0.3,
    "streamline": 0.4, "empower": 0.4, "multifaceted": 0.2, "palpable": 0.2,
    "align": 1.0, "additionally": 0.8, "moreover": 0.6, "furthermore": 0.6,
    "highlight": 1.0, "valuable": 0.8, "actually": 1.5, "unprecedented": 0.3,
}

_PARTICIPLE = re.compile(
    r"[,;]\s+(highlighting|underscoring|emphasizing|ensuring|reflecting|"
    r"symbolizing|contributing|cultivating|fostering|encompassing|showcasing|"
    r"marking|setting|shaping)\b",
    re.I,
)
_COPULA_DODGE = re.compile(
    r"\b(serves as|stands as|functions as|boasts|is home to|represents a|marks a)\b",
    re.I,
)
_RULE_OF_THREE = re.compile(r"\b\w+, \w+,? and \w+\b", re.I)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CONTRACTIONS = re.compile(r"\b\w+['’](?:s|t|re|ve|ll|d|m)\b")
_FIRST_PERSON = re.compile(r"\b(I|me|my|mine|I'm|I've|I'd|I'll)\b", re.I)
_CONNECTIVES = [
    "and", "but", "so", "because", "although", "though", "while",
    "however", "yet", "since", "unless", "whereas", "if", "when",
]

_MIN_CORPUS_WORDS = 1500


# ── Internal helpers ───────────────────────────────────────────────────────────

def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


def _opener_class(s: str) -> str:
    w = re.sub(r"^[^\w]+", "", s).split()
    if not w:
        return "other"
    first = w[0].lower().strip(",")
    if first in ("and", "but", "so", "or", "yet", "because"):
        return "conjunction"
    if first in ("although", "though", "while", "if", "when", "since",
                 "after", "before", "unless", "whereas", "given"):
        return "subordinate"
    if first.endswith("ly"):
        return "adverb"
    return "subject"


def _measure(text: str) -> dict[str, Any]:
    sents = _sentences(text)
    words = re.findall(r"[\w']+", text)
    n = max(len(words), 1)
    lengths = [len(s.split()) for s in sents] or [0]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    para_lens = [len(_sentences(p)) for p in paras] or [0]
    openers = Counter(_opener_class(s) for s in sents)
    conn: Counter = Counter()
    low = " " + " ".join(w.lower() for w in words) + " "
    for c in _CONNECTIVES:
        conn[c] = low.count(f" {c} ")
    mean_len = _st.mean(lengths)
    return {
        "words": n,
        "sentences": len(sents),
        "mean_sentence": round(mean_len, 1),
        "sd_sentence": round(_st.pstdev(lengths), 2),
        "cv_sentence": round(_st.pstdev(lengths) / mean_len, 2) if mean_len else 0.0,
        "mean_para_sentences": round(_st.mean(para_lens), 1),
        "contractions_per_100w": round(100 * len(_CONTRACTIONS.findall(text)) / n, 1),
        "first_person_per_100w": round(100 * len(_FIRST_PERSON.findall(text)) / n, 1),
        "commas_per_sentence": round(text.count(",") / max(len(sents), 1), 2),
        "openers_pct": {k: round(100 * v / max(len(sents), 1)) for k, v in openers.most_common()},
        "top_connectives": [w for w, c in conn.most_common(6) if c],
        "punct_per_1000w": {
            "colon":     round(1000 * text.count(":") / n, 1),
            "semicolon": round(1000 * text.count(";") / n, 1),
            "paren":     round(1000 * text.count("(") / n, 1),
            "emdash":    round(1000 * text.count("—") / n, 1),
        },
    }


def _tells(text: str) -> tuple[list[str], list[str]]:
    words = max(len(re.findall(r"[\w']+", text)), 1)
    hard: list[str] = []
    soft: list[str] = []

    for name, pat in ABSOLUTE.items():
        hits = re.findall(pat, text, re.I)
        if hits:
            hard.append(f"{name}: {len(hits)}")

    for word, thresh in GRADED.items():
        count = len(re.findall(r"\b" + word + r"\w{0,3}\b", text, re.I))
        rate = 1000 * count / words
        if count and rate > thresh:
            soft.append(f"{word}: {count}x ({rate:.1f}/1k, limit {thresh})")

    for label, pattern, limit in (
        ("participle_padding", _PARTICIPLE, 1.0),
        ("copula_avoidance",   _COPULA_DODGE, 1.0),
        ("rule_of_three",      _RULE_OF_THREE, 4.0),
    ):
        count = len(pattern.findall(text))
        rate = 1000 * count / words
        if rate > limit:
            soft.append(f"{label}: {count}x ({rate:.1f}/1k, limit {limit})")

    return hard, soft


# ── Public API ─────────────────────────────────────────────────────────────────

def profile_corpus(texts: list[str]) -> dict[str, Any]:
    """Measure a list of text samples and return a targets dict.

    Joins all texts, measures the aggregate. Returns measured targets plus
    a confidence field: "low" if below 1500 words (profile unreliable),
    "medium" up to 5000, "high" above.

    The returned dict is the profile passed to check_text().
    """
    joined = "\n\n".join(texts)
    m = _measure(joined)
    words = m["words"]

    if words < _MIN_CORPUS_WORDS:
        confidence = "low"
    elif words < 5000:
        confidence = "medium"
    else:
        confidence = "high"

    cv = m["cv_sentence"]
    return {
        "words": words,
        "confidence": confidence,
        "cv_sentence": cv,
        "cv_band": (round(cv * 0.8, 2), round(cv * 1.2, 2)),
        "mean_sentence": m["mean_sentence"],
        "contractions_per_100w": m["contractions_per_100w"],
        "first_person_per_100w": m["first_person_per_100w"],
        "commas_per_sentence": m["commas_per_sentence"],
        "mean_para_sentences": m["mean_para_sentences"],
        "openers_pct": m["openers_pct"],
        "top_connectives": m["top_connectives"],
        "punct_per_1000w": m["punct_per_1000w"],
    }


def check_text(text: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check text for AI-tells and optionally compare against a voice profile.

    Returns:
      tells_hard:   list[str]  — absolute tells (em-dash, chatbot artifacts, etc.)
      tells_soft:   list[str]  — graded tells exceeding frequency thresholds
      target_pass:  dict       — per-metric pass/fail vs profile (empty if no profile)
      gate:         str        — "BLOCKED" | "REVIEW" | "CLEAR"

    gate logic:
      BLOCKED  — any hard tell present (regardless of profile confidence)
      REVIEW   — soft tells present, or target_pass has any FAIL
      CLEAR    — no hard tells, no soft tells, all targets pass (or no profile)

    When profile["confidence"] == "low": target comparison runs but gate never
    upgrades to BLOCKED from target failures alone — thin corpus enforces soft only.
    """
    hard, soft = _tells(text)
    m = _measure(text)

    target_pass: dict[str, str] = {}
    if profile:
        # CV band
        lo, hi = profile.get("cv_band", (0.0, 999.0))
        cv = m["cv_sentence"]
        target_pass["cv_sentence"] = "PASS" if lo <= cv <= hi else "FAIL"

        # Contractions — allow ±max(1.5, 35% of target)
        for key in ("contractions_per_100w", "first_person_per_100w"):
            target = profile.get(key)
            if target is not None:
                tolerance = max(1.5, 0.35 * target)
                got = m[key]
                target_pass[key] = "PASS" if abs(got - target) <= tolerance else "FAIL"

    # Gate decision
    if hard:
        gate = "BLOCKED"
    elif soft or "FAIL" in target_pass.values():
        # Thin corpus: only soft-enforce (target FAILs don't escalate to BLOCKED)
        gate = "REVIEW"
    else:
        gate = "CLEAR"

    return {
        "tells_hard": hard,
        "tells_soft": soft,
        "target_pass": target_pass,
        "gate": gate,
        "metrics": {
            "cv_sentence": m["cv_sentence"],
            "mean_sentence": m["mean_sentence"],
            "contractions_per_100w": m["contractions_per_100w"],
            "first_person_per_100w": m["first_person_per_100w"],
        },
    }
