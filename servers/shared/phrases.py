"""The phrase lists youk matches against text, each defined once.

  CONTRACT_PHRASES         a user message stating a standing rule. Read by the server (which
                           saves it as a contract) and the usage hooks (which count it).
  PUSHBACK_PHRASES         a user message pushing back on the model's last answer. Read by the
                           prompt hook, the correction capture and the reaction classifier.
  LOOP_CORRECTION_PHRASES  wording in a session-end summary that a challenge loop was corrected
                           after it declared itself done. Read by session_end.

PUSHBACK and LOOP_CORRECTION share a few phrases ("you missed") but answer different questions
about different text, so they stay separate. Copies of these lists in other files would drift,
and a rule the server saves but the metrics miss would make the repeat-correction rate wrong;
tests/test_phrases.py fails if a phrase list is defined anywhere else.
"""
from __future__ import annotations

CONTRACT_PHRASES = [
    "always ", "never ", "from now on", "remember to", "make sure you",
    "every time", "don't forget", "commit format", "test after", "before committing",
    # Implicit corrections: softer phrases that indicate a behavioral contract
    "don't do that", "wrong approach", "instead of doing", "do it this way",
    "stop doing", "use this instead", "the right way is",
]


def has_contract_phrase(prompt: str) -> bool:
    lower = prompt.lower()
    return any(phrase in lower for phrase in CONTRACT_PHRASES)


PUSHBACK_PHRASES = [
    "you missed", "that's wrong", "not quite", "are you sure", "sure?",
    "what about", "you didn't", "incorrect", "that's not", "wrong approach",
    "is this all", "fight the urge", "fight your", "directionally biased",
    "you're missing", "still missing", "not complete", "incomplete",
    "you forgot", "what else", "anything else", "keep going", "go deeper",
    "that's not all", "is that all", "is this it", "only this",
]

LOOP_CORRECTION_PHRASES = [
    "you missed", "what about", "unchallenged", "you didn't consider",
    "still not at floor", "loop not dry", "not at floor", "still not done",
    "angle unchallenged", "you forgot", "missed this",
]


def is_pushback(prompt: str) -> bool:
    """True if the prompt pushes back on the model's prior response."""
    lower = prompt.lower().strip()
    # Short prompts: a phrase anywhere counts.
    if len(lower) <= 80:
        return any(phrase in lower for phrase in PUSHBACK_PHRASES)
    # Longer prompts: only a phrase in the first 60 characters counts, which avoids a false
    # positive where "are you sure" appears inside a pasted code snippet.
    return any(phrase in lower[:60] for phrase in PUSHBACK_PHRASES)


def has_loop_correction(summary: str) -> bool:
    """True if a session-end summary contains post-verdict correction language."""
    lower = summary.lower()
    return any(phrase in lower for phrase in LOOP_CORRECTION_PHRASES)
