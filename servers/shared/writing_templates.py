"""Writing templates: the layout of a document, separate from the voice it is written in.

Voice is how the words sound and is learned from the developer. A template is how the text is laid
out, and it depends on the situation. A commit message is a short note to the next maintainer. A PR
description is a formal document a reviewer works from. Chat is a reply. The same voice applies to
all three, and the template changes with the situation.

    commit    subject line, then what changed, why, and the impact, as plain paragraphs
    pr        headed sections for what changed, why, impact and how it was checked
    decision  Chose, Over, Because, Cost, the format DECISIONS.md already uses
    chat      no template: answer first, short, plain

The checks here are structural. They cannot tell whether a paragraph really is the impact, only
that the parts a reviewer needs are present, so they stay small and cheap. Wording stays the job of
the voice gate. Stdlib only.
"""
from __future__ import annotations

import re
import subprocess

SITUATIONS = ("commit", "pr", "decision", "chat")

SUBJECT_MAX = 72
# A change this size needs all three paragraphs; smaller ones need fewer.
LARGE_FILES, LARGE_LINES = 3, 80
TINY_FILES, TINY_LINES = 1, 10

_TRAILER = re.compile(r"^(co-authored-by|signed-off-by|claude-session|reviewed-by|fixes|closes|refs?)\b",
                      re.I)
_EXEMPT_SUBJECT = re.compile(r"^(merge\b|revert\b|fixup!|squash!|amend!)", re.I)

PR_SECTIONS: tuple[tuple[str, re.Pattern], ...] = (
    ("What changed", re.compile(r"^#{1,4}\s*what\s+(changed|this\s+(adds|does))\b", re.I | re.M)),
    ("Why", re.compile(r"^#{1,4}\s*(why|motivation|problem)\b", re.I | re.M)),
    ("Impact", re.compile(r"^#{1,4}\s*(impact|effect|result)\b", re.I | re.M)),
    ("How it was checked", re.compile(r"^#{1,4}\s*(how\s+(it\s+was\s+)?(checked|tested)|checked|tests?|testing|verification)\b",
                                       re.I | re.M)),
)

_SKELETONS = {
    "commit": (
        "<subject line, plain, under 72 characters>\n\n"
        "<what changed, in a sentence or two>\n\n"
        "<why it was needed>\n\n"
        "<the impact it had or will have on whoever uses it>"),
    "pr": (
        "## What changed\n<what the change does, plainly>\n\n"
        "## Why\n<the problem or goal behind it>\n\n"
        "## Impact\n<what this means for users, the system or the next piece of work>\n\n"
        "## How it was checked\n<tests run, what was and was not verified>\n\n"
        "## Not done\n<optional: what is left, risks, follow-ups>"),
    "decision": (
        "## <date>  [<title>]\nChose:      <what was chosen>\nOver:       <what was rejected>\n"
        "Because:    <the reason>\nCost:       <what this gives up>"),
    "chat": "Answer first, then only what changes what the reader does next. Short, plain sentences.",
}


def template_for(situation: str) -> str:
    """The skeleton for a situation, so the right layout is shown when it applies."""
    if situation not in _SKELETONS:
        raise ValueError(f"unknown situation {situation!r}; one of {SITUATIONS}")
    return _SKELETONS[situation]


def split_commit(message: str) -> tuple[str, list[str]]:
    """(subject, body paragraphs) with git comment lines, trailers and blank runs removed."""
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    text = "\n".join(lines).strip()
    if not text:
        return "", []
    subject, _, rest = text.partition("\n")
    paragraphs = []
    for block in re.split(r"\n\s*\n", rest.strip()):
        block = block.strip()
        if not block:
            continue
        kept = [ln for ln in block.splitlines() if not _TRAILER.match(ln.strip())]
        if kept and len(kept) == len(block.splitlines()):
            paragraphs.append(block)
        elif kept:
            paragraphs.append("\n".join(kept))
    return subject.strip(), paragraphs


def required_paragraphs(files: int, lines: int) -> int:
    """How many body paragraphs a commit of this size needs: 0 tiny, 1 small, 2 medium, 3 large."""
    if files <= TINY_FILES and lines <= TINY_LINES:
        return 0
    if files >= LARGE_FILES or lines >= LARGE_LINES:
        return 3
    return 2 if lines >= 30 else 1


def validate_commit(message: str, files: int = 0, lines: int = 0) -> list[str]:
    """What is missing from a commit message for a change of this size. Empty when it fits."""
    subject, paragraphs = split_commit(message)
    if not subject or _EXEMPT_SUBJECT.match(subject):
        return []
    problems = []
    if len(subject) > SUBJECT_MAX:
        problems.append(f"the subject line is {len(subject)} characters, keep it under {SUBJECT_MAX}")
    need = required_paragraphs(files, lines)
    if len(paragraphs) < need:
        names = ["what changed", "why", "the impact"][:need]
        problems.append(
            f"a change of {files} file(s) and {lines} line(s) needs {need} body paragraph(s) "
            f"({', '.join(names)}) and this has {len(paragraphs)}")
    return problems


def validate_pr(body: str) -> list[str]:
    """Missing required sections of a PR description, by name."""
    return [name for name, pattern in PR_SECTIONS if not pattern.search(body or "")]


def staged_size(cwd: str) -> tuple[int, int]:
    """(files, changed lines) staged in the repo at cwd. (0, 0) when git cannot say."""
    try:
        out = subprocess.run(["git", "-C", cwd, "diff", "--cached", "--numstat"],
                             capture_output=True, text=True, timeout=10).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return 0, 0
    lines = 0
    for row in out:
        parts = row.split("\t")
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            lines += int(parts[0]) + int(parts[1])
    return len(out), lines
