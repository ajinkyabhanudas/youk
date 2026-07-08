#!/usr/bin/env python3
"""
UserPromptSubmit hook — fires before Claude processes every user message.

Two jobs:
1. Inject an intent-gated brief (~100-150 tokens) so the right contracts
   are always hot in context without dumping everything every turn.
2. Detect context pressure from transcript size and inject a compact signal
   when we're approaching the threshold where auto-compaction would fire.

The compact signal tells Claude to run /compact BEFORE processing this
message. Claude Code evaluates slash commands from system context injected
by hooks — this is the mechanism that makes compaction automatic.

Pressure thresholds (chars in transcript, ÷4 ≈ tokens):
  - < 40k tokens (~160k chars): normal — inject intent brief only
  - 40k-60k tokens (~240k chars): elevated — inject brief + soft warning
  - > 60k tokens (~240k chars): critical — inject compact signal

These thresholds trigger compaction at ~30-40% of the 200k context window,
leaving plenty of room and avoiding auto-compaction at 70%.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from youk_hook_utils import (
    read_stdin,
    youk_root,
    slug_from_cwd,
    extract_intent_keywords,
    build_intent_gated_brief,
    estimate_context_tokens,
    ok,
    ok_no_output,
)

# Token thresholds
THRESHOLD_ELEVATED = 40_000   # ~160k chars — start warning
THRESHOLD_CRITICAL = 60_000   # ~240k chars — trigger compact

# Minimum prompt length to bother with intent extraction (skip "ok", "yes", etc.)
MIN_PROMPT_LEN = 8


def build_compact_signal(estimated_tokens: int, brief: str) -> str:
    """
    Compact signal injected when context pressure is critical.

    Instructs Claude to run /compact before processing the current message.
    After /compact, the auto-resume guard in CLAUDE.md calls compact_context,
    which rebuilds the brief from files — achieving a clean reset.
    """
    return (
        f"[YOUK CONTEXT SIGNAL] Context at ~{estimated_tokens:,} tokens "
        f"(threshold: {THRESHOLD_CRITICAL:,}). "
        "Run /compact now to clear dead context before processing this message. "
        "After /compact, youk will rebuild context from files automatically via the "
        "auto-resume guard. The message below will be reprocessed with fresh context.\n\n"
        + brief
    )


def build_elevated_signal(estimated_tokens: int, brief: str) -> str:
    return (
        f"[YOUK CONTEXT NOTE] Context growing (~{estimated_tokens:,} tokens). "
        "Consider /compact after this task completes.\n\n"
        + brief
    )


def main() -> None:
    data = read_stdin()
    cwd = data.get("cwd", "")
    transcript_path = data.get("transcript_path", "")
    user_prompt = data.get("user_prompt", "")

    root = youk_root()
    if root is None:
        ok_no_output()
        return

    slug = slug_from_cwd(cwd)

    # Extract intent from the incoming prompt
    keywords = (
        extract_intent_keywords(user_prompt)
        if len(user_prompt) >= MIN_PROMPT_LEN
        else set()
    )

    # Build the intent-gated brief
    brief = build_intent_gated_brief(root, slug, keywords)

    # Estimate context pressure from transcript
    estimated_tokens = estimate_context_tokens(transcript_path) if transcript_path else 0

    if estimated_tokens >= THRESHOLD_CRITICAL:
        context = build_compact_signal(estimated_tokens, brief)
    elif estimated_tokens >= THRESHOLD_ELEVATED:
        context = build_elevated_signal(estimated_tokens, brief)
    else:
        context = brief

    ok(additional_context=context)


if __name__ == "__main__":
    main()
