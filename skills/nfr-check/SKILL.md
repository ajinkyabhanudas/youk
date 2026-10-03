---
name: nfr-check
rationale_why: "NFR decisions made after code exists get embedded in the code and cost 10x to change. This gate makes them cheap — four questions now versus a production incident later."
rationale_why_terse: "[nfr-check] — decide caching, retry, and observability before you build, not after."
description: >
  Pre-build non-functional requirements gate. Fires before any dev-loop invocation on
  non-trivial features. Forces explicit decisions on caching, retry, observability, auth,
  rate limits, idempotency, consistency, and data volume — before a single line of code
  is written. Prevents NFR decisions from being deferred until they become production
  incidents. Triggers on: "add feature", "build X", "implement Y", any new module,
  endpoint, background job, or integration point. Can also be invoked standalone for
  NFR-only review of an existing design. Do not trigger for: pure refactors with no
  external I/O change, doc-only changes, test additions to existing endpoints, or
  renaming/moving code that introduces no new behavior.
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

─ If task mentions benchmark / eval / measurement / re-run / scoring / comparison / "run again" / "compare models" / "test results" / repeated LLM calls ─
7. Measurement integrity?  {is cache/state cleared before each run? are runs independent? is a baseline (control) included? without clearing, repeated runs measure cache behavior not model behavior}
```

These questions cover 80% of production incidents. No ceremony beyond this for S/M.
Proceed to dev-loop once all applicable questions are answered.
Q6 and Q7 are conditional — only ask when the task surface matches. Skip silently otherwise.

---

─ If task mentions benchmark / eval / measurement / re-run / scoring / comparison / "run again" / "compare models" / "test results" / repeated LLM calls ─
7. Measurement integrity?  {is cache/state cleared before each run? are runs independent? is a baseline (control) included? without clearing, repeated runs measure cache behavior not model behavior}
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

**Functional edge cases (CIR-150 item 1 / CIR-151):** before moving to Phase 2, also
answer the questions in the `functional_edge_case_questions` field (M/L/XL calls only
— nfr_check_quick/nfr_check_full populate it from
`references/edge-case-questions.md` via `stress-test`'s Agent B question bank, the
same list Agent B uses to attack a finished plan reactively). Answering them here,
against the bare task text, is the proactive counterpart — empty/null inputs,
boundary values, concurrent/ordering issues, partial failure — derived before a plan
exists rather than attacked after one does. Output:

```
[FUNCTIONAL EDGE CASES]
{question} → {inferred answer from task text, or "OPEN — needs plan-time decision"}
```

**Domain edge-case disposition (CIR-170 Phase B):** for each non-empty entry in
`domain_edge_case_candidates`, after judging it against the task per the
`domain_edge_case_instruction` field above, decide and log its real disposition —
`accepted` (the plan changed because of it), `dismissed` (explicitly judged
irrelevant to this task), or `ignored` (surfaced, no explicit call made either
way — log this too, never silently omit it). Call
`youk-core.log_domain_edge_case_disposition(project, task, bounded_context,
source_file, source_id, disposition)` once per candidate, using that candidate's
own `bounded_context` / `source_file` / `source_id` fields unchanged and the
current project slug for `project`. This exists in youk-core, not youk-code, for
the same read-only-mount reason as `log_ab_exposure` — nfr-check itself cannot
persist the write. This is the measurement layer Phase C's reversal check and
Phase D's promotion path both depend on (see docs/pattern-learning-architecture-
design.md's "DispositionEvent" schema section): a candidate that is reviewed but
never logged produces no evidence either way, confirmed or not.

**Domain Brief fallback (CIR-168):** if `domain_edge_case_candidates` is empty, that is
usually a true negative (CIR-163's own instruction above) — nothing in a populated Domain
Brief matched this task's vocabulary. But it can also mean the Domain Brief has nothing to
match against at all, which is a different problem needing a different response. Tell the
two apart by reading `state/domain-brief.json` directly (or noting its absence) before
moving on:

- **True negative, do nothing:** the file exists and at least one entry in its `sources`
  list shows `"format_recognized": true` (equivalently, `bounded_contexts` is non-empty) —
  some real decision record parsed, it just didn't match this task. Proceed as normal.
- **Fallback case — this is where the gap actually is:** the file is missing entirely, OR
  every entry in `sources` shows `"format_recognized": false` or `null` — no known
  decision-doc dialect produced a single real bounded context anywhere in this project. The
  extractor genuinely has nothing to work with; this is not "nothing matched," it's "there
  was nothing to try matching against." In that case:

  1. Examine the actual codebase: top-level directory structure (and one level into any
     `src`/`app`/`packages`/`lib` dir), key module or file names, what the README says the
     project does in its own words, and any config file naming real subsystems (package.json
     workspaces, pyproject.toml packages, docker-compose service names).
  2. State 2-4 inferred bounded contexts, each a short name plus one sentence tying it to
     something you actually read — a directory, a module, a README line, a service name.
     A generic guess with nothing cited ("User management," unsupported) does not count; a
     cited one does ("Auth — `src/auth/` owns login/session/token issuance, confirmed by
     `routes/auth.py`").
  3. Tag every one of these `source_file: inferred-from-codebase` (never a real file path)
     and `source_id:` naming what was examined (e.g. `src/orders/, README.md:1`). This must
     never be presented, logged, or cited as if it were a real decision-record citation — it
     is a lower-confidence, session-local hypothesis for this task's review, not a fact to
     add back into `state/domain-brief.json` itself (that file stays exactly what
     `build_domain_brief` actually extracted; nothing inferred here is written back to it).

  **Worked example — a fresh repo with no `DECISIONS.md` at all:** a new API service with
  `src/orders/`, `src/billing/`, `src/notifications/`, a `README.md` opening "handles order
  lifecycle and payment capture for the storefront," and a `docker-compose.yml` naming
  services `api`, `postgres`, `redis`. `sources` shows both entries `"present": false`,
  `"format_recognized": null` — there's nothing to parse, full stop. Codebase examination
  infers: **Orders** — `src/orders/` plus the README's "order lifecycle" phrase
  (`source_file: inferred-from-codebase`, `source_id: src/orders/, README.md:1`); **Billing**
  — `src/billing/` plus "payment capture" in the same README line (`source_id: src/billing/,
  README.md:1`); **Notifications** — `src/notifications/` alone, flagged as the weakest of
  the three since nothing else in the repo corroborates it. Three contexts, each tied to
  something real that was actually read — not four padded in to hit a round number, and
  none of them treated as equivalent in confidence to a real `DECIDED`/`WHY` citation.

**Domain scope (problem-space-modeling Phase 5 / CIR-165):** before moving to Phase 2,
also answer fresh — every M/L/XL call, never cached or reused from a prior task's answer
— "which 2-4 knowledge domains, beyond generic software engineering, are actually
relevant to THIS task's assumptions, and why?" A billing feature needs financial-
regulation + security; a chat UI needs UX + cognitive-science; a data pipeline needs
statistics. This is a judgment call made by reading the actual task text, not a lookup —
do not consult or produce a fixed domain table (`if "payment" in task: return
["finance"]` is exactly the mistake this step exists to prevent). Output:

```
[DOMAIN SCOPE]
{domain} — {one-sentence reason this domain's assumptions matter to this specific task}
(2-4 domains)
```

Then call `youk-core.log_domain_scope_event(task, domains)` — `domains` is the
real list of `{domain, reason}` pairs just named above, never a cached/reused
prior answer (same discipline this step already requires). This is the
single heaviest LLM judgment call in the whole system; logging it durably
(`state/domain-scope-log.jsonl`) is what lets drift or bias in it be checked
later instead of guessed at. Do this before moving on — the decision must not
happen in-session and vanish.

Then call `youk-core.build_domain_research_invocation(domains, task)` and run the
returned `invocation` (youk-research's existing WebSearch → extract → propose loop,
`/research [topic]` scoped to these domains — reuse it, do not build a second search
loop). Carry whatever it finds forward as external evidence for `challenge`'s Lens 3
(hidden assumptions) on this task.

---

### Phase 2 — PROBE

Load `references/skill-scope-matrix.yaml` and cross-reference the feature type against
mandatory NFR categories for this task. Confirm mandatory domains from the matrix are
covered before proceeding to DECIDE.

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

**Pre-output check (silent):** Before emitting the NFR Decision Block, verify: (1) every
mandatory category has DECIDED or DEFER-with-trigger — no TBD allowed; (2) caching is
DECIDED for all external API / LLM calls; (3) the block is ≤25 lines. If any check fails,
revise the decisions before surfacing.

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

**Emit the examination surface block immediately after CONNECTIONS:**

```
[EXAMINATION SURFACE — nfr-check]
Mode:         {quick | full | validate}
Feature type: {new_endpoint | schema_change | llm_call | ui_component | background_job | other}
Examined:     [comma-separated NFR categories actually probed]
              Valid categories: caching, retry, auth, idempotency, rate_limiting,
              observability, consistency, data_volume, rendering_env, measurement_integrity
Not examined: [category — reason]
              e.g. "rate_limiting — internal-only endpoint, no public surface"
              e.g. "caching — N/A: no repeated expensive computation in this path"
              e.g. "rendering_env — no UI surface"
```

Rules:
- `caching` is mandatory for any LLM call or external API. If not examined: reason must be explicit and must not be "N/A" unless the feature has zero external calls.
- In `validate` mode: only gaps appear in Examined (categories the developer did NOT pre-empt). Pre-empted categories go in Not examined with reason "developer pre-empted at {DEPTH}".
- This block is the attribution surface for the skill self-improvement system. SCOPE_MISS on a mandatory NFR category (e.g., caching on an LLM path) triggers a deduction in nfr-check's health score.

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

- **Emit the coverage view.** Render the NFR dimensions as a coverage view (`mode_coverage_view.view_from_outcomes("nfr-check", target, outcomes)`) so completeness is glanceable — a dimension the pass never reached shows as a MISSING gap. Generated from the pass, never hand-authored. UNVERIFIED unless an independent adversary ran over the dimension set; never imply the pass self-verified its own completeness.

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
