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


def detect_task_size(prompt: str) -> str | None:
    """
    Detect if the prompt implies an M+ task that needs /build routing.
    Returns 'M' if detected, None if not clearly M+.
    Deliberately conservative — false positives are more annoying than misses.
    """
    lower = prompt.lower().strip()
    # Skip very short prompts — not enough signal
    if len(lower) < 15:
        return None
    # Skip prompts that are clearly questions or clarifications
    if lower.startswith(("what", "why", "how", "where", "when", "which", "does", "is ", "are ")):
        return None
    # Skip explicit slash commands — user is already routing
    if lower.startswith("/"):
        return None
    # Check build signals
    if any(sig in lower for sig in _BUILD_SIGNALS):
        return "M"
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
    """One-line nudge injected when an M+ task is detected without explicit /build."""
    return (
        "[YOUK] M+ task detected — NFR gate will run before implementation. "
        "Type /build to make this explicit, or continue and the gate fires automatically."
    )


def build_session_end_nudge() -> str:
    """One-line nudge injected when a session-end signal is detected."""
    return (
        "[YOUK] Session-end detected — run /done before closing "
        "to save contracts, review work, and compound today's patterns. "
        "Takes 60 seconds. Skipping loses this session's learnings."
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
