from __future__ import annotations
import sys
from pathlib import Path

YOUK_ROOT = Path("/youk")
sys.path.insert(0, "/shared")

from models import NFRBlock, TaskSize
from skill_loader import load_skill, load_skill_reference
from domain_edge_cases import surface_domain_edge_cases

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


_VALIDATE_MODE_INSTRUCTION = (
    "Coverage check, not fresh prompting: for each of the 4 dimensions above, if your "
    "session context already establishes an answer, output 'CONFIRMED: <dimension> — "
    "<one-line basis>' rather than re-deriving it from scratch. Only reason a dimension "
    "out fully if nothing in context already covers it. Output as [NFR — VALIDATE] block "
    "followed by [CONNECTIONS] section. Keep total output under 200 words."
)

_STANDARD_MODE_INSTRUCTION = (
    "Answer the 4 NFR questions above for this task using your full session context. "
    "Output as [NFR — QUICK] block followed by [CONNECTIONS] section. "
    "Keep total output under 400 words."
)


def _parse_markdown_bullets(markdown: str) -> list[str]:
    """Extract top-level `- ` bullet lines from a markdown reference file."""
    return [
        stripped[2:].strip()
        for line in markdown.splitlines()
        if (stripped := line.strip()).startswith("- ")
    ]


def load_functional_edge_case_questions() -> list[str]:
    """
    CIR-150 item 1 / CIR-151: the functional-edge-case question bank, loaded from
    the SAME reference file stress-test's Agent B reads
    (skills/stress-test/references/edge-case-questions.md) — one list, so this
    proactive-derivation phase and Agent B's reactive attack can never drift apart.

    Returns [] if the reference file is missing rather than raising — nfr-check
    must never fail to run because stress-test's reference moved or was renamed.
    """
    try:
        content = load_skill_reference("stress-test", "edge-case-questions.md")
    except FileNotFoundError:
        return []
    return _parse_markdown_bullets(content)


_FUNCTIONAL_EDGE_CASE_INSTRUCTION = (
    "Before drafting any plan, answer each functional edge-case question below "
    "against the raw task text — empty/null inputs, boundary values, "
    "concurrent/ordering issues, partial failure. This is stress-test's Agent B "
    "lens (references/edge-case-questions.md) applied proactively to the problem "
    "statement, the same way Phase 1 CLASSIFY derives NFR categories from raw "
    "task text before a plan exists — not run reactively against a finished "
    "design the way stress-test itself runs. State inferred answers where the "
    "task text already settles them; flag only the ones a plan needs to "
    "actually decide."
)


_DOMAIN_EDGE_CASE_INSTRUCTION = (
    "CIR-163: domain-specific candidates below (if any) are DISTINCT from the generic "
    "functional edge-case questions above — each one is filtered against this project's "
    "actual Domain Brief (state/domain-brief.json) and names the real invariant/ADR that "
    "made it relevant, so treat each as a real, checkable claim, not a generic prompt. An "
    "empty list here is the correct, honest answer when nothing in the Domain Brief is "
    "genuinely relevant to this task — never force one."
)


def nfr_check_quick(task: str, autonomy_mode: str = "standard") -> dict:
    """
    4-question NFR context for M tasks — returns in_session dict for Claude Code to answer.
    No API call: the active Claude Code session answers the questions with full project context.

    autonomy_mode: "standard" (default) asks all 4 questions fresh, every time. "validate"
    is the branch session.py's nfr_autonomy_mode computation was already deciding on
    (rate >= 0.4 over the last 90 days) but that nothing here ever read — a developer
    who has consistently answered these questions well gets asked to confirm coverage
    against existing context instead of re-deriving each answer, not skip the gate. Any
    value other than "validate" is treated as "standard" — the safe default when the mode
    is missing, unrecognized, or the caller hasn't wired it through yet.
    """
    skill_content = load_skill("nfr-check")
    validate = autonomy_mode == "validate"
    return {
        "mode": "in_session",
        "task": task,
        "size": "M",
        "skill_content": skill_content,
        "questions": _QUICK_4Q_QUESTIONS,
        "autonomy_mode": "validate" if validate else "standard",
        "instruction": _VALIDATE_MODE_INSTRUCTION if validate else _STANDARD_MODE_INSTRUCTION,
        "functional_edge_case_questions": load_functional_edge_case_questions(),
        "functional_edge_case_instruction": _FUNCTIONAL_EDGE_CASE_INSTRUCTION,
        "domain_edge_case_candidates": surface_domain_edge_cases(task, root=YOUK_ROOT),
        "domain_edge_case_instruction": _DOMAIN_EDGE_CASE_INSTRUCTION,
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
        "functional_edge_case_questions": load_functional_edge_case_questions(),
        "functional_edge_case_instruction": _FUNCTIONAL_EDGE_CASE_INSTRUCTION,
        "domain_edge_case_candidates": surface_domain_edge_cases(task, root=YOUK_ROOT),
        "domain_edge_case_instruction": _DOMAIN_EDGE_CASE_INSTRUCTION,
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
        state_file = YOUK_ROOT / "state" / "session.json"
        if state_file.exists():
            return json.loads(state_file.read_text()).get("last_project", "")
    except Exception:
        pass
    return ""


def _is_youk_project() -> bool:
    slug = _load_current_slug()
    return Path(slug).name == "youk" if slug else False


def run_nfr_check(task: str, size_str: str = "M", autonomy_mode: str = "standard") -> NFRBlock | dict:
    """
    XS/S: returns NFRBlock (fast path, no API call).
    M+: returns in_session dict for Claude Code to execute with full context.

    autonomy_mode only affects the M path — L/XL always run the full check regardless
    of developer autonomy history. Higher-stakes work earns no reduction in ceremony;
    only the M-level quick-path scales down, and only after it's been demonstrated.
    """
    size = TaskSize(size_str.upper()) if size_str.upper() in TaskSize.__members__ else TaskSize.M

    if size in (TaskSize.XS, TaskSize.S):
        return nfr_check_fast(task)
    elif size == TaskSize.M:
        result = nfr_check_quick(task, autonomy_mode)
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
