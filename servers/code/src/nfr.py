from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, "/shared")

from models import NFRBlock, TaskSize
from skill_loader import load_skill

_FAST_PATH_QUESTIONS = [
    "Does this touch an external API, DB write, or auth path?",
    "Can this break if called twice (idempotency)?",
]

_QUICK_4Q_QUESTIONS = [
    "Q1 — Auth / credentials / session: does this touch auth state, tokens, or access control?",
    "Q2 — Idempotency: can this be called twice safely, or does it mutate shared state?",
    "Q3 — Scale / performance: what are the expected load and latency bounds?",
    "Q4 — Security boundary: does this handle untrusted input or produce output that reaches a UI or external system?",
]


def nfr_check_fast(task: str) -> NFRBlock:
    """2-question fast path for XS/S tasks — no API call."""
    decisions = [
        f"Q1 — External I/O / auth path: Review task scope: '{task[:80]}'. "
        "If no external API, DB write, or auth path is involved, no NFR gates apply.",
        "Q2 — Idempotency: If this operation can be called twice safely, no idempotency requirement.",
    ]
    return NFRBlock(
        task=task,
        size=TaskSize.S,
        mode="fast_path_2q",
        decisions=decisions,
        connections=[],
        raw_output="\n".join(decisions),
    )


def nfr_check_quick(task: str) -> dict:
    """
    4-question NFR context for M tasks — returns in_session dict for Claude Code to answer.
    No API call: the active Claude Code session answers the questions with full project context.
    """
    skill_content = load_skill("nfr-check")
    return {
        "mode": "in_session",
        "task": task,
        "size": "M",
        "skill_content": skill_content,
        "questions": _QUICK_4Q_QUESTIONS,
        "instruction": (
            "Answer the 4 NFR questions above for this task using your full session context. "
            "Output as [NFR — QUICK] block followed by [CONNECTIONS] section. "
            "Keep total output under 400 words."
        ),
    }


def nfr_check_full(task: str, size: TaskSize) -> dict:
    """
    Full NFR context for L/XL tasks — returns in_session dict for Claude Code to answer.
    No API call: the active Claude Code session runs the full check with all phases.
    """
    skill_content = load_skill("nfr-check")
    return {
        "mode": "in_session",
        "task": task,
        "size": size.value,
        "skill_content": skill_content,
        "questions": _QUICK_4Q_QUESTIONS,
        "instruction": (
            f"Run the full nfr-check skill (all phases) for this {size.value} task. "
            "Output the complete NFR DECISION BLOCK and CONNECTIONS section. "
            "Keep total output under 800 words."
        ),
    }


_WAF_QUESTIONS = [
    "Does this change maintain zero footprint in downstream project repos "
    "(no writes outside /youk/ or /claude/skills/)?",
    "Does this change respect the knowledge-extraction-not-logging hard rule "
    "(no raw conversation transcripts stored at any point in the code path)?",
]


def _load_current_slug() -> str:
    """Read the last project slug from youk state — used for WAF injection."""
    try:
        import json
        state_file = Path("/youk/state/session.json")
        if state_file.exists():
            return json.loads(state_file.read_text()).get("last_project", "")
    except Exception:
        pass
    return ""


def _is_youk_project() -> bool:
    slug = _load_current_slug()
    return Path(slug).name == "youk" if slug else False


def run_nfr_check(task: str, size_str: str = "M") -> NFRBlock | dict:
    """
    XS/S: returns NFRBlock (fast path, no API call).
    M+: returns in_session dict for Claude Code to execute with full context.
    """
    size = TaskSize(size_str.upper()) if size_str.upper() in TaskSize.__members__ else TaskSize.M

    if size in (TaskSize.XS, TaskSize.S):
        return nfr_check_fast(task)
    elif size == TaskSize.M:
        result = nfr_check_quick(task)
    else:
        result = nfr_check_full(task, size)

    # Inject WAF invariant checks for M+ tasks on the youk platform repo itself.
    if _is_youk_project():
        waf_note = (
            "\n[WAF — PLATFORM INVARIANTS]\n"
            f"Q-WAF1: {_WAF_QUESTIONS[0]}\n"
            f"Q-WAF2: {_WAF_QUESTIONS[1]}\n"
            "If either answer is No or Uncertain — stop and surface before proceeding."
        )
        result["questions"] = result.get("questions", []) + [waf_note]

    return result
