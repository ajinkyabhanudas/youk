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
    route_task_ran_this_session,
    count_route_warnings_this_session,
    log_route_warning,
    build_route_missing_warning,
    load_routes_yaml_signals,
    load_session_health,
    build_build_nudge,
    build_session_end_nudge,
    build_health_nudge,
    # Generation frame + correction capture
    _is_correction,
    capture_correction,
    build_generation_frame,
    should_inject_frame,
    # Session-10 experiment
    init_experiment_if_needed,
    experiment_trigger_due,
    build_experiment_trigger_nudge,
    ok,
    ok_no_output,
    _ROUTE_WARNING_SUPPRESS_AFTER,
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


def _load_session_counter(root: "Path") -> int:
    """Read current session counter from state/session.json."""
    try:
        f = root / "state" / "session.json"
        if f.exists():
            return json.loads(f.read_text()).get("session_counter", 0)
    except Exception:
        pass
    return 0


def _load_session_id(root: "Path") -> str:
    """Read current session slug/id from state/session-open.json."""
    try:
        f = root / "state" / "session-open.json"
        if f.exists():
            return json.loads(f.read_text()).get("slug", "unknown")
    except Exception:
        pass
    return "unknown"


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

    # ── Correction capture (runs before anything else — highest value signal) ─
    # Detect if this prompt is a correction of the model's prior response.
    # Write to corrections.jsonl regardless of other logic.
    if len(user_prompt) >= MIN_PROMPT_LEN and _is_correction(user_prompt):
        session_id = _load_session_id(root)
        capture_correction(root, user_prompt, transcript_path, session_id)

    # Extract intent from the incoming prompt
    keywords = (
        extract_intent_keywords(user_prompt)
        if len(user_prompt) >= MIN_PROMPT_LEN
        else set()
    )

    # Build the intent-gated brief
    brief = build_intent_gated_brief(root, slug, keywords)

    # ── Generation frame (prepended before brief) ─────────────────────────────
    # Shifts model attractor toward completeness before first token of response.
    # Skipped on slash commands, very short prompts, and one-word replies.
    frame_block = ""
    if should_inject_frame(user_prompt):
        frame_block = build_generation_frame(root)

    # Estimate context pressure from transcript
    estimated_tokens = estimate_context_tokens(transcript_path) if transcript_path else 0

    # ── Experiment marker init (session 55 = first session with frame) ────────
    current_session = _load_session_counter(root)
    init_experiment_if_needed(root, current_session)

    # ── Ambient intelligence injections ──────────────────────────────────────
    nudges: list[str] = []

    routes_signals = load_routes_yaml_signals(root)

    if len(user_prompt) >= MIN_PROMPT_LEN:
        # 0. Session-10 experiment trigger — highest priority, fires once at session 65
        if experiment_trigger_due(root, current_session):
            nudges.append(build_experiment_trigger_nudge(root, current_session))

        # 1. Session-end detection
        elif detect_session_end(user_prompt):
            nudges.append(build_session_end_nudge())

        # 2. M+ task detection
        elif detect_task_size(user_prompt, routes_signals) == "M":
            if not route_task_ran_this_session(root, slug):
                warn_count = count_route_warnings_this_session(root, slug)
                if warn_count < _ROUTE_WARNING_SUPPRESS_AFTER:
                    nudges.append(build_route_missing_warning())
                    log_route_warning(root, slug)
            elif not nfr_check_ran_this_session(root, slug):
                nudges.append(build_build_nudge(user_prompt))

    # 3. Ambient health — only inject every ~8 turns so it doesn't become noise
    turn_count = _estimate_turn_count(transcript_path) if transcript_path else 0
    if turn_count > 0 and turn_count % _HEALTH_NUDGE_INTERVAL_TURNS == 0:
        health = load_session_health(root)
        health_nudge = build_health_nudge(health)
        if health_nudge:
            nudges.append(health_nudge)

    # ── Assemble final context ────────────────────────────────────────────────
    # Order: nudges → generation frame → brief
    nudge_block = "\n".join(nudges)

    if estimated_tokens >= THRESHOLD_CRITICAL:
        context = build_compact_signal(estimated_tokens, brief)
    elif estimated_tokens >= THRESHOLD_ELEVATED:
        context = build_elevated_signal(estimated_tokens, brief)
    else:
        context = brief

    # Generation frame prepended to brief (inside compact/elevated signals too)
    if frame_block:
        context = frame_block + "\n\n" + context

    if nudge_block:
        context = nudge_block + "\n\n" + context

    ok(additional_context=context)


if __name__ == "__main__":
    main()
