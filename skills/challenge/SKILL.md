---
name: challenge
description: >
  Direction gate skill. Fires before work starts on any M+ task to challenge the
  interpretation, not the plan. Asks: is this the right problem? Is there a simpler
  framing? What are we assuming about what the user wants? Runs a constraint-aware
  pre-mortem loop — iterates challenge rounds until no new objections survive.
  Exit condition: a challenge round produces nothing new. Only then does work begin.
  Triggers on: any M+ task at route_task time, explicit "challenge this", "are we
  solving the right problem?", "before we go further". Does NOT replace stress-test
  (which red-teams implementation after direction is set). challenge attacks direction itself.
  Do NOT use for: XS/S tasks, tasks where direction is already explicitly confirmed
  by the user this session, retest of an already-challenged direction.
---

# challenge — Direction Gate

Stop before going deep. The most expensive mistake is solving the right problem wrong.
The second most expensive is solving the wrong problem well.

This skill fires before work starts, not after a plan exists. It challenges the
interpretation — the framing, the assumed goal, the implicit constraints — and iterates
until the direction survives a full challenge round with nothing new to object to.

One loop. Exit on silence.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full challenge loop — all four lenses, iterate until stable |
| `quick` | Single pass, top objection per lens only, no iteration |
| `framing only` | Lens 1 (problem framing) only |
| `assumptions only` | Lens 3 (hidden assumptions) only — fastest path |
| `retest: [revised direction]` | Given a revised direction, run one more challenge round to confirm it survives |
| `silent` | Run challenge internally, only surface if a blocking objection is found |
| `plan: [task list]` | Plan coherence check — Lens 2+3 across the full task list as a unit, then Lens 3 quick on tasks that need sharpening. Fires before any task is implemented. |

---

## Context Capture (Always First)

Extract before any phase:

```
TASK:              [the user's request, verbatim or paraphrased]
INTERPRETED_AS:    [what youk is about to do — the implicit direction being challenged]
FIXED_CONSTRAINTS: [what cannot change — stated explicitly by user this session]
PRIOR_WORK:        [what has already been done / decided this session — walls, not surfaces]
STAKES:            [low / medium / high — how bad is it to go the wrong direction here?]
SESSION_DEPTH:     [how many exchanges deep are we? >5 means more context is load-bearing]
```

Infer FIXED_CONSTRAINTS from conversation — look for "we're using X", "we can't change Y",
"given that Z". These are NOT attack surfaces. Do not challenge them.

If STAKES is low: use `quick` mode automatically, do not run full loop.
If SESSION_DEPTH > 10: flag that reversing direction now has high cost — weight objections accordingly.

---

## Multi-Level Convergence (runs before any lens, when goal contains a quality word)

When the task or goal contains a quality word ("elite", "production-grade", "better", "bullet-proof",
"right", "clean", "solid", "complete") — run the seven-angle convergence check BEFORE the four lenses.

Seven fixed angles, bottom-up, adversarial ordering (most likely to fail first):

1. **STRUCTURAL** — what weak links or missing fundamentals exist regardless of feature quality?
   (no CHANGELOG, state bug, missing security posture, unpinned dependencies)
2. **OPERATIONAL** — can a stranger use this without hand-holding on first run?
3. **EXPERIENTIAL** — would a principal engineer deploying to 50 engineers approve after 20 sessions?
4. **ADVERSARIAL** — what would a competitor who has thought longer reject? what angle is unchallenged?
5. **TEMPORAL** — does this hold across model generations? what breaks when the model is replaced?
6. **OUTCOME** — what predictions does this generate that reality can verify, without seeing the codebase?
7. **SEMANTIC** — given angles 1-6, does the quality label fit what actually exists?

Rules:
- Evaluate structural FIRST — it fails most often and is most often skipped
- Contradiction between any two angles = BLOCKING objection, do not proceed
- Semantic label (angle 7) only applied after angles 1-6 converge
- A label that fits angle 7 but contradicts angle 1 is false unanimity — BLOCKING
- If you cannot name what structural failure looks like: that IS the structural failure

Emit before the four lenses:
```
[CONVERGENCE CHECK]
Structural:    {finding or CLEAR}
Operational:   {finding or CLEAR}
Experiential:  {finding or CLEAR}
Adversarial:   {finding or CLEAR}
Temporal:      {finding or CLEAR}
Outcome:       {finding or CLEAR}
Semantic:      {label fits | label does not fit — reason}
Verdict:       CONVERGED | CONTRADICTION on {angles} — BLOCKING
```

If CONTRADICTION: do not proceed to the four lenses. Surface the contradiction as a BLOCKING objection.
If CONVERGED: proceed to the four lenses with the converged definition as the fixed frame.

---

## The Four Lenses

Each lens is independent. They do not see each other's output within a round.

**Lens 1 — Problem Framing**
Is this the right problem to solve right now?
- Is there a simpler version of this problem that achieves the same outcome?
- Is the stated problem a symptom of a deeper problem?
- Would solving this create a new problem that's harder than the current one?
- Is there evidence the user actually wants what they asked for, or is the ask a proxy?

**Lens 2 — Scope Creep**
Is the interpreted direction bigger than the task requires?
- What is the minimum version that proves the direction is right?
- Are there sub-problems being pulled in that don't need to be solved yet?
- Is the direction building infrastructure for a future that may not arrive?
- What would a 10x simpler path look like?

**Lens 3 — Hidden Assumptions**
What is the direction assuming that hasn't been stated?
- What does this direction assume about the user's goal?
- What does it assume about the current state of the system?
- What does it assume about what's already been decided?
- Which assumption, if wrong, would make the entire direction wrong?
- **Intent assumption:** What does this direction assume about what the user wants to *experience*, vs. what they want *delivered*? If the user's goal was stated in quality words ("elite", "right", "better", "clean", "proper") or mindset language ("discover the pattern", "surface the mindset"), name the specific experience I'm assuming that means. If I cannot name it, that is a BLOCKING objection — the translation is opaque and must be collapsed before proceeding.

**Lens 4 — Opportunity Cost**
What is NOT being done if we go this direction?
- What would be lost by not taking an alternative path?
- Is this the highest-leverage use of the next N exchanges?
- Is there a direction that addresses this AND a prior open question simultaneously?

---

## Plan Coherence Phase (fires only in `plan:` mode)

`[PHASE: PLAN COHERENCE]`

Runs once across the full task list before any per-task challenge. Single agent, Lens 2 + Lens 3 applied to the plan as a unit. File context from conversation (recently read files, mentioned modules) is used opportunistically — no explicit loading required.

**Input:** task list (N items), FIXED_CONSTRAINTS, file context in conversation.

**Three questions, in order:**

1. **Redundancy** (Lens 2): Which tasks solve the same problem as another task in this list, or as something already in the codebase? Name the overlap specifically.
2. **Already solved** (Lens 3): Which tasks assume a problem exists that the codebase already addresses? Name the file/function that already solves it if visible in context.
3. **Broken ordering** (Lens 3): Which tasks assume a state produced by another task that comes after it in the list?

**Output per task:**

```
Task N: {task description}
Verdict: PASSED | NEEDS SHARPENING | WRONG
Reason: {one sentence — only required for WRONG and NEEDS SHARPENING}
```

**After all tasks assessed:**
- PASSED tasks: proceed to implementation, no further challenge
- NEEDS SHARPENING tasks: run Lens 3 `assumptions only` quick on that task alone, then re-emit verdict
- WRONG tasks: surface with default-yes confirmation before dropping:
  `"Task N flagged WRONG: {reason}. Drop it? (default yes — say no to keep)"`

**Rules:**
- PASSED tasks are silent — do not list them unless user asks
- Only surface WRONG and NEEDS SHARPENING
- Do not challenge FIXED_CONSTRAINTS
- If zero tasks come back WRONG or NEEDS SHARPENING: emit `[PLAN COHERENCE PASSED]` and proceed immediately

---

## The Three Phases

Each phase begins with the token `[PHASE: NAME]`

---

### Phase 1 — ORIENT

`[PHASE: ORIENT]`

State what is being challenged:

1. Write INTERPRETED_AS in one sentence — exactly what is about to happen if challenge passes
2. List FIXED_CONSTRAINTS — these will not be attacked
3. State STAKES and SESSION_DEPTH
4. Identify which lenses are most relevant for this task type:
   - Feature/build tasks: all four lenses
   - Debugging tasks: Lens 3 (assumptions) + Lens 1 (framing) primary
   - Design/architecture tasks: Lens 1 + Lens 4 (opportunity cost) primary
   - Question/research tasks: Lens 1 (framing) only — quick mode sufficient

> Compact summary: "Challenging [direction] at [stakes] stakes. Fixed: [constraints]. Running [N] lenses."

---

### Phase 2 — CHALLENGE LOOP

`[PHASE: CHALLENGE LOOP]`

Run each active lens independently. For each lens, produce at most 2 objections.
An objection is only valid if:
- It is not blocked by a FIXED_CONSTRAINT
- It is specific — names what exactly would go wrong and when
- It has not already been raised and resolved this session

**Objection format:**
```
[LENS N: NAME]
Objection {n}:
  What: {the specific thing being challenged}
  Why it matters: {what goes wrong if this objection is correct}
  Weight: BLOCKING | HIGH | LOW
  Resolved by: {what would make this objection go away — a fact, a decision, a clarification}
```

**BLOCKING** = if this is correct, the direction is wrong and work must not start.
**HIGH** = work can start but this should be addressed in the first exchange.
**LOW** = worth noting, does not block.

After all lenses run:
- If zero objections: direction SURVIVES — emit `[CHALLENGE PASSED]` and proceed
- If only LOW objections: direction SURVIVES WITH NOTES — emit findings inline, proceed
- If any HIGH: direction NEEDS SHARPENING — emit findings, propose revised direction, go to Phase 3
- If any BLOCKING: direction WRONG — stop, surface the blocking objection, ask user to redirect

**Direction reversal audit field:** If the initial direction is rejected (WRONG verdict) or
substantially revised via ITERATE (the revised direction differs from the original), emit:
`direction_reversal: yes` — this field is logged in session_end to feed prevented_cost_score.
A direction reversal = wrong-path sessions avoided. Pass `direction_reversal=True` to
`youk-core.session_end()` when closing the session.

> Compact summary: "{N} objections found ({n} BLOCKING, {n} HIGH, {n} LOW). Verdict: [PASSED / NEEDS SHARPENING / WRONG]"

---

### Phase 3 — ITERATE (conditional)

`[PHASE: ITERATE]`

Only runs when verdict is NEEDS SHARPENING.

1. Propose a revised direction that addresses the HIGH objections
2. State what changes from the original direction and what stays the same
3. Re-run lenses against the revised direction (one more round only)
4. If the revised direction survives: emit `[CHALLENGE PASSED — revised direction]`
5. If new BLOCKING/HIGH objections emerge: surface them and ask user — do not iterate a third time automatically

**Exit rule:** The loop exits when two conditions are both true:
1. The last round produced zero new objections from the lenses that ran.
2. No angle exists that hasn't been run yet.

Before surfacing any verdict, self-check both explicitly:
- "Did the last round produce zero new objections?" — if not, iterate.
- "Is there any lens, angle, or dimension I haven't challenged yet?" — if yes, run it now.

Only when both are true is the loop dry. Two rounds is the emergency brake for
unresolvable/circular objections only — not the exit condition.

> Compact summary: "Revised direction: [one sentence]. New challenge round result: [verdict]."

---

## Quality Bars (Non-Negotiable)

- **Objections must be specific.** "This might be the wrong approach" is not an objection. "We're about to build a cross-project pattern scanner when the user's actual complaint was about a single contract not promoting — the scope is 10x larger than the problem" is an objection.
- **Fixed constraints are never attacked.** If the user said "we're using SQLite", Lens 3 does not produce "assumes SQLite is the right database." That constraint is a wall.
- **BLOCKING means stop.** If a BLOCKING objection is found, work does not start. The objection is surfaced, the user redirects. Not negotiable.
- **Global optimum exit condition.** Before surfacing any verdict, two checks must both pass: (1) did the last round produce zero new objections from every lens that ran? (2) is there any lens, angle, or dimension not yet challenged? If either fails — keep going internally. "Zero objections from lenses I ran" is not the exit condition. "Zero objections from all angles, none skipped" is.
- **LOW objections do not block.** They are noted and carried forward as context. They do not trigger Phase 3.
- **silent mode only speaks on BLOCKING.** In silent mode, LOW and HIGH findings are held internally and influence the answer without surfacing friction to the user. Only BLOCKING objections break silence.

### Hiring Validation

This skill passes the hiring committee if it can:

1. **Constraint respect:** Given "we're using Redis, challenge whether we should add a task queue" — Lens 3 does NOT produce "assumes Redis is the right store." Redis is a fixed constraint. The challenge attacks the task queue direction, not the store.
2. **BLOCKING stop:** Given a task where the stated goal contradicts something already decided this session, the skill emits `[DIRECTION WRONG]` and stops — it does not proceed to implementation with a footnote.
3. **Scope lens fires:** Given "build a two-level reasoning system with reconciliation gate" — Lens 2 identifies "minimum version is a single forced-failure pass, not a dual-layer system" before work starts. This is the rabbit hole prevention case.
4. **Silent mode discipline:** In `silent` mode on a task with only LOW objections, the skill produces no output visible to the user — it influences the answer silently. It does not surface "I challenged this and found nothing" — that is noise.
5. **Run-until-dry exit:** The skill keeps iterating internally until a round produces zero new objections. Only then does it surface a verdict. If objections persist after two rounds, it surfaces the unresolved tension to the user and stops — it does not propose further revisions autonomously.

---

## Reference Files

| File | When to read |
|------|-------------|
| `stress-test/references/assumption-taxonomy.md` | Phase 2, Lens 3 — categories of hidden assumptions |

---

## Example Flows

**The rabbit hole case — direction is 10x larger than needed:**
> User: "build a two-level reasoning loop with first-principles layer, context layer, and reconciliation gate"

ORIENT: direction = build three-component system. Stakes: high (architecture decision). Fixed: must run in-session, no API calls.
CHALLENGE LOOP:
- Lens 1: Is this the right problem? The actual failure is "going down rabbit holes" — is a three-component system the minimum fix?
- Lens 2: Scope — minimum version is a single pre-mortem pass before answering. Three components solve a harder version of the problem than described.
- Lens 3: Assumes LLM can run two independent layers — stress-test just showed this is architecturally impossible in one session.
- Lens 4: Building this costs 3+ sessions. A single challenge skill (this one) costs 1 session and solves 80% of the problem.
VERDICT: NEEDS SHARPENING — Lens 2 HIGH (scope), Lens 3 BLOCKING (independence assumption false)
ITERATE: Revised direction = build `challenge` skill (single pre-mortem pass, constraint-aware). Challenge round 2 → SURVIVES.
`[CHALLENGE PASSED — revised direction: challenge skill only]`

**Quick check on a debugging task:**
> User: "the test is failing, let's add a mock for the database call"

ORIENT: direction = add mock. Stakes: low. SESSION_DEPTH: 2.
Auto-selects `quick` mode (low stakes).
Lens 3 only: "assumes the test is failing because of the database call — have we confirmed this?"
One objection, weight HIGH: "Resolved by: reproduce failure without mock first."
VERDICT: NEEDS SHARPENING — surface: "before adding the mock, can you confirm the failure is in the DB call? If yes, proceed."

**Direction already confirmed — skip:**
> User said "yes, let's build the challenge skill" two exchanges ago.

ORIENT: PRIOR_WORK includes explicit user confirmation of direction.
All lenses: no objections — user already resolved the framing.
`[CHALLENGE PASSED]` — silent, proceed immediately.

**Silent mode on a well-framed task:**
> User: "add the `theme` field to `_detect_cross_project_patterns()` return value"

ORIENT: Stakes low. Specific, bounded task. No ambiguity.
`silent` mode auto-selected.
All lenses: zero objections.
No output. Proceed to implementation.

**Plan coherence check — 7-task plan, 4 WRONG:**
> Planning phase produces: [1. add retry logic, 2. add caching layer, 3. add rate limiting, 4. refactor query loop, 5. add connection pooling, 6. add timeout handling, 7. add circuit breaker]
> File context in conversation: `query.py` already has retry decorator, `db.py` has connection pool.

`challenge plan: [task list]`

PLAN COHERENCE — Lens 2+3 across full list:
- Task 1 (retry logic): WRONG — `query.py` has `@retry` decorator already. Redundant.
- Task 2 (caching): PASSED
- Task 3 (rate limiting): NEEDS SHARPENING — assumes rate limiting belongs in the query layer; likely belongs at the API boundary
- Task 4 (refactor query loop): PASSED
- Task 5 (connection pooling): WRONG — `db.py` has `ConnectionPool` class already. Redundant.
- Task 6 (timeout handling): PASSED
- Task 7 (circuit breaker): NEEDS SHARPENING — assumes circuit breaker is needed; no evidence of downstream instability in context

Surface:
```
Task 1 flagged WRONG: retry logic already exists in query.py (@retry decorator). Drop it? (default yes)
Task 5 flagged WRONG: connection pool already exists in db.py (ConnectionPool). Drop it? (default yes)
Task 3 needs sharpening: rate limiting assumption → running Lens 3 quick...
  Assumption: rate limiting belongs in query layer. Risk: already handled at API gateway. Confirm placement before building.
Task 7 needs sharpening: circuit breaker assumption → running Lens 3 quick...
  Assumption: downstream instability exists. No evidence in context. Add only if instability is confirmed.
```

`[PLAN COHERENCE — 2 WRONG dropped, 2 NEEDS SHARPENING flagged, 3 PASSED proceeding]`
