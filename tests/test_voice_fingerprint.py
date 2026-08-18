"""Voice fingerprint — unit tests for profile_corpus and check_text.

Load-bearing properties:
- profile_corpus returns stable, deterministic measurements on a fixture
- confidence reflects corpus size (low / medium / high)
- check_text catches hard tells → BLOCKED regardless of profile
- check_text catches soft tells → REVIEW
- check_text returns CLEAR on clean prose
- target comparison (CV band, contractions) works correctly
- low-confidence profile: target FAIL produces REVIEW, never BLOCKED
- capture_voice_sample: appends, skips short/slash, silent-fails
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# voice_fingerprint is in servers/core/src (conftest puts it on sys.path)
from voice_fingerprint import check_text, profile_corpus

# ── Fixtures ───────────────────────────────────────────────────────────────────

# A clean ~350-word corpus excerpt using straight ASCII quotes only, no AI tells.
_CLEAN_CORPUS = (
    "We found three models that disagreed on every synthetic benchmark but converged on the "
    "real evaluation set. That is not a coincidence. The synthetic benchmarks were built from "
    "the same distribution as the training data, so they measure memorization, not transfer. "
    "The real set was drawn from a different domain entirely. "
    "This happens more than people admit. A model can score 94% on one benchmark and fail the "
    "simplest out-of-distribution probe. The number becomes a shield. Teams stop asking what "
    "it measures and start optimizing for it directly, which makes it measure even less. "
    "What we did instead: built the evaluation set before we trained the model. Fixed the "
    "criteria first, then collected data. It took two extra weeks and we argued about it the "
    "whole time. Every model shipped since has held up in production. "
    "The lesson is not that benchmarks are useless. It is that a benchmark you control is a "
    "benchmark you can game, and a benchmark you can game will be gamed, whether you intend it "
    "or not. The fix is boring: evaluate on data no one touched during training, with criteria "
    "set before the results are visible. "
    "One more thing. We run the same evaluation every quarter on the production model, not "
    "just at release. Models drift. Distributions shift. A score from six months ago tells you "
    "nothing about what the model does today. Continuous evaluation is the only kind that "
    "matters for systems that stay deployed. "
)

# Enough copies to cross 1500/5000 word thresholds for confidence tests.
# _CLEAN_CORPUS is ~244 words; x7 = ~1708w (medium), x21 = ~5124w (high).
_CORPUS_MEDIUM = _CLEAN_CORPUS * 7
_CORPUS_HIGH = _CLEAN_CORPUS * 21

# A short clean text with no tells (straight quotes, no em-dash)
_CLEAN_SHORT = (
    "The build failed on the integration test. I checked the logs and traced it to the "
    "migration step. The schema change was not applied before the fixture ran. Fixed by "
    "reordering the test setup steps."
)

_EM_DASH_TEXT = "This is good — but that is wrong."
_NOT_JUST_TEXT = "It's not just a style problem, but it's a signal."
_GRADED_TEXT = "Additionally, the holistic and nuanced approach is transformative. " * 5


# ── profile_corpus ─────────────────────────────────────────────────────────────

class TestProfileCorpus:
    def test_stable_on_fixture(self):
        p1 = profile_corpus([_CLEAN_CORPUS])
        p2 = profile_corpus([_CLEAN_CORPUS])
        assert p1 == p2

    def test_returns_required_keys(self):
        p = profile_corpus([_CLEAN_CORPUS])
        for key in ("words", "confidence", "cv_sentence", "cv_band",
                    "mean_sentence", "contractions_per_100w",
                    "first_person_per_100w", "commas_per_sentence"):
            assert key in p, f"missing key: {key}"

    def test_confidence_low_on_thin_corpus(self):
        p = profile_corpus(["Short text."])
        assert p["confidence"] == "low"

    def test_confidence_medium_on_mid_corpus(self):
        p = profile_corpus([_CORPUS_MEDIUM])
        assert p["confidence"] in ("medium", "high")

    def test_confidence_high_on_large_corpus(self):
        p = profile_corpus([_CORPUS_HIGH])
        assert p["confidence"] == "high"

    def test_cv_band_is_80_120_pct_of_cv(self):
        p = profile_corpus([_CLEAN_CORPUS])
        cv = p["cv_sentence"]
        lo, hi = p["cv_band"]
        assert abs(lo - round(cv * 0.8, 2)) < 0.01
        assert abs(hi - round(cv * 1.2, 2)) < 0.01

    def test_joins_multiple_texts(self):
        p_joined = profile_corpus([_CLEAN_CORPUS + "\n\n" + _CLEAN_CORPUS])
        p_split = profile_corpus([_CLEAN_CORPUS, _CLEAN_CORPUS])
        # Word count should be the same either way
        assert p_joined["words"] == p_split["words"]


# ── check_text — gate logic ────────────────────────────────────────────────────

class TestCheckTextGate:
    def test_em_dash_is_blocked(self):
        result = check_text(_EM_DASH_TEXT)
        assert result["gate"] == "BLOCKED"
        assert any("em_dash" in t for t in result["tells_hard"])

    def test_not_just_pivot_is_blocked(self):
        result = check_text(_NOT_JUST_TEXT)
        assert result["gate"] == "BLOCKED"
        assert any("not_just_pivot" in t for t in result["tells_hard"])

    def test_graded_tells_produce_review(self):
        result = check_text(_GRADED_TEXT)
        # Should have soft tells from overused graded vocab
        assert result["gate"] in ("REVIEW", "BLOCKED")
        assert len(result["tells_soft"]) > 0

    def test_clean_text_is_clear(self):
        result = check_text(_CLEAN_SHORT)
        assert result["gate"] == "CLEAR"
        assert result["tells_hard"] == []

    def test_hard_tell_beats_soft(self):
        # Even if graded tells present, em-dash makes it BLOCKED not REVIEW
        combined = _EM_DASH_TEXT + " " + _GRADED_TEXT
        result = check_text(combined)
        assert result["gate"] == "BLOCKED"


# ── check_text — profile comparison ───────────────────────────────────────────

class TestCheckTextWithProfile:
    def _profile(self, **overrides):
        base = profile_corpus([_CLEAN_CORPUS])
        base.update(overrides)
        return base

    def test_cv_in_band_passes(self):
        p = profile_corpus([_CLEAN_CORPUS])
        # Check the same corpus text against its own profile — CV must be in band
        result = check_text(_CLEAN_CORPUS, p)
        assert result["target_pass"].get("cv_sentence") == "PASS"

    def test_cv_out_of_band_fails(self):
        # Artificially narrow band to guarantee failure
        p = self._profile(cv_band=(0.01, 0.02))
        result = check_text(_CLEAN_CORPUS, p)
        assert result["target_pass"].get("cv_sentence") == "FAIL"
        assert result["gate"] == "REVIEW"  # no hard tell → REVIEW not BLOCKED

    def test_target_fail_on_low_confidence_is_review_not_blocked(self):
        # Low-confidence profile: target failures must not escalate to BLOCKED
        p = self._profile(confidence="low", cv_band=(0.01, 0.02))
        result = check_text(_CLEAN_CORPUS, p)
        assert result["gate"] != "BLOCKED"
        assert result["gate"] == "REVIEW"

    def test_no_profile_returns_empty_target_pass(self):
        result = check_text(_CLEAN_SHORT, None)
        assert result["target_pass"] == {}

    def test_result_always_has_required_keys(self):
        result = check_text(_CLEAN_SHORT)
        for key in ("tells_hard", "tells_soft", "target_pass", "gate", "metrics"):
            assert key in result


# ── capture_voice_sample ───────────────────────────────────────────────────────

class TestCaptureVoiceSample:
    def _import(self):
        # Import from plugin/scripts — not on conftest path, so add manually
        scripts = Path(__file__).parent.parent / "plugin" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        from youk_hook_utils import capture_voice_sample
        return capture_voice_sample

    def test_appends_substantive_text(self, tmp_path):
        capture_voice_sample = self._import()
        text = "This is a substantive message that is long enough to be captured by the hook."
        capture_voice_sample(tmp_path, text, slug="testproject", register="chat")
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        assert corpus.exists()
        entry = json.loads(corpus.read_text().strip())
        assert entry["text"] == text
        assert entry["slug"] == "testproject"
        assert entry["register"] == "chat"
        assert "ts" in entry

    def test_skips_short_text(self, tmp_path):
        capture_voice_sample = self._import()
        capture_voice_sample(tmp_path, "ok", slug="p", register="chat")
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        assert not corpus.exists()

    def test_skips_slash_commands(self, tmp_path):
        capture_voice_sample = self._import()
        capture_voice_sample(tmp_path, "/build this thing now", slug="p", register="chat")
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        assert not corpus.exists()

    def test_appends_multiple_entries(self, tmp_path):
        capture_voice_sample = self._import()
        msg = "A substantive message that is long enough to pass the length gate for capture."
        capture_voice_sample(tmp_path, msg, slug="p", register="chat")
        capture_voice_sample(tmp_path, msg + " second", slug="p", register="chat")
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        lines = [l for l in corpus.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_silent_fail_on_unwritable_path(self, tmp_path):
        capture_voice_sample = self._import()
        # Pass a root that can't be written to (file in place of dir)
        bad_root = tmp_path / "not_a_dir"
        bad_root.write_text("I am a file, not a directory")
        # Must not raise
        capture_voice_sample(bad_root, "A long enough message to pass the length check.", "p")

    def test_caps_entry_text_at_2000_chars(self, tmp_path):
        capture_voice_sample = self._import()
        long_text = "x" * 3000
        capture_voice_sample(tmp_path, long_text, slug="p", register="chat")
        corpus = tmp_path / "knowledge" / "voice-corpus.jsonl"
        entry = json.loads(corpus.read_text().strip())
        assert len(entry["text"]) == 2000
