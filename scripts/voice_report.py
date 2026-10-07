#!/usr/bin/env python3
"""What youk has learned about how you write.

Reads knowledge/voice-corpus.jsonl (your prompts, saved by the UserPromptSubmit hook), builds the
profile the way session_end does, and prints it. If knowledge/global/voice-baseline.json exists it
prints those earlier numbers beside it. Both files are local and gitignored, and no one's numbers
ship in this repo. Nothing is gated on these numbers.

    python3 scripts/voice_report.py [--root ~/.claude/youk] [--register chat]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "servers" / "core" / "src"))
from voice_fingerprint import profile_corpus  # noqa: E402

KEYS = ("mean_sentence", "cv_sentence", "contractions_per_100w", "first_person_per_100w",
        "commas_per_sentence")


def load_baseline(root: Path) -> dict:
    """Earlier numbers kept locally by the developer, or {} when there are none."""
    path = root / "knowledge" / "global" / "voice-baseline.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def corpus_texts(root: Path, register: str) -> list[str]:
    path = root / "knowledge" / "voice-corpus.jsonl"
    if not path.exists():
        return []
    texts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("register", "chat") == register and row.get("text"):
            texts.append(row["text"])
    return texts


def render(profile: dict, register: str, baseline: dict | None = None) -> str:
    baseline = baseline or {}
    head = f"{'measure':24} {'learned':>9}" + (f" {'baseline':>9}" if baseline else "")
    lines = [f"register {register}: {profile['words']} words, confidence {profile['confidence']}", head]
    for key in KEYS:
        row = f"{key:24} {profile[key]:>9}"
        if baseline:
            row += f" {baseline.get(key, '-'):>9}"
        lines.append(row)
    marks = profile.get("punct_per_1000w", {})
    lines.append("punctuation per 1000 words: " + ", ".join(f"{k} {v}" for k, v in marks.items()))
    if profile["confidence"] == "low":
        lines.append("under 1500 words, so the profile is not written to knowledge/global yet.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path.home() / ".claude" / "youk")
    ap.add_argument("--register", default="chat")
    args = ap.parse_args(argv)
    texts = corpus_texts(args.root, args.register)
    if not texts:
        print(f"no {args.register} samples in {args.root}/knowledge/voice-corpus.jsonl. The "
              "UserPromptSubmit hook writes it once the youk plugin hooks load.")
        return 1
    print(render(profile_corpus(texts), args.register, load_baseline(args.root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
