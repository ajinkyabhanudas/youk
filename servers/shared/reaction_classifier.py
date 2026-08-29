"""Deterministic classification of a user's reaction to an A/B pilot exposure.

Built for the Phase 1 gap in the nfr-check rationale pilot (see
~/.claude/plans/zany-squishing-crayon.md): `autonomy_depth` is Claude
self-grading its own read of the conversation, with nothing checking that
judgment against the user's actual next message. This module is the
independent check — pure pattern matching on raw text, no LLM call, callable
from the UserPromptSubmit hook where no agent cooperation is available.

Reuses `_CORRECTION_PHRASES` and `_BUILD_SIGNALS` from `youk_hook_utils.py`
rather than reforking them — this module adds only the acknowledgment list
and the 4-bucket decision, not a second phrase taxonomy for the same
underlying signals.
"""
from __future__ import annotations

import sys
from pathlib import Path

_plugin_scripts = Path(__file__).resolve().parents[2] / "plugin" / "scripts"
if str(_plugin_scripts) not in sys.path:
    sys.path.insert(0, str(_plugin_scripts))

from youk_hook_utils import _CORRECTION_PHRASES, _BUILD_SIGNALS  # noqa: E402

REACTIONS = ("correction", "redirect", "acknowledgment", "silent_proceed")

_ACKNOWLEDGMENT_PHRASES = [
    "sounds good", "makes sense", "agreed", "yes exactly", "sgtm", "lgtm",
    "got it", "understood", "ok let's", "okay let's", "yep", "yup, ",
    "that works", "perfect,", "exactly,", "makes sense,", "agreed,",
    "yes, ", "ok, ", "okay, ", "sure, ",
]

_MIN_REDIRECT_LEN = 25


def classify_reaction(user_prompt: str) -> str:
    """Classify the message that immediately follows a logged A/B exposure.

    Order matters: correction checked first (a correction can also start a
    new task, and should count as correction — that's the more informative
    signal). Acknowledgment next (short confirmations). Redirect only once
    neither matches and the message reads like a new task start. Everything
    else — including empty input, short replies, and anything ambiguous —
    is silent_proceed, the deliberate default per the plan.
    """
    lower = user_prompt.lower().strip()
    if not lower:
        return "silent_proceed"

    head = lower[:80]
    if any(phrase in head for phrase in _CORRECTION_PHRASES):
        return "correction"

    if any(phrase in head for phrase in _ACKNOWLEDGMENT_PHRASES):
        return "acknowledgment"

    if len(lower) >= _MIN_REDIRECT_LEN and any(
        signal in head for signal in _BUILD_SIGNALS
    ):
        return "redirect"

    return "silent_proceed"
