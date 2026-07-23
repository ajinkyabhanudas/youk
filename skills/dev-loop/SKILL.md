---
name: dev-loop
rationale_why: "Implementation without a shared plan produces code that solves the wrong problem correctly. This anchors direction before the first line is written."
description: >
  Advanced developer coding assistant that understands language, stack, task, and
  end-goal to then write, audit, test, refactor, and iteratively improve code with
  best practices. Activate when a developer asks to write, review, audit, test,
  refactor, or improve code — or any combination of these. Also triggers on: "write
  this for me", "audit this code", "review my implementation", "help me refactor",
  "make this better", "find bugs", "write tests for this", "improve this function",
  "clean this up", or any request involving code quality, correctness, performance,
  or iterative improvement. Use this skill even for simple code tasks — the context
  capture and phase discipline always improve output quality.
---

# dev-loop — Advanced Developer Coding Skill

A phase-gated agentic loop for writing, auditing, testing, and refactoring code.
Built for developers who want rigorous, iterative, best-practice output — not a
one-shot guess.

---

## Invocation Grammar

Users can invoke any phase by name. Claude enters at the specified phase and
continues forward unless told to stop.

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full loop: UNDERSTAND → WRITE → AUDIT → TEST → REFACTOR |
| `write only` | UNDERSTAND → WRITE, then stop |
| `audit only` / `review this` | UNDERSTAND → AUDIT, then stop |
| `test only` | UNDERSTAND → TEST, then stop |
| `refactor only` | UNDERSTAND → REFACTOR, then stop |
| `audit + fix` | UNDERSTAND → AUDIT → REFACTOR |
| `audit + test + fix` | UNDERSTAND → AUDIT → TEST → REFACTOR |
| `loop: N` | Run AUDIT → TEST → REFACTOR up to N iterations |
| `enter: AUDIT` | Skip to AUDIT phase (assumes code is already in context) |

---

## Context Capture (Always First)

Before any phase, extract or ask for:

```
LANGUAGE:     [e.g. TypeScript, Python 3.11, Rust, Go]
FRAMEWORK:    [e.g. Next.js 14, FastAPI, Axum, none]
RUNTIME:      [e.g. Node 20, CPython, browser, edge, embedded]
TASK:         [one sentence — what this code must do]
END GOAL:     [what success looks like — perf target, correctness guarantee, etc.]
CONSTRAINTS:  [style guide, no external deps, existing API contract, etc.]
OUTPUT FMT:   [full file | diff | annotated | inline-comments]
EXISTING CODE:[paste / path / none]
```

If the user's message already answers most of these, infer and state assumptions
inline rather than asking again. Only ask if critical context is truly missing.

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — UNDERSTAND

0. **Scope-collapse gate** — if `route_task` returned `blocked: true` for this task
   (check for `blocked=True` in the routing result in recent context): surface the
   `collapsing_question` to the user immediately. Do NOT proceed to step 1 until the
   user answers. After their answer, re-call `optimize_intent(raw_input, clarified_context=<answer>)`
   then re-call `route_task`. Only proceed when `route_task` returns `blocked: false`.
   This gate mirrors the scope-collapse behavior in `servers/core/src/intent.py` —
   `ambiguity_detected=true` blocks routing until the implementation fork is resolved.

1. Parse the task. Restate it in one sentence: what must the code do, and what does
   done look like?
2. Identify the language, framework, runtime, and any constraints.
3. **NFR Gate check**: Is this a non-trivial feature (new module, new external I/O,
   new endpoint, user-facing change)? If yes, call `youk-core.check_nfr_gate(task, size, nfr_decision_block)`
   where `size` is the value from `route_task`. If it returns `blocked: true`, pause: "This feature needs an NFR check before
   implementation. Run `/nfr-check` first, then resume dev-loop with the NFR Decision
   Block as context." Do not proceed to WRITE while blocked.
   Skip this check only for: bug fixes, test additions, documentation changes, and
   hotfixes to existing behavior.
4. **Run the Stack Coverage check** (see Stack Coverage System below). If a gap is
   detected, pause here and propose generating the stack reference before continuing.
   Do not proceed to the next phase until the user responds.
5. **Scope-collapse check** — before writing a single line, model the solution space:
   - List every interpretation of the task that produces a materially different implementation.
   - For each, estimate: what changes, how many lines, which files touched.
   - If two interpretations differ by more than trivially (>10 lines, different files, different API contract): ask the one question whose answer collapses the fork. Wait for the answer. Do not proceed to WRITE until the fork is resolved.
   - If interpretations converge to the same implementation: state your reading in the CONTEXT BLOCK and proceed. Do not ask.
   - **The test before asking:** "If I'm wrong about this assumption, how much do I throw away?" More than a few lines → ask. Almost nothing → state and proceed.
   - Never ask about something answerable from existing context. Never ask more than one question per turn.
6. Declare the entry point for the next phase.

> Output: a compact CONTEXT BLOCK (≤10 lines) carried into all subsequent phases as
> the source of truth. If scope-collapse required a question, write CONTEXT BLOCK
> after the answer arrives — not before.

---

### Phase 2 — WRITE

0. **Minimal-path check** — before writing, answer: what is the smallest implementation
   that satisfies the constraint stated in CONTEXT BLOCK? Write that. Not a generalized
   version, not a future-proof version. If a dict covers the use case, don't add Redis.
   If one function covers it, don't add a class. Additions require a stated reason tied
   to a constraint in CONTEXT BLOCK — not anticipated future use.
1. Write the implementation using idiomatic patterns for the detected language
   and framework.
2. Apply best practices by default — see `references/best-practices.md` for
   language-specific defaults.
3. Include inline comments for non-obvious decisions; omit comments for
   self-evident code.
4. Declare what the code does *not* handle (out-of-scope) to set expectations.
5. Output in the format declared in CONTEXT BLOCK (full file / diff / annotated).

> Compact phase summary: "Written — N lines, covers X, does not handle Y."

---

### Phase 3 — AUDIT

Run the audit checklist from `references/audit-checklist.md`. Work through each
category systematically.

Emit findings as:

```
[FINDING: SEVERITY] Category — Description
  Location: function/line/block
  Risk: what breaks or degrades
  Fix: one-line recommendation
```

Severity levels: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `INFO`

After all findings:
- Count by severity
- State whether the code is safe to ship as-is, needs fixes before ship, or is
  blocked

> If zero findings: say so explicitly. Do not invent issues to seem thorough.

---

### Phase 4 — TEST

1. Identify what needs testing: public API surface, edge cases, failure modes,
   performance-sensitive paths.
2. Generate a test plan (bullet list, ≤15 items) before writing any test code.
3. Write tests using the idiomatic test framework for the language/runtime:
   - Python → pytest
   - TypeScript/JS → Vitest or Jest (prefer Vitest for new projects)
   - Go → testing package + testify
   - Rust → built-in #[test]
   - Other → ask or default to closest standard
4. Tests must be **runnable**, not pseudocode. Include all imports and any
   required fixtures or mocks.
5. Cover: happy path, boundary values, invalid inputs, error propagation,
   and at least one concurrency/async case if relevant.
6. If no runtime is available, produce test files + a `test_plan.md` describing
   expected outputs.

> Compact phase summary: "N tests written. Coverage: happy path ✓, edge cases ✓,
> error handling ✓, [missing: X]."

---

### Phase 5 — REFACTOR

1. Apply all `CRITICAL` and `HIGH` fixes from the AUDIT phase.
2. Apply `MEDIUM` fixes unless the user said to skip them.
3. Re-check: does the refactored code still pass the test plan from Phase 4?
4. Note every change made as a brief changelog:
   ```
   CHANGED: [what] → [why]
   ```
5. After refactoring, re-run a **mini-audit** (CRITICAL + HIGH only) to confirm
   no regressions were introduced.
6. If new issues are found → loop back to AUDIT (up to 3 iterations by default,
   configurable with `loop: N`).

> Compact phase summary: "Refactored. N changes. Mini-audit: clean / N new findings."

---

## Loop Control

The loop continues automatically if:
- The mini-audit in REFACTOR finds new CRITICAL or HIGH issues
- Test failures are detected that weren't present before refactoring
- The user says `continue` or `loop again`

The loop stops when:
- Mini-audit is clean (no CRITICAL/HIGH findings)
- `loop: N` limit is reached
- The user says `stop` or `done`

**Convergence failure — ESCALATION BLOCK:**

If `loop: N` limit is reached and CRITICAL or HIGH findings remain unresolved, do NOT loop again. Emit an ESCALATION BLOCK instead:

```
[ESCALATION BLOCK]
Iterations: N (limit reached)
Unresolved: {N CRITICAL, M HIGH}
Root cause hypothesis: {wrong approach | missing dependency | scope too large | external blocker}

Findings that didn't converge:
  - {finding}: {why each iteration failed to fix it}

Recommendation: {one of:}
  - SIMPLIFY: the approach is adding complexity, not removing it — restart with a simpler design
  - SPLIT: the scope is too large for one dev-loop; break into independent sub-tasks
  - ESCALATE: unresolvable without a decision from the founder (architectural blocker)
  - ACCEPT: remaining findings are LOW risk; ship with known tech debt documented
```

After 3 iterations without convergence, the problem is the **approach**, not the implementation. Stop. Diagnose. Don't loop again with the same approach.

At the end of each loop iteration (non-escalation), emit:

```
[ITERATION N COMPLETE]
Status: CLEAN | ISSUES REMAIN
Open findings: [count by severity]
Next action: [loop again | stop | awaiting instruction]
```

---

## Output Contracts

| Format | When to use |
|--------|-------------|
| **Full file** | New code, or changes >40% of original |
| **Diff** | Targeted fixes to existing code |
| **Annotated** | When the user needs to understand every decision |
| **Inline-comments** | When adding context without changing structure |

Default to **full file** for new code, **diff** for audits/refactors unless the
user specifies otherwise.

---

## Quality Bars (Non-Negotiable)

These apply regardless of phase or invocation mode:

- No hardcoded secrets, credentials, or environment-specific magic strings
- No `TODO` left in output unless the user asked for a scaffold
- No dead code in the final output
- Error paths must be handled explicitly — no silent swallows
- All public functions/methods must have docstrings/JSDoc/rustdoc
- Complexity: flag any function over 30 lines or cyclomatic complexity > 7
- Dependencies: prefer stdlib; if adding a dep, state why and the tradeoff

---

## Reference Files

Read these files when the relevant phase is active:

| File | When to read |
|------|--------------|
| `references/audit-checklist.md` | AUDIT phase — before emitting findings |
| `references/best-practices.md` | WRITE + REFACTOR phases — language defaults |
| `references/test-strategies.md` | TEST phase — framework patterns and fixtures |
| `references/stacks/[stack].md` | Any phase — if a stack-specific file exists for the detected stack |

---

## Stack Coverage System

The skill detects the stack during UNDERSTAND and checks whether deep reference
coverage exists for it. If coverage is missing or shallow, the skill proposes
generating it before continuing — so the references grow with your work rather
than staying static.

### Step 1 — Detect the stack

During UNDERSTAND, identify the full stack fingerprint:

```
LANGUAGE:    [TypeScript / Python / Go / Rust / other]
FRAMEWORK:   [React / Next.js / FastAPI / Axum / Django / Vue / Svelte / other]
RUNTIME:     [Node / browser / edge / CPython / etc.]
TOOLING:     [Vite / Webpack / pnpm / poetry / etc.]
STATE:       [Zustand / Redux / Jotai / React Query / none / other]
TESTING:     [Vitest / Jest / pytest / testing / other]
```

### Step 2 — Check coverage

After building the stack fingerprint, check `references/stacks/` for a matching
file (e.g. `react.md`, `nextjs.md`, `vue.md`, `django.md`).

Coverage is **sufficient** if:
- A stack file exists for the primary framework
- It covers best practices, audit checks, and test patterns for that stack

Coverage is **missing or shallow** if:
- No stack file exists for the detected framework
- The framework is only briefly mentioned in `best-practices.md`

### Step 3 — Propose an update if needed

If coverage is missing or shallow, pause before proceeding and tell the user:

```
[STACK GAP DETECTED]
Stack: [framework + version]
Coverage: none / shallow (only generic [language] defaults available)

I can generate a dedicated reference file for [framework] covering:
- Idiomatic patterns and anti-patterns
- Framework-specific audit checks
- Test strategy and recommended libraries
- Common performance and security gotchas

This will be saved to references/stacks/[framework].md and used for all
future sessions with this stack.

Generate it now? [yes / no / skip for this session]
```

### Step 4 — Generate and save the stack reference

If the user confirms, generate the stack reference file covering:

1. **Patterns** — idiomatic component/module/service patterns for the framework
2. **Anti-patterns** — what to avoid and why
3. **Audit additions** — framework-specific checks to layer on top of the base
   audit checklist (e.g. React: missing keys, inline handlers, prop drilling)
4. **Performance** — framework-specific perf gotchas
5. **Security** — framework-specific attack surfaces
6. **Test strategy** — recommended libraries, patterns, and fixture examples
7. **Tooling** — linters, formatters, config defaults

Save to `references/stacks/[framework-name].md`.

Then confirm:
```
[STACK REFERENCE SAVED]
File: references/stacks/[framework].md
Continuing with full [framework] coverage active.
```

Then proceed with the original task using the new reference loaded.

### Step 5 — Use the stack reference in all phases

Once a stack file exists, load it alongside the base reference files:
- WRITE: base best-practices + stack patterns
- AUDIT: base checklist + stack audit additions
- TEST: base test strategies + stack test patterns
- REFACTOR: base best-practices + stack anti-patterns to eliminate

### Covered stacks (built-in)

These have at least basic coverage in `best-practices.md` already:

| Stack | Coverage level |
|-------|---------------|
| TypeScript / Node | Good |
| Python / FastAPI | Good |
| Go | Good |
| Rust / Tokio | Good |
| React / Next.js | Shallow — stack gap will trigger |
| All others | None — stack gap will trigger |

---

## Example Flows

**New stack encountered (React):**
> "Build a dashboard component in React with Zustand for state."

Claude: UNDERSTAND → detects React + Zustand → checks references/stacks/ → no
react.md found → pauses → proposes generating react.md → user confirms → generates
and saves references/stacks/react.md → continues full loop with React coverage active.

**Stack already covered:**
> "Add a new FastAPI endpoint with JWT auth."

Claude: UNDERSTAND → detects Python + FastAPI → checks references/stacks/ →
fastapi.md exists → loads it → continues full loop without interruption.

**Full loop, new feature:**
> "Write a rate limiter middleware for Express. TypeScript, Node 20, use in-memory
> store for now. Loop until clean."

Claude: UNDERSTAND → WRITE → AUDIT → TEST → REFACTOR → [loop if needed] → done.

**Audit-only, existing code:**
> "Audit this Python function for security and performance. audit only."

Claude: UNDERSTAND → AUDIT → stop.

**Targeted fix:**
> "This Go handler has a data race. enter: AUDIT."

Claude: skips UNDERSTAND/WRITE → AUDIT → REFACTOR → mini-audit.

**Iterative improvement:**
> "Refactor this for readability. loop: 2."

Claude: UNDERSTAND → REFACTOR → mini-audit → loop if needed, max 2 iterations.
