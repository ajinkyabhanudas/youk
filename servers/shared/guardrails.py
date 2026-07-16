from __future__ import annotations
import re
import yaml
from pathlib import Path

from models import ViolationType, SoftRuleWarning


YOUK_ROOT = Path("/youk")
GUARDRAILS_FILE = YOUK_ROOT / "config" / "guardrails.yaml"

_CREDENTIAL_PATTERNS = [
    r"\.env$",
    r"\.env[.\-_]",  # .env.local, .env.backup, .env.production etc.
    r"secret",
    r"credential",
    r"api_key",
    r"password",
    r"\.pem$",
    r"\.key$",
]

# Known-safe env templates — blocked by pattern above but explicitly allowed.
_ALLOWED_CREDENTIAL_FILES = {".env.example", ".env.sample", ".env.template"}

_DESTRUCTIVE_PATTERNS = [
    r"rm\s+-rf",
    r"rm\s+-r\s+-f",   # rm -r -f (flags separated)
    r"rm\s+-f\s+-r",   # rm -f -r (flags reversed)
    r"DROP\s+TABLE",
    r"push\b.*--force(?!-)",  # git push [ref] --force but NOT --force-with-lease
    r"reset\s+--hard",
    r"checkout\s+\.",
    r"restore\s+\.",
    r"commit\b.*--no-verify",  # bypasses pre-commit hook — contract enforcement bypass
]


def load_guardrails() -> dict:
    if not GUARDRAILS_FILE.exists():
        return {"hard_rules": [], "soft_rules": []}
    with open(GUARDRAILS_FILE) as f:
        return yaml.safe_load(f)


class HardRuleViolation(Exception):
    def __init__(self, rule_id: str, message: str):
        self.rule_id = rule_id
        self.message = message
        super().__init__(f"HARD RULE VIOLATION [{rule_id}]: {message}")


def check_credential_file(file_path: str) -> None:
    """Raise HardRuleViolation if file_path matches credential patterns."""
    from pathlib import Path
    if Path(file_path).name in _ALLOWED_CREDENTIAL_FILES:
        return
    for pattern in _CREDENTIAL_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            raise HardRuleViolation(
                "no-credential-commits",
                f"File '{file_path}' matches credential pattern '{pattern}'. "
                "Cannot commit secrets. Move secrets to environment variables.",
            )


def check_destructive_command(command: str) -> None:
    """Raise HardRuleViolation if command is destructive without explicit confirm."""
    for pattern in _DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            raise HardRuleViolation(
                "no-destructive-without-confirm",
                f"Destructive command detected: '{command[:80]}'. "
                "Explicit confirmation required before executing.",
            )


def check_knowledge_write(content: str) -> None:
    """Raise HardRuleViolation if content looks like a raw transcript."""
    raw_transcript_signals = [
        "human:", "assistant:", "user:", "claude:", "<human>", "<assistant>",
    ]
    lower = content.lower()
    for signal in raw_transcript_signals:
        if signal in lower:
            raise HardRuleViolation(
                "knowledge-extraction-not-logging",
                f"Content appears to be a raw transcript (contains '{signal}'). "
                "knowledge/ stores structured insights only, never raw sessions.",
            )


def get_soft_rule_warnings(task_size: str, skills_invoked: list[str]) -> list[SoftRuleWarning]:
    """Return applicable soft rule warnings for the current task context."""
    warnings = []

    if task_size in ("M", "L", "XL") and "nfr_check" not in skills_invoked:
        warnings.append(SoftRuleWarning(
            rule_id="nfr-before-m-tasks",
            name="NFR check before M+ tasks",
            message=f"Task size {task_size} typically benefits from an NFR check before coding.",
            violation_type=ViolationType.SURFACE,
        ))

    if task_size in ("L", "XL") and "write_spec" not in skills_invoked:
        warnings.append(SoftRuleWarning(
            rule_id="spec-before-l-tasks",
            name="write-spec before L/XL tasks",
            message=f"Task size {task_size} should have a spec before dev-loop starts.",
            violation_type=ViolationType.SURFACE,
        ))

    return warnings
