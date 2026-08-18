"""Tests for voice_profile.rebuild_voice_profiles.

Covers: corpus-absent, corpus-empty, low-confidence gate, medium-confidence write,
multi-register isolation, corrupt JSONL resilience, atomic write.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "servers" / "core" / "src"))
from voice_profile import rebuild_voice_profiles

# ~140 words — need 11+ copies to reach medium confidence (>1500w)
_SAMPLE_TEXT = (
    "We found three models that disagreed on every synthetic benchmark but converged on the "
    "real evaluation set. That is not a coincidence. The synthetic benchmarks were built from "
    "the same distribution as the training data, so they measure memorization, not transfer. "
    "The real set was drawn from a different domain entirely. "
    "This happens more than people admit. A model can score 94% on one benchmark and fail the "
    "simplest out-of-distribution probe. The number becomes a shield. Teams stop asking what "
    "it measures and start optimizing for it directly, which makes it measure even less. "
    "What we did instead: built the evaluation set before we trained the model. Fixed the "
    "criteria first, then collected data. It took two extra weeks and we argued about it the "
    "whole time. Every model shipped since has held up in production."
)


def _write_corpus(root: Path, entries: list[dict]) -> Path:
    corp = root / "knowledge" / "voice-corpus.jsonl"
    corp.parent.mkdir(parents=True, exist_ok=True)
    with corp.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return corp


def _entry(text: str = _SAMPLE_TEXT, register: str = "chat") -> dict:
    return {"ts": "2026-08-18", "slug": "youk", "register": register, "text": text}


def _medium_entries(register: str = "chat", n: int = 15) -> list[dict]:
    return [_entry(register=register) for _ in range(n)]


# ── corpus-absent ──────────────────────────────────────────────────────────────

def test_corpus_absent(tmp_path):
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert result["skipped"] is True
    assert result["reason"] == "corpus_absent"


# ── corpus-empty ───────────────────────────────────────────────────────────────

def test_corpus_empty(tmp_path):
    _write_corpus(tmp_path, [])
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert result["skipped"] is True
    assert result["reason"] == "corpus_empty"


# ── low-confidence gate ────────────────────────────────────────────────────────

def test_low_confidence_does_not_write(tmp_path):
    # 3 entries ≈ 420 words — well below 1500w threshold
    _write_corpus(tmp_path, [_entry() for _ in range(3)])
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert result["skipped"] is False
    assert "chat" in result["registers_skipped_low_confidence"]
    assert "chat" not in result["registers_written"]
    out = tmp_path / "knowledge" / "global" / "voice-youk-chat.md"
    assert not out.exists()


# ── medium-confidence write ────────────────────────────────────────────────────

def test_medium_confidence_writes_file(tmp_path):
    _write_corpus(tmp_path, _medium_entries())
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert result["skipped"] is False
    assert "chat" in result["registers_written"]
    out = tmp_path / "knowledge" / "global" / "voice-youk-chat.md"
    assert out.exists()
    content = out.read_text()
    assert "# Voice profile — youk / chat" in content
    assert "Confidence:" in content
    assert "cv_sentence" in content or "sentence length CV" in content


def test_profile_file_content_keys(tmp_path):
    _write_corpus(tmp_path, _medium_entries())
    rebuild_voice_profiles(tmp_path, "youk")
    content = (tmp_path / "knowledge" / "global" / "voice-youk-chat.md").read_text()
    for marker in ("contractions", "first person", "commas/sentence", "Opener distribution"):
        assert marker in content, f"Missing: {marker}"


# ── multi-register isolation ───────────────────────────────────────────────────

def test_multi_register_writes_separate_files(tmp_path):
    entries = _medium_entries("chat") + _medium_entries("commit")
    _write_corpus(tmp_path, entries)
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert "chat" in result["registers_written"]
    assert "commit" in result["registers_written"]
    assert (tmp_path / "knowledge" / "global" / "voice-youk-chat.md").exists()
    assert (tmp_path / "knowledge" / "global" / "voice-youk-commit.md").exists()


# ── corrupt JSONL resilience ───────────────────────────────────────────────────

def test_corrupt_lines_skipped_gracefully(tmp_path):
    corp = tmp_path / "knowledge" / "voice-corpus.jsonl"
    corp.parent.mkdir(parents=True)
    with corp.open("w") as f:
        f.write("not json at all\n")
        f.write("{broken\n")
        for e in _medium_entries():
            f.write(json.dumps(e) + "\n")
    result = rebuild_voice_profiles(tmp_path, "youk")
    assert "chat" in result["registers_written"]


# ── idempotent / overwrite ─────────────────────────────────────────────────────

def test_idempotent_write(tmp_path):
    _write_corpus(tmp_path, _medium_entries())
    rebuild_voice_profiles(tmp_path, "youk")
    rebuild_voice_profiles(tmp_path, "youk")
    out = tmp_path / "knowledge" / "global" / "voice-youk-chat.md"
    assert out.exists()
    # Second write should produce identical content
    c1 = out.read_text()
    rebuild_voice_profiles(tmp_path, "youk")
    assert out.read_text() == c1
