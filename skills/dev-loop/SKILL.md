---
name: dev-loop
rationale_why: "Implementation without a shared plan produces code that solves the wrong problem correctly. This anchors direction before the first line is written."
description: >
  Phase-gated coding loop: write, audit, test, refactor. Triggers on combined-phase
  requests — "write and test", "audit and fix", "refactor with tests", any full-loop
  code task, or explicit phase flags (audit only, write only, loop: N). Also triggers
  on: "review my implementation", "find bugs", "improve this function", "clean this up",
  or multi-step code quality requests. Do not trigger for: single-sentence explain
  requests, one-line rename/typo fixes, doc-only edits, or pure Q&A about code with
  no write/audit/test intent — those route directly without ceremony.
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
**Parent-task anchor (fires when task is a decomposition):**
If the current task was produced by breaking a larger goal into sub-tasks:
1. At decomposition time: write `state/parent-task.json` with {parent_goal, success_criteria, sub_tasks: [...], completed: []}.
2. Before routing any sub-task follow-up: read the anchor. If the conversation has moved more than 3 exchanges without touching a parent criterion — emit one line: "Parent goal: {parent_goal} — still open. Current sub-task: {sub_task}." Then continue.
3. When a sub-task completes (task_checkpoint called): move it to completed[]. When completed == sub_tasks: surface "Parent goal satisfied — run /done to close." and delete the anchor.
4. If the user's follow-up question is scoped only to the sub-task and does not touch the parent goal: answer it, but do not update the anchor. Sub-task drift ≠ parent drift. Only emit the reorientation when the parent criteria are at risk of being forgotten, not on every sub-task exchange.
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

0b. **Blast-radius trip-wire** — a cost-tiered guard against drifted fixes: a change that is
   locally correct but breaks something downstream because you didn't check what depends on it.
   Each tier gates the next, so cost tracks actual risk — you never pay the expensive tier on a
   local edit.

   Applies when: about to modify or delete an EXISTING shared surface — a function signature,
   a return-value shape, a constant/flag other code reads, a schema, a string another branch
   matches on. Skip entirely for: brand-new code, test files, comments, and additive-only
   changes that touch no existing dependent.

   - **Tier 1 — free grep (always, when the guard applies):** one search for dependents of the
     symbol you're changing — `grep` its name, and for a string/flag also grep any `startswith`
     / `==` / membership check against it. If zero dependents → proceed, no further cost.
   - **Tier 2 — find_affected (only if Tier 1 shows dependents):** call
     `youk-core.find_affected(file_path, project_slug)` to map the reach. State in one line what
     depends on this and how the change affects each. If the reach is contained and understood →
     proceed.
   - **Tier 3 — challenge (only if the change is FORCED by an error/regression/reversal AND
     Tier 2 shows the change alters behavior other code relies on):** this is the drifted-fix
     danger zone — a fix made under the pressure of something breaking, touching depended-on
     behavior. Route the DOWNSTREAM IMPACT (not the local fix) through `challenge`: does this fix
     hold the system's actual intent, or does it satisfy the local failure while breaking the
     contract the dependents assume? Resolve before writing.

   The rule this encodes: the cost of the check must stay below the cost of the rework it prevents.
   A one-line grep is cheaper than a failed test cycle; a failed test cycle is cheaper than a
   drifted fix that ships. Spend at the tier the risk justifies, never above it. (Worked example:
   changing `_update_resume_point` to "strip all prefixes" was locally correct but a Tier-1 grep
   for `startswith("Resume:")` would have surfaced session_start's dependency BEFORE the broken
   test — Tier 1 alone would have caught it.)

   **Known limits (do not oversell this guard):** Tier 1 finds STATIC dependents. It will miss
   dynamic references (getattr, string interpolation, cross-boundary deps like a Python symbol
   read by CLAUDE.md prose) — for those, a passing grep does not prove safety. And this guard is
   prose-triggered: it works only if step 0b actually runs. It is deliberately kept to one grep
   precisely so the cost of running it is too low to rationalize skipping — a heavier check here
   would be skipped under pressure and be worse than none. It reduces drifted fixes; it does not
   eliminate them.
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

**Drift check (mandatory when this pass modified an existing shared surface):** for each change
to a depended-on symbol, ask "what assumed the old behavior, and does it still hold?" If the
blast-radius trip-wire (WRITE step 0b) escalated to Tier 2/3, confirm its finding was addressed.
A fix that passes its own test but changes a contract a dependent relies on is a `HIGH` finding,
not a pass — the local test cannot see the dependent.

After all findings:
- Count by severity
- State whether the code is safe to ship as-is, needs fixes before ship, or is
  blocked

> If zero findings: say so explicitly. Do not invent issues to seem thorough.

**Emit the examination surface block at the end of every AUDIT phase:**

```
[EXAMINATION SURFACE — dev-loop AUDIT]
Task type:    {new_endpoint | schema_change | ui_component | bug_fix | refactor | other}
Examined:     [comma-separated list of domains actually checked]
              Valid domains: error_handling, auth, rate_limiting, idempotency,
              data_validation, concurrency, naming, complexity, tests, security_injection,
              security_secrets, performance, data_volume, consistency, logging
Not examined: [domain — reason]
              e.g. "auth — read-only endpoint, no auth surface"
              e.g. "concurrency — single-threaded, no shared state"
```

Rules:
- "Not examined" with no reason = SCOPE_MISS in the signal detector. Always give a reason.
- If a domain is in scope for the task type but was not examined: list it in Not examined with reason "time constraint" or "skipped" — do not omit it. Omission is indistinguishable from examination.
- Task type drives expected domains (from `references/skill-scope-matrix.yaml` when it exists).

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

## Before writing new code
**Rework-vs-patch check (fires whenever a direction is corrected mid-task):**
When a plan or in-progress implementation is corrected — wrong shape,
wrong tool, wrong output type, anything caught before or during
implementation — do not simply patch the new decision onto the existing
surrounding design and continue. Explicitly ask: does this correction mean
an existing interface/module/pattern the new code will sit on top of also
needs to change, or does the existing surface genuinely still fit?

Concretely, before writing the next line of code after any correction:
1. Name the existing interface/contract the corrected piece will plug into.
2. Check whether that interface's original assumptions still hold given the
   correction (e.g. a boolean-returning interface built for keyword checks
   may not fit a richer categorical-plus-rationale result without losing
   information at the boundary).
3. If the interface no longer fits, decide explicitly — in front of the
   user if the answer isn't obvious — whether to widen/rework the shared
   interface now (bounded, scoped to what's needed) or to keep it
   unchanged and add a separate, additive path for the new case (not
   forcing a square peg through it).
4. Do NOT silently choose "patch around it" by default just because it's
   less code right now — that is exactly the kind of effort that "sticks"
   as debt once more is built on top of it, per explicit founder feedback
   on this exact failure mode.

This is a distinct gate from the existing-dependency scan
(PENDING-20260728100914) — that one prevents building new code that
duplicates something already available; this one prevents a *correction*
from becoming a patch bolted onto a design that no longer fits, once new
code has already started to accumulate on top of it.

---

## Phase 6 — COMMIT

Fires after REFACTOR is clean and the loop has stopped. Non-optional when code changed.

1. Draft the commit message: one subject line (≤72 chars, imperative mood), blank line,
   body (what changed and why — not a restatement of the subject).
2. Run `check_text` on the draft. If BLOCKED: rewrite and recheck before proceeding.
   If REVIEW: fix the soft tells, then recheck. Do not commit a BLOCKED or REVIEW message.
3. Call `route_to_skill("humanize", draft_message)`. Apply the returned rewrite if it
   changes anything. If humanize is unavailable, proceed with the check_text-cleared draft.
4. Commit with the cleared message.
5. Call `compact_context(project_dir)` after the commit.

No exceptions: every commit that exits dev-loop goes through steps 1-5. The voice gate
in the commit-msg hook is the last line of defense; this step is the first.