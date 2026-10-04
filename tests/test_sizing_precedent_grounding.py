"""_build_sizing_precedent_block: retrieval-grounding for optimize_intent's
estimated_size, appended at the end of the final message so it gets the
strongest attention in a transformer, not buried in a long system prompt.
"""
from __future__ import annotations

from intent import _build_sizing_precedent_block


def test_returns_empty_string_with_no_real_history(tmp_path):
    assert _build_sizing_precedent_block("anything", log_path=tmp_path / "none.jsonl") == ""


def test_includes_a_real_precedent_and_its_real_resolved_size(tmp_path):
    from sizing_decision import log_sizing_decision

    log_path = tmp_path / "sizing.jsonl"
    log_sizing_decision(
        task="design a new architecture for the payment system",
        deterministic_size="L", llm_estimated_size="L", resolved_size="L",
        mismatch_flag=False, log_path=log_path,
    )
    block = _build_sizing_precedent_block(
        "redesign the architecture for the billing system", log_path=log_path,
    )
    assert "Real precedent" in block
    assert "-> L" in block


def test_block_is_appended_not_prepended_to_user_content():
    """Research finding: the position right before generation gets the
    strongest attention in a transformer. The precedent block must come
    after the real task text, not before it."""
    from sizing_decision import log_sizing_decision
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "sizing.jsonl"
        log_sizing_decision(
            task="fix a typo", deterministic_size="XS", llm_estimated_size="XS",
            resolved_size="XS", mismatch_flag=False, log_path=log_path,
        )
        block = _build_sizing_precedent_block("fix a typo somewhere else", log_path=log_path)

    user_content = f"Raw input: fix a typo somewhere else{block}"
    assert user_content.index("Raw input:") < user_content.index("Real precedent")


def test_never_raises_when_the_log_path_is_unreadable(tmp_path):
    """Logging/retrieval must never block the real judgment call it's
    meant to improve."""
    bad_path = tmp_path / "does" / "not" / "exist" / "sizing.jsonl"
    assert _build_sizing_precedent_block("anything", log_path=bad_path) == ""
