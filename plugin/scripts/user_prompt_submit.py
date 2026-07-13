#!/usr/bin/env python3
"""
UserPromptSubmit hook — fires before Claude processes every user message.

Three jobs:
1. Inject an intent-gated brief (~100-150 tokens) so the right contracts
   are always hot in context without dumping everything every turn.
2. Detect context pressure from transcript size and inject a compact signal
   when approaching the threshold where auto-compaction would fire.
3. Ambient intelligence: detect M+ tasks and session-end signals in natural
   language so /build and /done fire without requiring the user to type them.

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
    detect_task_size,
    detect_session_end,
    nfr_check_ran_this_session,
    load_session_health,
    build_build_nudge,
    build_session_end_nudge,
    build_health_nudge,
    ok,
    ok_no_output,
)

# Token thresholds
THRESHOLD_ELEVATED = 40_000   # ~160k chars — start warning
THRESHOLD_CRITICAL = 60_000   # ~240k chars — trigger compact

# Minimum prompt length to bother with intent extraction (skip "ok", "yes", etc.)
MIN_PROMPT_LEN = 8

# Only inject health nudge every N turns to avoid noise (approx via transcript size growth)
_HEALTH_NUDGE_INTERVAL_TURNS = 8


def build_compact_signal(estimated_tokens: int, brief: str) -> str:
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


def _estimate_turn_count(transcript_path: str) -> int:
    """Rough turn count from transcript line count — each turn is ~several lines."""
    try:
        lines = Path(transcript_path).read_text(errors="ignore").splitlines()
        return max(1, len([ln for ln in lines if ln.strip()]) // 8)
    except Exception:
        return 0


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

    # ── Ambient intelligence injections ──────────────────────────────────────
    nudges: list[str] = []

    if len(user_prompt) >= MIN_PROMPT_LEN:
        # 1. Session-end detection — highest priority signal
        if detect_session_end(user_prompt):
            nudges.append(build_session_end_nudge())

        # 2. M+ task detection — inject build nudge if NFR hasn't run this session
        elif detect_task_size(user_prompt) == "M":
            if not nfr_check_ran_this_session(root, slug):
                nudges.append(build_build_nudge(user_prompt))

    # 3. Ambient health — only inject every ~8 turns so it doesn't become noise
    turn_count = _estimate_turn_count(transcript_path) if transcript_path else 0
    if turn_count > 0 and turn_count % _HEALTH_NUDGE_INTERVAL_TURNS == 0:
        health = load_session_health(root)
        health_nudge = build_health_nudge(health)
        if health_nudge:
            nudges.append(health_nudge)

    # ── Assemble final context ────────────────────────────────────────────────
    nudge_block = "\n".join(nudges)

    if estimated_tokens >= THRESHOLD_CRITICAL:
        context = build_compact_signal(estimated_tokens, brief)
    elif estimated_tokens >= THRESHOLD_ELEVATED:
        context = build_elevated_signal(estimated_tokens, brief)
    else:
        context = brief

    if nudge_block:
        context = nudge_block + "\n\n" + context

    ok(additional_context=context)


if __name__ == "__main__":
    main()
