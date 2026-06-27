from __future__ import annotations
import os
import sys
sys.path.insert(0, "/shared")

from models import NFRBlock, TaskSize
from skill_loader import load_skill

try:
    import anthropic
    _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
except Exception:
    _client = None

_MODEL = "claude-sonnet-4-6"

_FAST_PATH_QUESTIONS = [
    "Does this touch an external API, DB write, or auth path?",
    "Can this break if called twice (idempotency)?",
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


def nfr_check_quick(task: str) -> NFRBlock:
    """4-question NFR block for M tasks — single API call."""
    if not _client:
        return NFRBlock(
            task=task,
            size=TaskSize.M,
            mode="quick_4q",
            decisions=["API client not available — check ANTHROPIC_API_KEY"],
            connections=[],
            raw_output="",
        )

    skill_content = load_skill("nfr-check")
    user_msg = (
        f"Task: {task}\nSize: M\n\n"
        "Run the nfr-check skill in quick mode (4 questions only).\n"
        "Output format: [NFR — QUICK] block followed by [CONNECTIONS] section.\n"
        "Keep total output under 400 words."
    )

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=skill_content,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text

    decisions = _extract_section(raw, "NFR")
    connections = _extract_section(raw, "CONNECTIONS")

    return NFRBlock(
        task=task,
        size=TaskSize.M,
        mode="quick_4q",
        decisions=[decisions] if decisions else [],
        connections=[connections] if connections else [],
        raw_output=raw,
    )


def nfr_check_full(task: str, size: TaskSize) -> NFRBlock:
    """Full NFR check for L/XL tasks."""
    if not _client:
        return NFRBlock(
            task=task,
            size=size,
            mode="full",
            decisions=["API client not available — check ANTHROPIC_API_KEY"],
            connections=[],
            raw_output="",
        )

    skill_content = load_skill("nfr-check")
    user_msg = (
        f"Task: {task}\nSize: {size.value}\n\n"
        "Run the full nfr-check skill (all phases).\n"
        "Output the complete NFR DECISION BLOCK and CONNECTIONS section.\n"
        "Keep total output under 800 words."
    )

    response = _client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=skill_content,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = response.content[0].text

    return NFRBlock(
        task=task,
        size=size,
        mode="full",
        decisions=[_extract_section(raw, "NFR DECISION BLOCK")],
        connections=[_extract_section(raw, "CONNECTIONS")],
        raw_output=raw,
    )


def run_nfr_check(task: str, size_str: str = "M") -> NFRBlock:
    size = TaskSize(size_str.upper()) if size_str.upper() in TaskSize.__members__ else TaskSize.M

    if size in (TaskSize.XS, TaskSize.S):
        return nfr_check_fast(task)
    elif size == TaskSize.M:
        return nfr_check_quick(task)
    else:
        return nfr_check_full(task, size)


def _extract_section(text: str, section_name: str) -> str:
    lines = text.split("\n")
    in_section = False
    result = []
    for line in lines:
        if section_name.upper() in line.upper() and ("[" in line or "#" in line):
            in_section = True
            result.append(line)
            continue
        if in_section:
            if line.strip().startswith("[") or (line.strip().startswith("#") and section_name not in line):
                break
            result.append(line)
    return "\n".join(result).strip()
