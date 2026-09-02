"""Tests for the deterministic A/B-exposure reaction classifier.

Covers Phase 1 of ~/.claude/plans/zany-squishing-crayon.md: `autonomy_depth` is
Claude self-grading its own read of the conversation, with nothing checking that
judgment against the user's actual next message. This classifier is the
independent check — pure pattern matching, no LLM call, no session state.

The correctness bar is narrow on purpose: same input always produces the same
bucket, and the four buckets are mutually exclusive by construction (an
if/elif chain, not independent boolean checks) so no message can be double
counted in the exposure log.
"""
from __future__ import annotations

from reaction_classifier import classify_reaction, REACTIONS


class TestClassifyReactionCorrection:
    def test_detects_known_correction_phrase(self):
        assert classify_reaction("that's wrong, you missed the edge case") == "correction"

    def test_correction_wins_over_a_new_task_start(self):
        """A correction that also kicks off new work is still a correction —
        the more informative signal takes priority."""
        msg = "you missed something, let's add a retry path for this"
        assert classify_reaction(msg) == "correction"

    def test_case_insensitive(self):
        assert classify_reaction("YOU MISSED the null check") == "correction"


class TestClassifyReactionAcknowledgment:
    def test_detects_short_confirmation(self):
        assert classify_reaction("sounds good, thanks") == "acknowledgment"

    def test_detects_lgtm(self):
        assert classify_reaction("lgtm") == "acknowledgment"


class TestClassifyReactionRedirect:
    def test_detects_new_task_start_with_no_correction_or_ack(self):
        msg = "let's add a new endpoint for exporting reports"
        assert classify_reaction(msg) == "redirect"

    def test_short_task_like_message_below_length_floor_is_not_redirect(self):
        """A bare 'add x' with no other content is too short to confidently
        call a redirect rather than noise — falls to the safe default."""
        assert classify_reaction("add x") == "silent_proceed"


class TestClassifyReactionSilentProceed:
    def test_empty_string_is_silent_proceed(self):
        assert classify_reaction("") == "silent_proceed"

    def test_whitespace_only_is_silent_proceed(self):
        assert classify_reaction("   \n  ") == "silent_proceed"

    def test_short_neutral_reply_is_silent_proceed(self):
        assert classify_reaction("ok") == "silent_proceed"

    def test_unrelated_short_reply_is_silent_proceed(self):
        assert classify_reaction("what time is it") == "silent_proceed"


class TestClassifyReactionIsDeterministic:
    def test_same_input_always_same_bucket(self):
        msg = "that's not quite right, can you also fix the header"
        results = {classify_reaction(msg) for _ in range(20)}
        assert len(results) == 1

    def test_result_is_always_a_declared_bucket(self):
        for msg in ["", "ok", "you missed it", "lgtm", "let's build a new module"]:
            assert classify_reaction(msg) in REACTIONS
