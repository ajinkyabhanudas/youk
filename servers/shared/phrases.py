"""Phrases that mark a user message as stating a standing rule.

One list, read by the server (which saves the rule as a contract) and by the usage hooks
(which count the message as a correction event). Two copies would drift, and a rule the
server saves but the metrics miss would make the repeat-correction rate wrong.
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
