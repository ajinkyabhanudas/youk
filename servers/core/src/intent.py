"""
Intent optimization: compress ambiguous user input into a structured brief.

Serves three purposes:
1. Token efficiency — a 50-word structured brief replaces 300 words of back-and-forth
2. Architecture steering — the brief embeds the right pattern from the start
3. Clarification capture — seeds knowledge/clarifications/ when intent was non-obvious
"""
from __future__ import annotations
import os
import re
from pathlib import Path

def _resolve_api_key() -> str:
    """Read API key from env var, then fall back to mounted file."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    fallback = Path("/claude/.anthropic/api_key")
    if fallback.exists():
        return fallback.read_text().strip()
    return ""

try:
    import anthropic
    _API_KEY = _resolve_api_key()
    _CLIENT = anthropic.Anthropic(api_key=_API_KEY)
    _ANTHROPIC_AVAILABLE = bool(_API_KEY)
except Exception:
    _ANTHROPIC_AVAILABLE = False
    _API_KEY = ""

YOUK_ROOT = Path("/youk")

_INTENT_SYSTEM_PROMPT = """\
You are an intent optimizer. Your job is to take a raw user request (possibly vague, multi-part, or ambiguous) and produce a structured, compressed intent brief that a software engineer can execute directly.

The brief must be:
- Concrete and specific (no vague adjectives)
- Architecturally opinionated (recommend a pattern, not "it depends")
- Token-efficient (under 120 words total for the brief)
- Honest about scope (what is explicitly out of scope)

Output ONLY valid JSON matching this schema:
{
  "problem": "1-2 sentences, specific and actionable",
  "success_criteria": "measurable outcome — what done looks like",
  "constraints": ["technical", "scope", "time constraints"],
  "architecture_recommendation": "concrete pattern recommendation with one sentence rationale",
  "anti_patterns": ["pattern to avoid and why", "..."],
  "out_of_scope": ["explicit exclusions"],
  "ambiguity_detected": true/false,
  "clarifying_questions": ["question if ambiguity_detected is true, else empty"],
  "estimated_size": "XS/S/M/L/XL",
  "token_efficiency_gain": "estimated token reduction vs. proceeding with raw input (e.g. '60%')"
}

If the input is already clear and specific, set ambiguity_detected to false and clarifying_questions to [].
If the input mentions multiple unrelated concerns, separate them and note that in constraints.
Always recommend a concrete architecture pattern — never say "it depends" without a default recommendation.
"""

_FAST_PATTERNS = {
    "make it a repo": {
        "problem": "Create a properly structured, reproducible project repository with versioning, documentation, and developer tooling — not just a git init.",
        "architecture_recommendation": "Standard open-source repo layout: README, CHANGELOG, pyproject.toml or package.json, Makefile/scripts, docs/, CI workflow.",
        "anti_patterns": ["Bare git init with no structure", "README-only repos", "No reproducible build step"],
        "out_of_scope": ["Actual feature implementation — repo scaffolding only"],
        "ambiguity_detected": False,
        "clarifying_questions": [],
        "estimated_size": "M",
    },
    "clean it up": {
        "problem": "Refactor for readability and maintainability without changing behaviour. Scope: the files currently in context.",
        "architecture_recommendation": "Apply naming conventions, extract obvious helpers, remove dead code. No API changes.",
        "anti_patterns": ["Changing behaviour under the guise of cleanup", "Premature abstraction", "Renaming everything at once"],
        "out_of_scope": ["Feature additions", "Performance optimization", "Files not in current context"],
        "ambiguity_detected": True,
        "clarifying_questions": ["Which files or modules should be in scope for cleanup?"],
        "estimated_size": "S",
    },
}


def _check_fast_patterns(raw_input: str) -> dict | None:
    """Check if input matches a known pattern for instant response (no API call)."""
    lower = raw_input.lower()
    for pattern, result in _FAST_PATTERNS.items():
        if pattern in lower:
            return result
    return None


def optimize_intent(raw_input: str, clarified_context: str | None = None) -> dict:
    """
    Compress raw user input into a structured intent brief.

    Fast path (no API): known ambiguity patterns matched from knowledge/interpretation/
    Full path (API call): general intent optimization with architecture recommendation

    Returns the brief dict plus metadata about whether a fast path was used.
    """
    # Fast path: check known patterns first
    fast_result = _check_fast_patterns(raw_input)
    if fast_result and not clarified_context:
        return {
            **fast_result,
            "raw_input": raw_input,
            "mode": "fast_pattern_match",
            "success_criteria": fast_result.get("success_criteria", "Deliverables match the architecture recommendation."),
            "constraints": fast_result.get("constraints", []),
        }

    # Check interpretation patterns from knowledge base
    interpretation_file = YOUK_ROOT / "knowledge" / "interpretation" / "user-intent.md"
    interpretation_context = ""
    if interpretation_file.exists():
        interpretation_context = f"\n\nKnown interpretation patterns for this user:\n{interpretation_file.read_text()[:2000]}"

    if not _ANTHROPIC_AVAILABLE:
        return {
            "problem": raw_input,
            "success_criteria": "Task completed as described.",
            "constraints": [],
            "architecture_recommendation": "Proceed with standard patterns for this domain.",
            "anti_patterns": [],
            "out_of_scope": [],
            "ambiguity_detected": len(raw_input.split()) < 8,
            "clarifying_questions": ["Could you describe the expected output in concrete terms?"] if len(raw_input.split()) < 8 else [],
            "estimated_size": "M",
            "token_efficiency_gain": "n/a",
            "raw_input": raw_input,
            "mode": "fallback_no_api",
        }

    user_content = f"Raw input: {raw_input}"
    if clarified_context:
        user_content += f"\n\nAdditional context from conversation: {clarified_context}"

    try:
        response = _CLIENT.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=_INTENT_SYSTEM_PROMPT + interpretation_context,
            messages=[{"role": "user", "content": user_content}],
        )
        text = response.content[0].text.strip()
        # Extract JSON from response (model may wrap in markdown)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            import json
            result = json.loads(json_match.group())
            result["raw_input"] = raw_input
            result["mode"] = "api_optimized"
            return result
        else:
            raise ValueError("No JSON in response")
    except Exception as e:
        error_msg = str(e)
        # Surface the actual error so it can be debugged, not silently swallowed
        if not _API_KEY:
            error_msg = (
                "ANTHROPIC_API_KEY not set and /claude/.anthropic/api_key not found. "
                "Set the env var in your shell profile or create the fallback file. "
                f"Original error: {e}"
            )
        return {
            "problem": raw_input,
            "success_criteria": "Task completed as described.",
            "constraints": [],
            "architecture_recommendation": "Proceed with standard patterns.",
            "anti_patterns": [],
            "out_of_scope": [],
            "ambiguity_detected": False,
            "clarifying_questions": [],
            "estimated_size": "M",
            "token_efficiency_gain": "n/a",
            "raw_input": raw_input,
            "mode": "api_error",
            "error": error_msg,
        }
