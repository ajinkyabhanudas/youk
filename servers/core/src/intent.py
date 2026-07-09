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

Before generating clarifying questions, model the solution space fork:
For each interpretation of the request, estimate what the implementation looks like.
The question that distinguishes the interpretations most efficiently is the right one to ask.
A question is only worth asking if the answer changes what gets written by more than trivially.
Never ask about something you can infer from context or assume safely.

Output ONLY valid JSON matching this schema:
{
  "problem": "1-2 sentences, specific and actionable",
  "success_criteria": "measurable outcome — what done looks like",
  "constraints": ["technical", "scope", "time constraints"],
  "architecture_recommendation": "concrete pattern recommendation with one sentence rationale",
  "anti_patterns": ["pattern to avoid and why", "..."],
  "out_of_scope": ["explicit exclusions"],
  "solution_fork": {
    "if_interpretation_A": "what the minimal implementation looks like under this reading — one sentence",
    "if_interpretation_B": "what the implementation looks like under the alternative reading — one sentence",
    "lines_delta": "rough difference in implementation size between A and B (e.g. '5 lines vs 80 lines')",
    "collapsing_question": "the single question whose answer makes A vs B obvious"
  },
  "ambiguity_detected": true/false,
  "clarifying_questions": ["at most one question — the collapsing_question if ambiguity_detected, else empty"],
  "estimated_size": "XS/S/M/L/XL",
  "token_efficiency_gain": "estimated token reduction vs. proceeding with raw input (e.g. '60%')"
}

Rules:
- solution_fork is required when ambiguity_detected is true. When ambiguity_detected is false, set solution_fork to null.
- clarifying_questions must contain AT MOST ONE item — the question from solution_fork.collapsing_question.
- Never ask about something answerable from context. Never ask multiple questions.
- If the input is already clear and specific, set ambiguity_detected to false and clarifying_questions to [].
- If the input mentions multiple unrelated concerns, separate them and note that in constraints.
- Always recommend a concrete architecture pattern — never say "it depends" without a default recommendation.
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
    "fix the bug": {
        "problem": "Diagnose and fix a specific bug. Goal: reproduce it first, understand root cause, fix minimally, verify it doesn't recur.",
        "architecture_recommendation": "Reproduce → isolate → fix → verify. Resist the urge to refactor while fixing; keep the diff minimal and focused.",
        "anti_patterns": ["Fixing symptoms not root cause", "Rewriting surrounding code while fixing", "Committing without a reproduction test"],
        "out_of_scope": ["Refactoring", "Adding unrelated features"],
        "ambiguity_detected": True,
        "clarifying_questions": ["What's the symptom? What's the expected behaviour? Can you reproduce it reliably?"],
        "estimated_size": "S",
    },
    "add a test": {
        "problem": "Add a test for the specified behaviour. Covers the happy path, at least one error state, and the specific case that was previously untested.",
        "architecture_recommendation": "Mirror the existing test structure. Integration tests over mocks for behaviour that touches real I/O. One assertion per test case concept.",
        "anti_patterns": ["Mocking the thing you're testing", "Testing implementation details not behaviour", "Green tests with no assertions"],
        "out_of_scope": ["Refactoring production code to make it testable — do that first, separately"],
        "ambiguity_detected": True,
        "clarifying_questions": ["Which function or behaviour? What's the failure mode you most want to catch?"],
        "estimated_size": "XS",
    },
    "review this": {
        "problem": "Review the code currently in context for correctness, safety, and maintainability. Not a style review — identify real risks.",
        "architecture_recommendation": "Focus on: logic errors, missing error handling, security risks (credential exposure, injection), untested edge cases, performance surprises.",
        "anti_patterns": ["Style-only review", "Praising without flagging real concerns", "Suggesting rewrites instead of targeted fixes"],
        "out_of_scope": ["Implementing the fixes — surface them, don't apply them unless asked"],
        "ambiguity_detected": False,
        "clarifying_questions": [],
        "estimated_size": "S",
    },
    "write a spec": {
        "problem": "Write a functional specification for a feature before implementation begins. Forces scope definition, acceptance criteria, and explicit out-of-scope decisions.",
        "architecture_recommendation": "User-facing language: what it does, not how. Include: goal, success criteria (measurable), constraints, out of scope, open questions.",
        "anti_patterns": ["Implementation detail in a spec", "Acceptance criteria that can't be tested", "Missing out-of-scope list"],
        "out_of_scope": ["Implementation — spec first, code second"],
        "ambiguity_detected": True,
        "clarifying_questions": ["What is the feature? Who is the primary user? What does 'done' look like?"],
        "estimated_size": "M",
    },
    "should i build": {
        "problem": "Evaluate whether to build a feature vs. buy/use existing, defer, or drop. The question is prioritisation and scope, not implementation.",
        "architecture_recommendation": "Build vs. buy vs. defer framework: does this create competitive advantage? What's the maintenance cost? What's the opportunity cost?",
        "anti_patterns": ["Jumping to implementation before validating the premise", "Ignoring existing solutions", "Building to learn without a clear learning goal"],
        "out_of_scope": ["Implementation details — decide first"],
        "ambiguity_detected": True,
        "clarifying_questions": ["What problem does it solve? Who needs it? What happens if you don't build it?"],
        "estimated_size": "S",
    },
    "add logging": {
        "problem": "Add observability to an existing function or module. Goal: make failure modes visible without changing behaviour.",
        "architecture_recommendation": "Structured logs (key=value or JSON). Log at entry + exit for slow operations. Log error + context (not just the exception message). Avoid logging secrets.",
        "anti_patterns": ["Logging everything at DEBUG in production paths", "Log strings without structured fields", "Logging after the error without preserving context"],
        "out_of_scope": ["Alerting, dashboards — that's infrastructure, not this task"],
        "ambiguity_detected": True,
        "clarifying_questions": ["Which function or code path? What failure mode are you trying to catch?"],
        "estimated_size": "XS",
    },
    "deploy this": {
        "problem": "Deploy the current version to the target environment. Includes pre-deploy checklist, migration steps, and rollback plan.",
        "architecture_recommendation": "Deploy checklist: tests pass, migrations reviewed, env vars set, rollback plan documented, canary or staged rollout if user-facing.",
        "anti_patterns": ["Deploy without a rollback plan", "Skip DB migration review", "Deploy on Friday afternoon"],
        "out_of_scope": ["Feature work — deploy what's ready, not what's half-done"],
        "ambiguity_detected": True,
        "clarifying_questions": ["Which environment? Is there a DB migration? What's the rollback plan?"],
        "estimated_size": "M",
    },
    "what's wrong with": {
        "problem": "Diagnose the issue in the code or system currently in context. Surface the root cause, not just symptoms.",
        "architecture_recommendation": "Reproduce first. Read the error message carefully — it usually names the line. Check the call stack, not just the error site.",
        "anti_patterns": ["Guessing without reproducing", "Fixing the symptom without the root cause", "Adding error suppression to make the symptom disappear"],
        "out_of_scope": ["Refactoring — diagnose first"],
        "ambiguity_detected": True,
        "clarifying_questions": ["What's the error or unexpected behaviour? When does it happen?"],
        "estimated_size": "S",
    },
    "explain this": {
        "problem": "Explain the selected code or concept clearly. Goal: the reader understands what it does, why it's written this way, and what would break if it changed.",
        "architecture_recommendation": "Top-down: purpose → structure → key decisions → gotchas. Use analogies for non-obvious patterns. Name the invariants explicitly.",
        "anti_patterns": ["Line-by-line translation of code into English", "Explaining the obvious", "Missing the 'why'"],
        "out_of_scope": ["Refactoring or changing the code being explained"],
        "ambiguity_detected": False,
        "clarifying_questions": [],
        "estimated_size": "XS",
    },
    "simplify this": {
        "problem": "Reduce complexity in the code currently in context without changing behaviour. Target: a junior engineer can understand it in 5 minutes.",
        "architecture_recommendation": "Flatten nesting, extract named helpers for non-obvious chunks, replace clever one-liners with readable two-liners. Measure before/after cyclomatic complexity if available.",
        "anti_patterns": ["Simplifying by moving complexity elsewhere", "Changing behaviour while simplifying", "Over-abstracting to 'simplify'"],
        "out_of_scope": ["Performance optimization", "Feature changes"],
        "ambiguity_detected": True,
        "clarifying_questions": ["Which part feels most complex? What's the target audience for the simplified version?"],
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
        is_ambiguous = len(raw_input.split()) < 8
        return {
            "problem": raw_input,
            "success_criteria": "Task completed as described.",
            "constraints": [],
            "architecture_recommendation": "Proceed with standard patterns for this domain.",
            "anti_patterns": [],
            "out_of_scope": [],
            "solution_fork": {
                "collapsing_question": "Could you describe the expected output in concrete terms?"
            } if is_ambiguous else None,
            "ambiguity_detected": is_ambiguous,
            "clarifying_questions": ["Could you describe the expected output in concrete terms?"] if is_ambiguous else [],
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
            "solution_fork": None,
            "ambiguity_detected": False,
            "clarifying_questions": [],
            "estimated_size": "M",
            "token_efficiency_gain": "n/a",
            "raw_input": raw_input,
            "mode": "api_error",
            "error": error_msg,
        }
