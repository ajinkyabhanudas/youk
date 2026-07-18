#!/usr/bin/env python3
"""
PreCompact hook — fires before Claude auto-compacts the context window.

Goal: ensure that when Claude's summarizer runs, it has a structured youk
brief as the most recent authoritative content. This biases the summarizer
to preserve contracts, active task, and resume point verbatim rather than
paraphrasing them from scattered conversation turns.

The hook does NOT prevent compaction (we can't and shouldn't). It ensures
the post-compact context starts from youk's structured knowledge, not from
Claude's lossy summarization of conversation text.

Output: systemMessage injected immediately before compaction runs.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from youk_hook_utils import (
    read_stdin,
    youk_root,
    slug_from_cwd,
    load_contracts,
    load_global_contracts,
    load_active_task,
    load_session_plan,
    load_decisions,
    ok,
    ok_no_output,
)


def build_pre_compact_brief(root: Path, slug: str, cwd: str) -> str:
    """
    Build a rich preservation brief for the compaction summarizer.

    Unlike the intent-gated UserPromptSubmit brief (which is minimal),
    this one is comprehensive — it's injected once before compaction
    and must carry everything load-bearing through the summarization.

    Still disciplined: contracts verbatim, decisions compressed,
    active task full, plan truncated to 3 items.
    """
    contracts = load_contracts(root, slug)
    global_contracts = load_global_contracts(root)
    active_task = load_active_task(root)
    plan = load_session_plan(root, slug)
    decisions = load_decisions(root, slug, max_decisions=5)

    lines: list[str] = [
        "=== YOUK PRE-COMPACT PRESERVATION BRIEF ===",
        "The following is authoritative structured context from youk's knowledge store.",
        "The compaction summarizer MUST preserve these items verbatim — they are not",
        "reconstructable from conversation and represent permanent working agreements.",
        "",
    ]

    # Global contracts first (cross-project, always apply)
    if global_contracts:
        lines.append("## Global Contracts (apply to all projects — preserve VERBATIM):")
        for c in global_contracts:
            lines.append(f"  {c}")
        lines.append("")

    # Project contracts
    if contracts:
        lines.append(f"## Project Contracts for '{slug}' (preserve VERBATIM):")
        for c in contracts:
            lines.append(f"  {c}")
        lines.append("")
    else:
        lines.append(f"## Project Contracts for '{slug}': (none saved)")
        lines.append("")

    # Active task — what we're currently doing
    if active_task:
        lines.append("## Active Task (current work — preserve for resume):")
        lines.append(f"  Task: {active_task.get('task', 'unknown')}")
        files = active_task.get("files_touched", [])
        if files:
            lines.append(f"  Files: {', '.join(files[:5])}")
        signal = active_task.get("last_signal", "")
        if signal:
            lines.append(f"  Last signal: {signal[:200]}")
        lines.append("")

    # Session plan resume point
    resume_items = [p for p in plan if p and not p.startswith("⚠")]
    if resume_items:
        lines.append("## Session plan (resume point):")
        for item in resume_items[:3]:
            lines.append(f"  - {item[:150]}")
        lines.append("")

    # Recent decisions
    if decisions:
        lines.append("## Recent Decisions:")
        for d in decisions:
            lines.append(f"  - {d[:120]}")
        lines.append("")

    lines.append(f"## Project: {slug} | Dir: {cwd}")
    lines.append("=== END YOUK PRE-COMPACT BRIEF ===")
    lines.append("")
    lines.append("INSTRUCTION TO SUMMARIZER: The items above marked VERBATIM must appear")
    lines.append("unchanged in the compacted context. Compress conversation turns freely,")
    lines.append("but treat this brief as the authoritative ground truth for this session.")

    return "\n".join(lines)


def main() -> None:
    data = read_stdin()
    cwd = data.get("cwd", "")

    root = youk_root()
    if root is None:
        ok_no_output()
        return

    # Track how many times auto-compact fires per session.
    # Persisted to state/compact-count.json; read and cleared by session_end.
    # Format: {session-day: YYYY-MM-DD, count: N} — session-day enables pre/post splits.
    count_file = root / "state" / "compact-count.json"
    try:
        import json as _json
        from datetime import date as _date
        today = _date.today().isoformat()
        existing = {}
        if count_file.exists():
            existing = _json.loads(count_file.read_text())
        count_file.write_text(_json.dumps({
            "session-day": existing.get("session-day", today),
            "count": existing.get("count", 0) + 1,
        }))
    except Exception:
        pass

    slug = slug_from_cwd(cwd)
    brief = build_pre_compact_brief(root, slug, cwd)
    ok(system_message=brief)


if __name__ == "__main__":
    main()
