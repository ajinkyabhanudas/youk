from __future__ import annotations
import re
import sys
sys.path.insert(0, "/shared")

from models import CommitQualityResult
from guardrails import check_credential_file, HardRuleViolation

_EM_DASH_PATTERN = re.compile(r"—|–")
_FILLER_PATTERNS = [
    r"\bit's worth noting\b",
    r"\bin order to\b",
    r"\bplease note\b",
    r"\bfeel free to\b",
    r"\bof course\b",
    r"\bcertainly\b",
    r"\babsolutely\b",
]
_GOOD_SIGNALS = [
    r"\bbecause\b",
    r"\bso that\b",
    r"\bto prevent\b",
    r"\bto fix\b",
    r"\bto support\b",
    r"\binstead of\b",
    r"\brather than\b",
    r"\bwithout\b",
]


def check_commit_quality(message: str, file_paths: list[str] | None = None) -> CommitQualityResult:
    """
    Score a commit message against youk voice rules.
    Also enforces the no-credential-commits hard rule for any file paths provided.
    """
    violations = []
    score = 100
    blocked = False
    block_reason = None

    # Hard rule: check file paths for credentials
    for fp in (file_paths or []):
        try:
            check_credential_file(fp)
        except HardRuleViolation as e:
            return CommitQualityResult(
                score=0,
                violations=[str(e)],
                suggested_rewrite=None,
                blocked=True,
                block_reason=str(e),
            )

    # Soft quality checks
    if len(message.split()) < 5:
        violations.append("Too short — add more context about why this change was made.")
        score -= 20

    if _EM_DASH_PATTERN.search(message):
        violations.append("Contains em dash (—) — use plain punctuation instead.")
        score -= 10

    for pattern in _FILLER_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            violations.append(f"Filler phrase detected: '{pattern}'. Be direct.")
            score -= 10

    has_why = any(re.search(p, message, re.IGNORECASE) for p in _GOOD_SIGNALS)
    if not has_why and len(message.split()) > 5:
        violations.append("No 'why' signal — add because/to fix/to prevent to explain the reason.")
        score -= 15

    score = max(0, score)
    suggested = None
    if violations:
        suggested = _suggest_rewrite(message)

    return CommitQualityResult(
        score=score,
        violations=violations,
        suggested_rewrite=suggested,
        blocked=blocked,
        block_reason=block_reason,
    )


def _suggest_rewrite(message: str) -> str:
    cleaned = _EM_DASH_PATTERN.sub(" -", message)
    for pattern in _FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not any(re.search(p, cleaned, re.IGNORECASE) for p in _GOOD_SIGNALS):
        cleaned = cleaned.rstrip(".") + " — run /humanize for full rewrite"
    return cleaned
