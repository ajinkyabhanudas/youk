"""
Shared utilities for youk hooks.

All hooks are read-only against youk state files — they never write to the
knowledge store directly (that's MCP tools' job). They only write to state/
ephemeral files and produce JSON output for Claude Code.

Token estimation: characters / 4 is a good approximation for English text.
We use transcript character count as a proxy since hooks have no API to
query actual token usage.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path


# ── Path resolution ────────────────────────────────────────────────────────────

def youk_root() -> Path | None:
    """Resolve YOUK_ROOT from env or well-known install location."""
    env = os.environ.get("YOUK_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p
    # Default install path
    default = Path.home() / ".claude" / "youk"
    if default.exists():
        return default
    return None


def slug_from_cwd(cwd: str) -> str:
    return Path(cwd).name or "unknown"


# ── State file readers ─────────────────────────────────────────────────────────

def load_contracts(root: Path, slug: str) -> list[str]:
    f = root / "knowledge" / "projects" / slug / "contracts.md"
    if not f.exists():
        return []
    return [
        line.strip()
        for line in f.read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("---")
    ]


def load_global_contracts(root: Path, cap: int = 10) -> list[str]:
    f = root / "knowledge" / "global" / "contracts.md"
    if not f.exists():
        return []
    lines = []
    for line in f.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
            if len(lines) >= cap:
                break
    return lines


def load_session_plan(root: Path, slug: str) -> list[str]:
    plan_file = root / "state" / "session-plan.json"
    if not plan_file.exists():
        return []
    try:
        data = json.loads(plan_file.read_text())
        if slug and data.get("slug") and data["slug"] != slug:
            return []
        return data.get("plan", [])
    except Exception:
        return []


def load_active_task(root: Path) -> dict:
    f = root / "state" / "active_task.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def load_decisions(root: Path, slug: str, max_decisions: int = 3) -> list[str]:
    f = root / "knowledge" / "projects" / slug / "decisions.md"
    if not f.exists():
        return []
    lines = f.read_text().splitlines()
    decisions: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ") and current:
            decisions.append("\n".join(current))
            current = [line]
        elif line.strip():
            current.append(line)
    if current:
        decisions.append("\n".join(current))
    # Return last N, compressed to heading + first body line
    result = []
    for d in decisions[-max_decisions:]:
        parts = d.strip().splitlines()
        heading = parts[0] if parts else ""
        body = next((p for p in parts[1:] if p.strip()), "")
        result.append(f"{heading}: {body}".strip())
    return result


# ── Intent extraction ─────────────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "not", "in", "on", "at", "from",
    "to", "with", "by", "for", "of", "it", "is", "i", "we", "you",
    "can", "do", "this", "that", "what", "how", "why", "when", "where",
    "me", "my", "our", "your", "its", "be", "has", "have",
    "are", "was", "were", "will", "would", "could", "should",
    "just", "also", "now", "then",
}


def extract_intent_keywords(prompt: str) -> set[str]:
    words = prompt.lower().split()
    return {w.strip(".,!?:;\"'()[]") for w in words
            if len(w) > 3 and w not in _STOP_WORDS}


def contract_matches_intent(contract: str, keywords: set[str]) -> bool:
    """Return True if contract contains any intent keyword, or if no keywords given."""
    if not keywords:
        return True  # no intent filter — include everything
    contract_words = set(contract.lower().split())
    return bool(contract_words & keywords)


# ── Intent-gated brief builder ────────────────────────────────────────────────

def build_intent_gated_brief(
    root: Path,
    slug: str,
    intent_keywords: set[str],
    include_active_task: bool = True,
) -> str:
    """
    Build a minimal brief (~100-200 tokens) gated on intent keywords.

    Philosophy: index model, not dump model.
    - Contracts matching intent: verbatim
    - Contracts not matching: count only ("N others in contracts.md")
    - Decisions: heading + one line, most recent 3 only
    - Active task: always included (it's always relevant)
    - Session plan: first non-warning item only
    """
    contracts = load_contracts(root, slug)
    global_contracts = load_global_contracts(root)
    all_contracts = global_contracts + contracts

    matching = [c for c in all_contracts if contract_matches_intent(c, intent_keywords)]
    non_matching_count = len(all_contracts) - len(matching)

    active_task = load_active_task(root) if include_active_task else {}
    decisions = load_decisions(root, slug, max_decisions=3)
    plan = load_session_plan(root, slug)
    resume_item = next((p for p in plan if p and not p.startswith("⚠")), "")

    lines: list[str] = ["[YOUK BRIEF]"]

    if matching:
        lines.append("Contracts (active):")
        for c in matching:
            lines.append(f"  {c}")
    if non_matching_count > 0:
        lines.append(f"  +{non_matching_count} others in contracts.md")

    if active_task:
        task_label = active_task.get("task", "")
        files = ", ".join(active_task.get("files_touched", [])[:3])
        last_signal = active_task.get("last_signal", "")
        parts = [f"Active: {task_label}"]
        if files:
            parts.append(f"files: {files}")
        if last_signal:
            parts.append(f"last: {last_signal[:80]}")
        lines.append(" | ".join(parts))

    if resume_item:
        lines.append(f"Resume: {resume_item[:120]}")

    if decisions:
        lines.append("Decisions: " + " / ".join(d[:60] for d in decisions))

    lines.append("[/YOUK BRIEF]")
    return "\n".join(lines)


# ── Transcript analysis ───────────────────────────────────────────────────────

def estimate_context_tokens(transcript_path: str) -> int:
    """
    Estimate total context tokens from transcript character count.
    Uses chars/4 approximation. Returns 0 if transcript unreadable.
    """
    try:
        text = Path(transcript_path).read_text(encoding="utf-8", errors="ignore")
        return len(text) // 4
    except Exception:
        return 0


def extract_recent_tool_outputs(transcript_path: str, max_outputs: int = 3) -> list[dict]:
    """
    Extract the most recent tool_use + tool_result pairs from the transcript.
    Returns list of {tool_name, output_chars, output_snippet}.
    """
    results = []
    try:
        lines = Path(transcript_path).read_text(errors="ignore").splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                content = entry.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if block.get("type") == "tool_result":
                        output = str(block.get("content", ""))
                        results.append({
                            "output_chars": len(output),
                            "output_snippet": output[:120],
                        })
                        if len(results) >= max_outputs:
                            return results
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass
    return results


# ── Ambient intelligence: task size + session-end detection ──────────────────

# M+ build signals — phrases that indicate a feature/refactor task is starting
_BUILD_SIGNALS = [
    "let's add", "let's build", "let's implement", "let's create", "let's refactor",
    "add a ", "add the ", "build a ", "build the ", "implement ", "create a ", "create the ",
    "i want to add", "i want to build", "i want to implement", "i want to create",
    "we need to add", "we need to build", "we need to implement",
    "can you add", "can you build", "can you implement", "can you create",
    "new feature", "new endpoint", "new component", "new module",
    "refactor ", "migrate ", "redesign ", "overhaul ",
]

# Route-task gate warning — suppressed after N warnings per session
_ROUTE_WARNING_SUPPRESS_AFTER = 3
_HOOK_WARNINGS_FILE = "state/hook-warnings.jsonl"


def load_routes_yaml_signals(root: Path) -> list[str]:
    """
    Load M/L/XL build signals from config/routes.yaml.

    Falls back to _BUILD_SIGNALS when routes.yaml is absent or unparseable.
    Merges signals from M, L, and XL size buckets — all imply M+ routing.
    """
    try:
        import yaml  # type: ignore[import-untyped]
        routes_file = root / "config" / "routes.yaml"
        if not routes_file.exists():
            return list(_BUILD_SIGNALS)
        data = yaml.safe_load(routes_file.read_text())
        task_sizes = data.get("task_sizes", {})
        combined: list[str] = []
        for size in ("M", "L", "XL"):
            combined.extend(task_sizes.get(size, {}).get("signals", []))
        return combined if combined else list(_BUILD_SIGNALS)
    except Exception:
        return list(_BUILD_SIGNALS)


def route_task_ran_this_session(root: Path, slug: str) -> bool:
    """
    Check whether route_task was called at any point this session for this slug.

    Session boundary: route-task-ran.json must have been written AFTER the
    session-open.json file (both written at session start / first tool call).
    If session-open.json is absent, falls back to same-calendar-day (mtime) check —
    a flag file from yesterday is treated as a prior session.
    """
    import datetime as _dt
    flag_file = root / "state" / "route-task-ran.json"
    if not flag_file.exists():
        return False
    try:
        raw = json.loads(flag_file.read_text())
        entries = raw if isinstance(raw, list) else [raw]
        # Check slug match first
        slug_match = any(e.get("slug") == slug for e in entries)
        if not slug_match:
            return False
        # Session boundary check: route-task-ran.json must be newer than session-open.json
        open_file = root / "state" / "session-open.json"
        if open_file.exists():
            open_mtime = open_file.stat().st_mtime
            flag_mtime = flag_file.stat().st_mtime
            if flag_mtime < open_mtime:
                return False  # route-task-ran is from a prior session
        else:
            # No session-open.json — fall back to same-calendar-day check.
            # A flag written yesterday is a prior session; only today's flag counts.
            flag_mtime = flag_file.stat().st_mtime
            flag_day = _dt.date.fromtimestamp(flag_mtime)
            if flag_day != _dt.date.today():
                return False  # flag from a different calendar day = stale
        return True
    except Exception:
        return False


def count_route_warnings_this_session(root: Path, slug: str) -> int:
    """Count route_task warnings already emitted this session for this slug."""
    warnings_file = root / _HOOK_WARNINGS_FILE
    if not warnings_file.exists():
        return 0
    try:
        open_file = root / "state" / "session-open.json"
        session_start = 0.0
        if open_file.exists():
            session_start = open_file.stat().st_mtime
        count = 0
        for line in warnings_file.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("slug") != slug or entry.get("type") != "route_missing":
                continue
            if entry.get("ts", 0.0) >= session_start:
                count += 1
        return count
    except Exception:
        return 0


def log_route_warning(root: Path, slug: str) -> None:
    """Append a route_missing warning entry to hook-warnings.jsonl."""
    import time
    warnings_file = root / _HOOK_WARNINGS_FILE
    try:
        warnings_file.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"type": "route_missing", "slug": slug, "ts": time.time()})
        with warnings_file.open("a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def build_route_missing_warning() -> str:
    """Warning injected when M+ signals are detected but route_task hasn't run."""
    return (
        "[YOUK] M+ signals detected — route_task has not run this session. "
        "Run /build before implementing: route_task → challenge → nfr_check → "
        "check_nfr_gate → check_challenge_gate → dev-loop."
    )

# Session-end signals — natural phrases that close a work block
_SESSION_END_SIGNALS = [
    "ok thanks", "that's all", "that's all for now", "looks good", "we're done",
    "we're done here", "let's call it", "alright", "perfect", "good enough",
    "that'll do", "that'll do it", "wrap it up", "let's wrap", "we can stop here",
    "nothing else", "i think we're good", "ship it", "commit it", "done for now",
    "done for today", "calling it", "calling it a day", "that's it for today",
    "ok done", "all done", "all good", "that works", "looks great", "nice",
]

# NFR check already ran — track via state file
_NFR_STATE_FILE = "state/nfr-check-ran.json"


def detect_task_size(prompt: str, signals: list[str] | None = None) -> str | None:
    """
    Detect if the prompt implies an M+ task that needs /build routing.
    Returns 'M' if detected, None if not clearly M+.
    Deliberately conservative — false positives are more annoying than misses.
    Exception: short prompts containing explicit BUILD_SIGNALS still trigger
    ("build page", "add auth") — length filter was blocking valid M+ detection.

    signals: optional list of M/L/XL signals from routes.yaml. Defaults to
    _BUILD_SIGNALS when None (backward-compatible for existing callers).
    """
    active_signals = signals if signals is not None else _BUILD_SIGNALS
    lower = prompt.lower().strip()
    # Skip explicit slash commands — user is already routing
    if lower.startswith("/"):
        return None
    # Check build signals first — short prompts with clear signals should fire
    if any(sig in lower for sig in active_signals):
        # Skip if clearly a question even with a build word
        if lower.startswith(("what", "why", "how", "where", "when", "which", "does", "is ", "are ")):
            return None
        return "M"
    # Skip very short prompts with no build signal — not enough signal
    if len(lower) < 15:
        return None
    # Skip prompts that are clearly questions or clarifications
    if lower.startswith(("what", "why", "how", "where", "when", "which", "does", "is ", "are ")):
        return None
    return None


def detect_session_end(prompt: str) -> bool:
    """
    Detect if the prompt signals the user is wrapping up for the day.
    Returns True only on clear session-closing phrases.
    """
    lower = prompt.lower().strip()
    # Must be short — long messages aren't session-close signals
    if len(lower) > 60:
        return False
    return any(sig in lower for sig in _SESSION_END_SIGNALS)


def nfr_check_ran_this_session(root: Path, slug: str) -> bool:
    """Check whether NFR check has already run for this session+slug."""
    state_file = root / _NFR_STATE_FILE
    if not state_file.exists():
        return False
    try:
        data = json.loads(state_file.read_text())
        return data.get("slug") == slug
    except Exception:
        return False


def routing_ran_for_task(root: Path, slug: str, task_hash: str) -> bool:
    """
    Check whether route_task was called for this specific task this session.
    Returns False if route_task was never called, or was called for different tasks only.
    Uses the array format written by server.py's route_task wrapper.
    """
    flag_file = root / "state" / "route-task-ran.json"
    if not flag_file.exists():
        return False
    try:
        raw = json.loads(flag_file.read_text())
        entries = raw if isinstance(raw, list) else [raw]
        return any(
            e.get("slug") == slug and e.get("task_hash") == task_hash
            for e in entries
        )
    except Exception:
        return False


def load_session_health(root: Path) -> dict:
    """
    Load a minimal health signal from improvement-metrics.json.
    Returns {org_score, gaps_last30, close_cluster_rate} or empty dict.
    """
    metrics_file = root / "state" / "improvement-metrics.json"
    if not metrics_file.exists():
        return {}
    try:
        data = json.loads(metrics_file.read_text())
        history = data.get("history", [])
        if not history:
            return {}
        latest = history[-1]
        return {
            "org_score": latest.get("org_score", 0),
            "gaps_last30": latest.get("gaps_last30", 0),
            "close_cluster_rate": latest.get("close_cluster_rate", 0),
        }
    except Exception:
        return {}


def build_build_nudge(prompt: str) -> str:
    """
    Directive injected when an M+ task is detected without explicit /build.
    Phrased as an instruction to Claude, not a suggestion to the user.
    """
    return (
        "[YOUK DIRECTIVE] M+ task detected. Run /build routing NOW before responding: "
        "challenge → nfr_check → check_nfr_gate → dev-loop. "
        "Do not ask the user — execute the sequence immediately, then continue."
    )


def build_session_end_nudge() -> str:
    """
    Directive injected when a session-end signal is detected.
    Phrased as an instruction to Claude, not a suggestion to the user.
    """
    return (
        "[YOUK DIRECTIVE] Session-end detected. Run /done NOW: "
        "code-review → verify → humanize → learn → session_end(close_cluster=True). "
        "Do not ask the user — execute immediately."
    )


def build_health_nudge(health: dict) -> str | None:
    """
    Return a one-line ambient health signal if something is materially wrong.
    Returns None if health is nominal or empty — silence is the right signal when things are fine.
    """
    if not health:
        return None
    score = health.get("org_score", 0)
    gaps = health.get("gaps_last30", 0)
    close_rate = health.get("close_cluster_rate", 0)

    if score < 5.0:
        return f"[YOUK HEALTH] org_score {score:.1f}/10 — run /improve to address {gaps} open gaps."
    if gaps > 20 and close_rate < 0.4:
        return (
            f"[YOUK HEALTH] {gaps} recurring gaps, {close_rate:.0%} session close rate. "
            "Type /done at session end — it's the primary driver of compounding."
        )
    return None


# ── Correction capture ───────────────────────────────────────────────────────
#
# Correction phrases: natural language the developer uses when the model stopped
# short of the real answer. Every instance is a labeled training signal — the
# model produced a response the developer found incomplete or wrong, and pushed.
# Captured in knowledge/corrections.jsonl (gitignored, personal data).

_CORRECTION_PHRASES = [
    "you missed", "that's wrong", "not quite", "are you sure", "sure?",
    "what about", "you didn't", "incorrect", "that's not", "wrong approach",
    "is this all", "fight the urge", "fight your", "directionally biased",
    "you're missing", "still missing", "not complete", "incomplete",
    "you forgot", "what else", "anything else", "keep going", "go deeper",
    "that's not all", "is that all", "is this it", "only this",
]

_CORRECTIONS_FILE = "knowledge/corrections.jsonl"
_CORRECTIONS_CAP = 200


def _is_correction(prompt: str) -> bool:
    """Return True if the prompt is a correction of the model's prior response."""
    lower = prompt.lower().strip()
    # Short correction phrases — check directly
    if len(lower) <= 80:
        return any(phrase in lower for phrase in _CORRECTION_PHRASES)
    # Longer prompts — only fire if correction phrase appears in first 60 chars
    # (avoids false positives where "are you sure" appears in a code snippet)
    return any(phrase in lower[:60] for phrase in _CORRECTION_PHRASES)


def _extract_prior_assistant_turn(transcript_path: str) -> str:
    """
    Extract the last 200 chars of the most recent assistant message from transcript.
    Returns empty string if transcript is unreadable or no assistant turn exists.
    """
    if not transcript_path:
        return ""
    try:
        lines = Path(transcript_path).read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines()
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                msg = entry.get("message", {})
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Extract text blocks only
                    text = " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                elif isinstance(content, str):
                    text = content
                else:
                    continue
                if text.strip():
                    return text.strip()[-200:]
            except (json.JSONDecodeError, KeyError):
                continue
    except Exception:
        pass
    return ""


def capture_correction(
    root: Path,
    prompt: str,
    transcript_path: str,
    session_id: str,
) -> None:
    """
    Write a correction event to knowledge/corrections.jsonl.
    Called when the incoming user prompt is detected as a correction.
    Rolling cap: oldest entries dropped when file exceeds _CORRECTIONS_CAP lines.
    """
    import time
    corrections_file = root / _CORRECTIONS_FILE
    try:
        corrections_file.parent.mkdir(parents=True, exist_ok=True)
        prior_excerpt = _extract_prior_assistant_turn(transcript_path)
        entry = json.dumps({
            "ts": time.time(),
            "session_id": session_id,
            "correction_text": prompt[:300],
            "prior_assistant_excerpt": prior_excerpt,
            "phrase_matched": next(
                (p for p in _CORRECTION_PHRASES if p in prompt.lower()[:80]),
                "",
            ),
        })
        # Rolling cap: read existing, drop oldest if at cap
        existing: list[str] = []
        if corrections_file.exists():
            existing = [
                ln for ln in corrections_file.read_text().splitlines() if ln.strip()
            ]
        if len(existing) >= _CORRECTIONS_CAP:
            existing = existing[-(  _CORRECTIONS_CAP - 1):]
        existing.append(entry)
        corrections_file.write_text("\n".join(existing) + "\n")
    except Exception:
        pass  # never surface hook errors to the user


def load_correction_patterns(root: Path, top_n: int = 3) -> list[dict]:
    """
    Read corrections.jsonl and return top N phrase patterns by frequency.
    Used to personalize the generation frame when enough corrections exist.
    Returns [] when file absent or fewer than 5 entries (cold start).
    """
    corrections_file = root / _CORRECTIONS_FILE
    if not corrections_file.exists():
        return []
    try:
        lines = [
            json.loads(ln)
            for ln in corrections_file.read_text().splitlines()
            if ln.strip()
        ]
    except Exception:
        return []
    if len(lines) < 5:
        return []
    counts: dict[str, int] = {}
    for entry in lines:
        phrase = entry.get("phrase_matched", "")
        if phrase:
            counts[phrase] = counts.get(phrase, 0) + 1
    sorted_phrases = sorted(counts.items(), key=lambda x: -x[1])
    return [{"pattern": p, "count": c} for p, c in sorted_phrases[:top_n]]


# ── Generation frame ──────────────────────────────────────────────────────────
#
# Injected BEFORE [YOUK BRIEF] on every substantive prompt.
# Purpose: shift the model's generation attractor from "approval-seeking"
# toward "completeness" BEFORE the first token of the response is generated.
# Generic frame used until corrections.jsonl has ≥5 entries.
# Personalized frame built from top correction patterns after that.

_GENERIC_GENERATION_FRAME = (
    "[GENERATION FRAME]\n"
    "This developer pushes until the real answer surfaces. "
    "The first response will be challenged. "
    "Say the uncomfortable thing now rather than after being asked three times. "
    "If the honest answer contradicts the current direction, say so immediately. "
    "Stopping at 'defensible' will be caught.\n"
    "[/GENERATION FRAME]"
)

# Prompts where the generation frame must NOT fire:
# slash commands, very short responses, file reads, one-word replies
_FRAME_SKIP_PREFIXES = ("/", "yes", "no", "ok", "okay", "sure", "done")
_FRAME_MIN_LEN = 20


def build_generation_frame(root: Path) -> str:
    """
    Return the generation frame string to inject before [YOUK BRIEF].
    Personalized when corrections.jsonl has ≥5 entries, generic otherwise.
    Returns empty string when the prompt should be skipped.
    """
    patterns = load_correction_patterns(root)
    if not patterns:
        return _GENERIC_GENERATION_FRAME

    # Personalized: top pattern drives the specific callout
    top = patterns[0]["pattern"]
    count = patterns[0]["count"]
    frame_lines = [
        "[GENERATION FRAME]",
        f"This developer has corrected '{top}' {count} times. "
        "The pattern: the model stopped short of the real answer. "
        "Say the uncomfortable thing now. "
        "If the honest answer contradicts the current direction, say so immediately. "
        "Stopping at 'defensible' will be caught.",
    ]
    if len(patterns) > 1:
        others = ", ".join(f"'{p['pattern']}'" for p in patterns[1:])
        frame_lines.append(f"Also recurring: {others}.")
    frame_lines.append("[/GENERATION FRAME]")
    return "\n".join(frame_lines)


def should_inject_frame(prompt: str) -> bool:
    """Return True if this prompt warrants a generation frame injection."""
    stripped = prompt.strip().lower()
    if len(stripped) < _FRAME_MIN_LEN:
        return False
    if any(stripped.startswith(p) for p in _FRAME_SKIP_PREFIXES):
        return False
    return True


# ── Session-10 experiment marker ──────────────────────────────────────────────
#
# Written at session start when the generation frame experiment begins.
# At session 65 (current=55, +10), youk auto-runs the measurement:
#   - compute correction rate from transcripts
#   - compare to baseline
#   - surface findings + Phase 3 decision gate
#
# Marker file: state/generation-frame-experiment.json
# {started_at_session: N, trigger_at_session: N+10, baseline_corrections_per_session: float}

_EXPERIMENT_FILE = "state/generation-frame-experiment.json"
_EXPERIMENT_TRIGGER_SESSIONS = 10


def load_experiment_state(root: Path) -> dict:
    """Load the generation frame experiment state. Returns {} if not started."""
    f = root / _EXPERIMENT_FILE
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}


def init_experiment_if_needed(root: Path, current_session: int) -> None:
    """
    Write experiment marker on the first session after generation frame is added.
    Idempotent — does nothing if already initialized.
    """
    f = root / _EXPERIMENT_FILE
    if f.exists():
        return
    try:
        data = {
            "started_at_session": current_session,
            "trigger_at_session": current_session + _EXPERIMENT_TRIGGER_SESSIONS,
            "baseline_corrections_per_session": None,  # computed on first run
            "started_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        f.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def experiment_trigger_due(root: Path, current_session: int) -> bool:
    """Return True when the current session has reached the measurement trigger."""
    state = load_experiment_state(root)
    if not state:
        return False
    trigger = state.get("trigger_at_session")
    if trigger is None:
        return False
    return current_session >= trigger


def build_experiment_trigger_nudge(root: Path, current_session: int) -> str:
    """
    Directive injected when the session-10 measurement is due.
    Tells Claude to run the measurement analysis autonomously.
    """
    state = load_experiment_state(root)
    started = state.get("started_at_session", "?")
    return (
        f"[YOUK EXPERIMENT] Generation frame experiment: session {current_session} "
        f"(started session {started}, trigger session {state.get('trigger_at_session', '?')}). "
        "Run correction rate measurement NOW: "
        "read knowledge/corrections.jsonl, compute corrections per session, "
        "compare against baseline in state/generation-frame-experiment.json, "
        "surface findings + Phase 3 decision (Outcome A/B/C). "
        "Do not wait for user to ask — this fires automatically."
    )


# ── Output helpers ────────────────────────────────────────────────────────────

def ok(system_message: str = "", additional_context: str = "") -> None:
    """Emit a successful hook response and exit 0."""
    out: dict = {"continue": True}
    if system_message:
        out["systemMessage"] = system_message
    if additional_context:
        out["hookSpecificOutput"] = {"additionalContext": additional_context}
    print(json.dumps(out))
    sys.exit(0)


def ok_no_output() -> None:
    """Emit minimal approval with no injected content."""
    print(json.dumps({"continue": True}))
    sys.exit(0)


def read_stdin() -> dict:
    """Read and parse JSON from stdin. Returns {} on failure (never raises)."""
    try:
        return json.loads(sys.stdin.read())
    except Exception:
        return {}
