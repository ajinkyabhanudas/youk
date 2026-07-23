---
name: nfr-check
rationale_why: "NFR decisions made after code exists get embedded in the code and cost 10x to change. This gate makes them cheap — four questions now versus a production incident later."
description: >
  Pre-build non-functional requirements gate. Fires before any dev-loop invocation on
  non-trivial features. Forces explicit decisions on caching, retry, observability, auth,
  rate limits, idempotency, consistency, and data volume — before a single line of code
  is written. Prevents NFR decisions from being deferred until they become production
  incidents. Triggers on: "add feature", "build X", "implement Y", any new module,
  endpoint, background job, or integration point. Can also be invoked standalone for
  NFR-only review of an existing design.
---

# nfr-check — Non-Functional Requirements Gate

A phase-gated pre-build gate that forces explicit NFR decisions before implementation
begins. The core principle: NFRs decided after code is written become rework. NFRs
decided before code is written become architecture.

Built on the observation that most production incidents trace back to an NFR that was
"obvious" but never explicitly decided — caching strategy, retry limits, auth model,
observability scope. This skill makes that decision explicit and documented.

---

## Size Override: Always M+ for Global State Mutations

Before applying the S/M/L sizing from route_task, check:

Does this task write to any of:
- `~/.claude/` or any global Claude Code configuration
- A shared namespace used by multiple tools or developers (skill names, MCP server names, config keys)
- Global system config outside the current project directory
- A file or directory that other tools on this machine also write to

If yes: treat as M regardless of route_task's size. These tasks look small but have a blast radius that spans the entire developer environment — collision risk, irreversibility, and cross-tool interference are all real. An S-sized task that writes 7 files into `~/.claude/skills/` with generic names like `done` and `build` is an M task.

---

## Default Behaviour: 4 Core Questions

For any S or M feature (under ~3 days of work), skip the full phase structure.
Answer these 4 questions and emit a compact NFR block:

```
[NFR — QUICK]
1. 10x load?         {what breaks if traffic/data grows 10x from today}
2. External fails?   {what happens when the API/DB/LLM call fails or times out}
3. Safe to retry?    {can this be called twice safely — yes | no, reason}
4. What's logged?    {minimum: what goes in the log, what gets timed}

─ If any of these is an LLM call or external API ─
5. Cached?           {yes: key + TTL | no: reason} ← MANDATORY for LLM/API paths

─ If task mentions UI / CSS / dark / frontend / component / style ─
6. Dark mode?        {system preference respected? forced-colors handled? test at implementation time, not at review}

─ If task mentions benchmark / eval / measurement / re-run / scoring ─
7. Measurement integrity?  {is cache/state cleared before each run? are runs independent? is a baseline (control) included? without clearing, repeated runs measure cache behavior not model behavior}
```

These questions cover 80% of production incidents. No ceremony beyond this for S/M.
Proceed to dev-loop once all applicable questions are answered.
Q6 and Q7 are conditional — only ask when the task surface matches. Skip silently otherwise.

---

## Full NFR Check (L and XL features only)

Invoke the full 5-phase check when:
- Feature is L (1-2 weeks) or XL (multi-week)
- New external dependency being introduced
- Data schema change
- Auth model change
- Multi-service or multi-team impact

---

## Adaptive Mode (auto-selected from session state)

Before running any other mode, read `nfr_autonomy_mode` from the session_start return
(available in the context brief as `nfr_autonomy_mode: standard | validate`).

| Mode | When | Behaviour |
|------|------|-----------|
| `standard` | `nfr_autonomy_mode: standard` (default) | Full 4-question block — ask all questions |
| `validate` | `nfr_autonomy_mode: validate` (autonomy_rate ≥ 0.4) | Developer has internalized the gate. Scan the task description for existing NFR coverage. Only surface gaps — do not ask questions that are already answered. Emit `[NFR — VALIDATE]` block listing covered + missing. If all 4 are covered: emit `[NFR COVERED — developer pre-empted]` and proceed. |

When `validate` mode fires, emit a one-line note:
`[Adaptive] Running nfr_check in validate mode — you've been catching these before I ask.`

This is the signal to the developer that compounding is observable: youk is adjusting
its ceremony because their judgment has grown. Do NOT silently skip nfr_check —
always run it, even in validate mode, and always emit the [NFR DECISION BLOCK].
The block content is what changes (gaps only vs. all decisions), not whether it runs.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive, S/M feature)* | Auto-mode from session state (standard or validate) |
| `full` | Full 5-phase check — for L/XL features |
| `caching` | Caching category only |
| `retry` | Retry + timeout + idempotency only |
| `auth` | Authentication + authorization + audit logging only |
| `observability` | Logging + timing + alerting only |
| `for: [feature]` | Target a specific feature description inline |
| `review existing` | Audit an already-built feature for missing NFR coverage |

---

## Context Capture (Always First)

Before any phase, extract or infer:

```
FEATURE NAME:    [one-sentence description of what's being built]
FEATURE TYPE:    [new module | endpoint | UI component | background job | data pipeline | infrastructure | hotfix]
INTEGRATION:     [external API | database | file system | user-facing | internal-only | multi]
SCALE CONTEXT:   [single user | small team | public | unknown — affects which NFRs are mandatory]
EXISTING NFRS:   [yes/no — is there already an NFR Decision Block for this feature?]
RELATED ADRs:    [any architecture decisions already made that constrain the NFRs?]
```

If EXISTING NFRS is yes, read it first. Do not re-decide already-decided NFRs — only
check for gaps or conflicts with new information.

Only ask for missing context if it changes which NFR categories are mandatory.

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — CLASSIFY

Determine the feature type and integration points. This routes which NFR categories
are **mandatory** (must decide now), **conditional** (decide if relevant), or
**optional** (can defer with a stated reason).

Read `references/feature-type-matrix.md` for the routing table.

**Global config / shared namespace** is a feature type not in the matrix file.
If the task writes to a shared global namespace (skills, MCP servers, ~/.claude/,
global CLI config), add these mandatory NFRs before the standard categories:

| NFR | Question |
|---|---|
| Namespace collision | Are the names chosen unique enough that another tool on this machine couldn't have the same name? |
| Reversibility | Can a developer undo this without data loss? Is there a backup/migration path? |
| Blast radius | Does this affect all Claude Code sessions on this machine, or only the current project? |
| Discoverability | Will the developer know which entries came from youk vs their own setup? |

Output a compact classification:

```
[CLASSIFICATION]
Feature type:   [type]
Integration:    [integration points]
Scale context:  [scale]
Mandatory NFRs: [list — these CANNOT be deferred without explicit reasoning]
Conditional:    [list — check if applicable]
Optional:       [list — may skip with note]
```

> Rule: Any feature that touches an external API, LLM, or database with variable
> response cost has CACHING as mandatory, not conditional.

---

### Phase 2 — PROBE

For each mandatory NFR category, ask the targeted questions from
`references/nfr-categories.md`.

**Do not ask all questions at once.** Work through one category at a time. If the
answer is clear from context (e.g., "this is a read-only endpoint — no idempotency
needed"), state the inferred decision and move on without asking.

Only pause for user input on:
- Decisions that require product or business context Claude cannot infer
- Conflicting constraints where two valid options exist and the choice has real consequences

For each category, emit:
```
[PROBING: CATEGORY]
Questions / inferred answers → stated assumptions
```

---

### Phase 3 — DECIDE

Force explicit decisions. No decision may be left as TBD. Every category gets one of:

- `DECIDED: [the decision]` — concrete, implementable
- `DEFER: [reason] — revisit when [condition]` — explicit deferral with trigger
- `N/A: [reason]` — not applicable to this feature, with justification

**Caching decisions must include:**
- Key design (what makes a cache key unique)
- TTL value and reasoning
- Eviction policy (LRU / LFU / FIFO / none)
- Invalidation trigger (what causes a stale entry)
- Cost justification (why cache here, what's the hit rate expectation)

**Retry decisions must include:**
- Max retry count
- Backoff strategy (fixed / exponential / jitter)
- Idempotency guarantee (is it safe to retry?)
- Failure mode after exhaustion (raise / log-and-continue / circuit break)

**Auth decisions must include:**
- Who can call this? (authenticated user / service account / public / internal only)
- What permission check runs? (role / scope / ownership)
- Audit log: what gets recorded and where?

---

### Phase 4 — DOCUMENT

Emit the **NFR Decision Block** — a structured artifact carried into dev-loop as
mandatory context. Strict maximum: 25 lines.

```
[NFR DECISION BLOCK — {FEATURE NAME}]
Generated: {date}

CACHING:         {DECIDED: key=sha256(query), TTL=24h, LRU eviction, invalidate on schema change}
                 OR {DEFER: not needed — no repeated expensive computation}
                 OR {N/A: single-use endpoint, no benefit}

RETRY:           {DECIDED: max 3, exponential backoff 1s/2s/4s, idempotent=yes}
                 OR {DEFER: ...}

OBSERVABILITY:   {DECIDED: log query time + result count; alert if p99 > 5s}

AUTH:            {DECIDED: authenticated user required; no per-row authorization; no audit log needed}

RATE LIMITING:   {DECIDED: 60 req/min per user; 429 on breach}

IDEMPOTENCY:     {DECIDED: safe to retry — read-only operation}

CONSISTENCY:     {DECIDED: eventual OK — cache read is acceptable staleness}

DATA VOLUME:     {DECIDED: ≤10K rows per query; paginate if > 1000 rows in response}

OPEN QUESTIONS:  [any unresolved items that require stakeholder input — max 2]
```

---

### Phase 5 — CONNECT

Check whether any NFR decision triggers a new ADR (Architecture Decision Record) or
reveals a conflict with existing ADRs.

Emit:
```
[CONNECTIONS]
New ADR triggers:    [list — each is a discrete architectural decision that deserves a DECISIONS.md entry]
Conflicts found:     [list — any NFR decision that contradicts an existing ADR]
Dev-loop readiness:  [READY / BLOCKED: reason]
NFRGap: {category}  [one line per gap found — categories: caching, retry, auth, idempotency,
                     rate-limiting, observability, consistency, data-volume]
```

**NFRGap audit field:** For each mandatory NFR that was found to be MISSING or UNDECIDED
pre-build (not already addressed in an existing decision block), emit one `NFRGap: {category}`
line. These lines are parsed by health.py to compute `nfr_gaps_flagged` in prevented_cost_score.
Each pre-build gap flagged = a potential incident avoided. Pass `nfr_gaps=[list]` to
`youk-core.session_end()` when closing the session.

If BLOCKED, state what must be resolved before implementation can begin.

---

## Autonomy Depth Rubric

When the developer pre-empts nfr_check by answering NFR questions unprompted, record both
the fact (`developer_caught=["nfr_check"]`) and the depth of what they provided
(`autonomy_depth={"nfr_check": "<LEVEL>"}`) in `session_end()`.

Depth levels for nfr_check:

| Level | What the developer provided |
|-------|----------------------------|
| SURFACE | Mentioned one NFR category exists (e.g. "we'll need caching") |
| WORKING | Provided a concrete NFR decision — TTL, retry count, specific approach |
| DEEP | Full decision with consistency tradeoff: WHY this approach + what it doesn't solve |
| ELITE | Pre-explained edge cases before being asked: cold start, thundering herd, cascading failure, or cross-cutting tradeoffs across multiple NFR dimensions |

If the developer caught 3+ NFR categories at WORKING or above: pass `autonomy_depth={"nfr_check": "DEEP"}`.
If they also pre-explained failure modes or tradeoffs: pass `ELITE`.

---

## Quality Bars (Non-Negotiable)

These apply regardless of invocation mode:

- **No TBD.** Every mandatory NFR must be DECIDED or DEFER. TBD is not a valid state.
- **DEFER requires a trigger.** "We'll figure it out" is rejected. "Defer until we have 100+ users" is accepted.
- **Caching is mandatory for all external API calls and LLM calls.** Reclassifying these as optional requires explicit product approval.
- **The NFR Decision Block must be ≤25 lines.** Conciseness forces clear thinking.
- **CONNECT runs even on `quick` invocations.** NFR decisions can always create ADR triggers.
- **If a feature already has an NFR block, do not re-decide.** Identify gaps only.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Scope test**: Given "add a search endpoint", correctly classify caching and retry as mandatory, auth as conditional, rate limiting as conditional — and ask exactly the right questions without over-probing.
2. **Gap detection**: Given an existing feature with no retry policy on an LLM call, flag it as HIGH gap and produce a concrete retry decision.
3. **No-TBD test**: When pushed to defer everything ("we'll decide later"), it refuses and forces at least a DEFER-with-trigger on mandatory items.
4. **Handoff test**: The NFR Decision Block it produces can be pasted directly into a dev-loop context block and used without interpretation.
5. **Proportionality test**: On a 2-line hotfix, it runs `quick` mode and produces ≤5 decisions without ceremony.

---

## Reference Files

Read on demand — load only the file relevant to the active phase:

| File | When to read |
|------|-------------|
| `references/feature-type-matrix.md` | CLASSIFY phase — routing table for NFR categories |
| `references/nfr-categories.md` | PROBE phase — questions per NFR category |
| `references/nfr-decision-format.md` | DOCUMENT phase — exact format templates |
| `references/stacks/{framework}.md` | PROBE phase — stack-specific NFR questions and failure modes |

---

## Stack Coverage System

During CLASSIFY, detect the stack and framework from the feature description and project context.
Check whether a stack-specific overlay exists at `references/stacks/{framework}.md`.
Without it, the PROBE phase asks generic questions — missing the failure modes specific to the stack.

### Step 1 — Detect the stack
From session context or project files, identify:
- Language: Python / TypeScript / Go / etc.
- Framework: Django / FastAPI / Flask / Next.js / etc.

### Step 2 — Check coverage
Check `references/stacks/{framework}.md` first, then `references/stacks/{stack}.md` as fallback.

### Step 3 — If coverage missing, emit gap and offer to generate
At the end of CLASSIFY, emit:

```
[STACK GAP DETECTED]
Stack: {framework or stack}
Coverage: none

A stack overlay for {framework} would add:
- Concurrency + GIL / runtime-specific NFR questions
- Default timeouts and retry behavior for common libraries
- Memory and startup NFRs specific to this framework

Generate now? [yes / skip for this session]
```

If confirmed: call `youk-code.generate_stack_overlay(skill_name="nfr-check", stack=..., framework=...)`.
Generated overlay is saved to `references/stacks/{framework}.md` and auto-loaded in future sessions.

### Step 4 — Load in PROBE
Once `references/stacks/{framework}.md` exists, it is appended to base SKILL.md
by `load_skill_with_context()` automatically. It deepens the PROBE phase with
stack-specific NFR questions that the generic categories miss.

---

## Example Flows

**Full check before a new LLM-backed feature:**
> "Add a citation lookup feature that calls an external API to enrich query results."

CLASSIFY → external API + LLM = caching mandatory, retry mandatory, rate limit conditional →
PROBE (caching: key design? TTL?) → PROBE (retry: idempotent? max retries?) →
DECIDE → DOCUMENT (NFR Block) → CONNECT (new ADR: external API integration pattern)

**Quick check for a small UI change:**
> "Add a loading spinner to the query button. quick."

CLASSIFY → UI component, no integration = top 3 NFRs only →
PROBE (observability: is timing logged?) → DECIDE → DOCUMENT (3-line NFR block) → CONNECT (no triggers)

**Review existing feature:**
> "Review the cache module for missing NFR coverage. review existing."

Read existing cache.py + canopy-context.md → CLASSIFY → compare against mandatory NFRs →
PROBE only on gaps → DOCUMENT gaps + recommended decisions
