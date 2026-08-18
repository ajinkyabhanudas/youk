"""Voice profile builder — per-register profile regeneration from corpus.

Called at session_end. Reads knowledge/voice-corpus.jsonl, groups by register,
calls profile_corpus() per register, writes knowledge/global/voice-{slug}-{register}.md.

Confidence gate: only writes profiles with confidence in {medium, high}.
Silent-fail throughout — a missing corpus or unwritable path must never block session_end.
Atomic write: tempfile + os.replace so a partial write never leaves a corrupt profile.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_MIN_CONFIDENCE = {"medium", "high"}


def rebuild_voice_profiles(youk_root: Path, slug: str) -> dict[str, Any]:
    """Read corpus, profile per register, write to knowledge/global/. Returns a summary dict."""
    corpus_path = youk_root / "knowledge" / "voice-corpus.jsonl"
    output_dir = youk_root / "knowledge" / "global"

    if not corpus_path.exists():
        log.debug("voice_profile: corpus absent, skipping")
        return {"skipped": True, "reason": "corpus_absent"}

    # Group texts by register
    by_register: dict[str, list[str]] = {}
    try:
        for line in corpus_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            register = entry.get("register", "chat")
            text = entry.get("text", "")
            if text:
                by_register.setdefault(register, []).append(text)
    except Exception as e:
        log.debug("voice_profile: corpus read error: %s", e)
        return {"skipped": True, "reason": f"corpus_read_error: {e}"}

    if not by_register:
        return {"skipped": True, "reason": "corpus_empty"}

    try:
        from voice_fingerprint import profile_corpus
    except ImportError as e:
        log.debug("voice_profile: import error: %s", e)
        return {"skipped": True, "reason": f"import_error: {e}"}

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.debug("voice_profile: output dir error: %s", e)
        return {"skipped": True, "reason": f"mkdir_error: {e}"}

    written: list[str] = []
    skipped_low: list[str] = []

    for register, texts in by_register.items():
        try:
            profile = profile_corpus(texts)
        except Exception as e:
            log.debug("voice_profile: profile_corpus failed for %s: %s", register, e)
            continue

        confidence = profile.get("confidence", "low")
        words = profile.get("words", 0)
        out_path = output_dir / f"voice-{slug}-{register}.md"
        log.debug(
            "voice_profile: register=%s words=%d confidence=%s",
            register, words, confidence,
        )

        if confidence not in _MIN_CONFIDENCE:
            skipped_low.append(register)
            log.debug("voice_profile: skipping %s (confidence=%s)", register, confidence)
            continue

        content = _render_profile_md(slug, register, profile)
        _atomic_write(out_path, content)
        written.append(register)
        log.debug("voice_profile: wrote %s", out_path)

    return {
        "skipped": False,
        "registers_written": written,
        "registers_skipped_low_confidence": skipped_low,
    }


def _render_profile_md(slug: str, register: str, profile: dict[str, Any]) -> str:
    """Render a profile dict as a markdown file."""
    lines = [
        f"# Voice profile — {slug} / {register}",
        "",
        f"Confidence: {profile['confidence']} ({profile['words']} words)",
        "",
        "## Measured targets",
        "",
        f"- sentence length CV: {profile['cv_sentence']} (band {profile['cv_band'][0]}–{profile['cv_band'][1]})",
        f"- mean sentence: {profile['mean_sentence']} words",
        f"- contractions: {profile['contractions_per_100w']}/100w",
        f"- first person: {profile['first_person_per_100w']}/100w",
        f"- commas/sentence: {profile['commas_per_sentence']}",
    ]
    if profile.get("openers_pct"):
        lines += ["", "## Opener distribution", ""]
        for opener, pct in profile["openers_pct"].items():
            lines.append(f"- {opener}: {pct}%")
    if profile.get("punct_per_1000w"):
        lines += ["", "## Punctuation (per 1000w)", ""]
        for mark, rate in profile["punct_per_1000w"].items():
            lines.append(f"- {mark}: {rate}")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a temp file in the same directory."""
    dir_ = path.parent
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
