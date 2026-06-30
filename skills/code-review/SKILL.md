---
name: code-review
description: >
  Structured code review against correctness, safety, and quality bars.
  Produces a line-level verdict with severity-tagged findings and a single
  top-level verdict: APPROVED, APPROVED WITH COMMENTS, or NEEDS REVISION.
  Triggers on: /done workflow command, explicit review request, before any
  commit touching shared infrastructure, auth, or data paths. Not a style
  linter — style violations are INFO only unless they mask a logic issue.

fast-path: |
  If the diff is ≤10 lines and touches only: comments, variable renames,
  string literals, or test fixture values — emit APPROVED WITH COMMENTS
  immediately. Note what was checked. Skip ANALYZE and SECURITY phases.
---

# code-review — Structured Code Review Skill

Phase-gated review that separates what the code does from whether it is
safe, correct, and maintainable. The verdict is always explicit — no
"looks good to me" without evidence.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full review: SCOPE → ANALYZE → SECURITY → VERDICT |
| `quick` | SCOPE → VERDICT only — surface CRITICAL and HIGH, skip MEDIUM/LOW |
| `security only` | SCOPE → SECURITY → VERDICT — skip logic and quality analysis |
| `enter: ANALYZE` | Skip SCOPE (diff already in context), go straight to analysis |

---

## Context Capture

Before any phase, establish:

```
DIFF:         [git diff or file contents being reviewed]
SCOPE:        [what changed — feature / bug fix / refactor / config / infra]
RISK TIER:    [LOW: tests/docs | MED: business logic | HIGH: auth/data/infra/API]
TEST STATUS:  [tests exist and pass / tests missing / not applicable]
PRIOR CONTEXT:[relevant decisions, constraints, or contracts this touches]
```

If the diff is not in context, ask for it before proceeding. Everything
else can be inferred.

---

## The Four Phases

Each phase begins with `[PHASE: NAME]`.

---

### Phase 1 — SCOPE

1. Parse what changed: which files, which layers (API / logic / data / config / infra).
2. Classify risk tier from the context block.
3. Identify the intent: what problem is this solving? State it in one sentence.
4. Flag any scope smell: change touches more than one concern, unrelated files
   modified, missing tests for changed behaviour.
5. State what the review will focus on — and what it will skip (out of scope).

> Compact phase summary: "N files, risk tier X, intent: Y. Review focus: Z."

---

### Phase 2 — ANALYZE

Work through the diff systematically. Emit findings as:

```
[FINDING: SEVERITY] Category — Description
  Location: file:line or function name
  Risk: what breaks or degrades if this is not addressed
  Fix: one-line recommendation
```

Severity levels: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `INFO`

Categories to check (skip categories with no applicable surface):

**Logic**
- Off-by-one, boundary conditions, null/None paths
- Control flow that can be bypassed or short-circuited unintentionally
- Async/concurrent access to shared state
- Return values that are silently ignored

**Error handling**
- Exceptions caught too broadly (bare `except`, `catch (e) {}`)
- Error paths that succeed silently
- Missing cleanup in error paths (open files, DB connections, locks)

**Data**
- Input validation missing at system boundary
- Type coercion that can produce unexpected values
- Mutation of data that callers expect to be immutable

**Quality**
- Functions over 30 lines or cyclomatic complexity > 7 — flag, don't block
- Dead code in the final output
- Magic strings or numbers without named constants (HIGH if in auth/routing)

**Tests**
- Changed behaviour with no corresponding test change — HIGH if risk tier MED+
- Tests that pass trivially (assert True, mock that always returns success)

After all findings:
- Count by severity
- State ship-readiness: SAFE TO SHIP AS-IS / NEEDS FIXES BEFORE SHIP / BLOCKED

> Compact phase summary: "N findings (X CRITICAL, Y HIGH, Z MEDIUM). Ship status: ___."

---

### Phase 3 — SECURITY

Run only the checks applicable to the detected risk tier. Skip categories
with no surface in this diff.

**Always check (any risk tier):**
- Hardcoded secrets, API keys, passwords, tokens — CRITICAL if present
- File paths constructed from user input without sanitisation
- Subprocess/shell calls with unvalidated input (command injection)

**HIGH risk tier additionally:**
- Authentication bypass: can the auth check be skipped?
- Authorisation: does the code check who is allowed, not just who is authenticated?
- Data exposure: does error output leak internal state, stack traces, or PII?
- Dependency: is a new external package added? State name + purpose + known CVEs if any.

**youk-specific checks (always):**
- Does any new code write outside `/youk/` or `/claude/skills/`? — CRITICAL
- Does any new MCP tool bypass the `confirmed=True` requirement for destructive actions?
- Does any code store raw conversation content (transcripts, chat history)? — CRITICAL

> Compact phase summary: "Security checks complete. N issues. Highest severity: ___."

---

### Phase 4 — VERDICT

```
[VERDICT]
Status:   APPROVED | APPROVED WITH COMMENTS | NEEDS REVISION

Summary:  {One sentence — what the code does and whether it is safe.}

Must fix before merge:
  {List CRITICAL and HIGH findings with fix. Empty if none.}

Should fix (non-blocking):
  {List MEDIUM findings. Can merge with known tech debt.}

Notes (INFO):
  {Style, naming, optional improvements. Author's call.}

Evidence:
  {What was checked — phases run, categories covered, risk tier applied.}
```

Rules:
- `NEEDS REVISION` if any CRITICAL or HIGH finding is unresolved
- `APPROVED WITH COMMENTS` if only MEDIUM/LOW/INFO findings remain
- `APPROVED` if zero findings or only INFO
- Never `APPROVED` without completing at least SCOPE + ANALYZE

---

## Quality Bars (Non-Negotiable)

- **Every CRITICAL finding blocks.** APPROVED cannot be issued with an unresolved CRITICAL.
- **Evidence is mandatory.** "Looks good" is not a verdict. State what was checked.
- **Security phase runs on HIGH risk tier always.** Not skippable even in `quick` mode.
- **Missing tests on changed logic = HIGH.** Not MEDIUM. Logic changes without tests are HIGH risk.
- **youk write-path violations are CRITICAL.** Any code that writes outside permitted paths blocks immediately.
- **No invented findings.** If zero issues, say so explicitly. Do not generate noise to seem thorough.

---

## Reference Files

| File | When to read |
|------|--------------|
| `references/severity-guide.md` | ANALYZE phase — borderline severity calls |
| `references/security-checklist.md` | SECURITY phase — full checklist by risk tier |

---

## Example Flows

**Standard /done review:**
> After implementing a new MCP tool in server.py

SCOPE (1 file, server.py, risk tier MED — new tool signature) → ANALYZE
(check: parameter types, error handling, no hardcoded values, docstring
present) → SECURITY (check: does tool bypass confirmed= requirement?) →
VERDICT (APPROVED WITH COMMENTS: docstring missing from one helper function)

**Quick review before commit:**
> "review this quick"

SCOPE (3 files, risk tier LOW — rename + comment changes) → VERDICT
(APPROVED — changes are cosmetic, no logic touched, fast-path applies)

**Security-only review:**
> "security only — this touches the auth flow"

SCOPE → SECURITY (full HIGH-tier checklist: auth bypass check, data
exposure check, dependency check) → VERDICT
