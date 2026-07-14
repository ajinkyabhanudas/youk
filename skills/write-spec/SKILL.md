---
name: write-spec
description: >
  Produces a PRD or feature spec that a senior director would sign off on. Precise
  problem definition, user outcomes, scoped requirements, success metrics, acceptance
  criteria, and a one-paragraph executive brief. The standard is: another engineer or
  PM could pick this up and build or review without further clarification. Triggers on:
  "write a spec", "write a PRD", "define this feature", "what are we building exactly",
  any new project before implementation, and handover preparation. Distinct from
  /pm-review (which decides whether to build) — /write-spec defines what to build
  once the decision is made.
---

# write-spec — Feature and Product Specification

Produces a spec that a senior director would call hire-worthy. The standard is not
length or completeness for its own sake — it's precision and the absence of ambiguity.
A good spec answers every question an engineer, designer, or reviewer would have before
they ask it.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full spec: all phases |
| `quick` | Problem + scope + acceptance criteria only — for small features |
| `update: [change]` | Revise an existing spec given a scope change |
| `review: [spec]` | Audit an existing spec for missing sections or ambiguities |
| `handover` | Full spec formatted for handover to a non-technical stakeholder |

---

## Context Capture (Always First)

```
FEATURE:      [what's being specified]
OUTCOME OF /pm-review: [the decision brief — or "not run yet"]
USERS:        [primary user — specific person/role]
EXISTING:     [any prior decisions, ADRs, NFR blocks relevant to this feature]
AUDIENCE:     [technical team | non-technical stakeholder | mixed]
```

If `/pm-review` was not run, start with the PROBLEM phase before spec writing.
If it was run, import the problem definition and user impact from its output.

---

## The Eight Phases

Each phase begins with: `[PHASE: NAME]`

---

### Phase 1 — PROBLEM

One sentence. Not a paragraph. The sentence must be specific enough that two people
independently reading it would scope the same solution.

```
[PROBLEM]
{User} cannot {do specific thing} because {specific constraint}.
This matters because {consequence for the user or business}.
```

If this can't be written in one sentence, the problem is not scoped. Stop and
clarify before proceeding.

---

### Phase 2 — USERS

Who. Not "users" — a specific person or clearly-defined role.

```
[USERS]
Primary:   {name / role} — {what they do, how frequently, what they need}
Secondary: {name / role} — {how they're affected} (if any)
Out of scope: {who this is explicitly NOT for — prevents scope creep}
```

---

### Phase 3 — SCOPE

What's in. What's out. Ambiguities resolved here, not during implementation.

```
[SCOPE]
In:
  - {specific capability 1}
  - {specific capability 2}

Out (explicitly):
  - {thing that could be assumed in scope but isn't}
  - {adjacent feature deferred to later}

Constraints:
  - {tech, time, dependency constraints}
```

Each "out" item must have a reason. "Deferred" and "not applicable" are both valid.

---

### Phase 4 — REQUIREMENTS

Functional requirements only. Non-functional requirements come from the NFR Decision
Block (reference it, don't repeat it).

Write as: "The system must [verb] [object] [condition]."
Not as: "The system should support X" — "should" is ambiguous. Use "must" or "does not."

```
[REQUIREMENTS]
F1: The system must {verb} {object} when {condition}.
F2: The system must {verb} {object} within {constraint}.
F3: The system does not {verb} {object} — this is out of scope.
...

NFR reference: see NFR Decision Block for {feature} — {date}
```

Maximum 10 functional requirements. If you have more, the spec is too large.
Break into sub-features.

---

### Phase 5 — SUCCESS METRICS

How will we know this feature worked? Quantifiable where possible.

```
[SUCCESS METRICS]
Primary metric:   {what changes, how measured, target value}
Secondary metric: {what else improves as a result}
Counter-metric:   {what should NOT get worse — regression guard}

Measurement method: {how these will be tracked — manual review / log analysis / user feedback}
Review cadence:     {when we check — after N uses / after N weeks}
```

If you cannot define a primary metric, state why and what proxy you'll use.
"Users are happy" is not a metric. "Jajean's average query time drops from 12s to < 3s
for repeated questions" is a metric.

---

### Phase 6 — ACCEPTANCE CRITERIA

The bar that must be met before this feature is considered done. Written so a reviewer
who didn't build it can verify it.

```
[ACCEPTANCE CRITERIA]
AC1: Given {setup}, when {action}, then {expected outcome}.
AC2: Given {setup}, when {action}, then {expected outcome}.
...
AC-EDGE-1: Given {edge case setup}, when {action}, then {expected outcome}.

Definition of done:
  - All ACs pass
  - All tests green
  - Living documents updated
  - Founder demo complete (if user-facing)
```

Write at least one edge case AC. The happy path is not enough.

---

### Phase 7 — OPEN QUESTIONS

Decisions still needed before or during implementation. Each question has a default
answer so work can proceed — the default is what happens if the question is not
answered in time.

```
[OPEN QUESTIONS]
Q1: {question}
    Default if unanswered: {what we'll do}
    Owner: {who resolves this}
    Needed by: {when}

Q2: ...
```

Maximum 3 open questions. More than 3 means the spec is not ready.

---

### Phase 7.5 — SELF-CHECK

Mandatory before EXEC BRIEF. One question — a specific named answer is required.

**Q — Confusion check:**
"What is the one thing this spec does NOT say that will cause the most confusion during
implementation? Name it specifically — not 'unclear requirements' but the exact statement
an engineer will ask about. Then decide: does it belong in the spec, or is it intentionally
deferred with a named owner?"

Emit one of:
- `[DEPTH NOTE: {gap named} → {added to spec / deferred to Q{N} with owner}]`
- `[SHALLOW: {what was not scoped — why the spec is not implementation-ready yet}]`

If the gap belongs in the spec: add it before emitting EXEC BRIEF.
If deferred: add to OPEN QUESTIONS with a default and owner.

---

### Phase 8 — EXEC BRIEF

One paragraph. Readable by a non-technical stakeholder in 30 seconds.

```
[EXEC BRIEF]
{What the feature does, in plain English — no jargon}.
{Who benefits and how their day changes}.
{The one constraint or trade-off worth knowing}.
{What we're not doing and why}.
```

No more than 5 sentences. This is the thing you'd read to Jajean before building.
If she wouldn't understand every word, revise.

---

## Quality Bars

- **No ambiguous verbs.** "Support", "handle", "allow" — each has a specific meaning. Use them precisely.
- **Every "out of scope" item has a reason.** Unexplained exclusions become scope creep.
- **Acceptance criteria are verifiable.** "Works well" is not verifiable. "Returns result in < 3s for cached queries" is verifiable.
- **Success metrics are quantifiable.** A proxy is acceptable; "it feels better" is not.
- **The exec brief passes the domain-expert reader test.** A non-technical domain expert should understand every sentence without a follow-up question.
- **Maximum 10 functional requirements.** More means split the spec.

  **How to split:** split by user journey, not by implementation module.
  - Wrong: "frontend spec" + "backend spec" — arbitrary tech boundary, invisible to users
  - Right: "search journey spec" + "results journey spec" — user-facing boundary, testable independently

  Structure for split specs:
  - **Parent spec:** goal, users, constraints, out-of-scope only — no requirements, no ACs
  - **Sub-specs:** full spec per journey, each with its own acceptance criteria
  - **Parent AC:** all sub-spec ACs pass + integration test between journeys passes
  - Link sub-specs from parent: "See: search-journey.md, results-journey.md"

---

## Hiring Validation

This is the "I'd hire you" test. The spec passes if:

1. **Ambiguity test**: An engineer who has never spoken to the requester can implement from this spec without asking a single clarifying question — because every ambiguity is resolved in scope or open questions.
2. **Scope creep test**: When a reviewer suggests adding an adjacent feature, the "out of scope" section already lists it with a reason, ending the conversation.
3. **Done test**: Two people independently reviewing the acceptance criteria would reach the same conclusion about whether the feature is done.
4. **Brevity test**: The spec is complete without being long. A senior reviewer reads it in under 5 minutes.
5. **Metric test**: The success metric is specific enough that 6 months later, without talking to anyone, you can determine whether the feature succeeded.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/spec-quality-bar.md` | REVIEW phase and ACCEPTANCE CRITERIA — the "I'd hire you" standard |

---

## Example Flows

**Full spec for canopy cache feature:**
> "/write-spec: add query result caching"

PROBLEM (repeated queries pay full LLM cost every time) →
USERS (Jajean: repeats donor-report queries weekly) →
SCOPE (in: exact-match cache with TTL; out: semantic caching, cross-user cache) →
REQUIREMENTS (F1: must return cached result < 200ms when hit; F2: must expire after 24h by default) →
SUCCESS METRICS (primary: cache hit rate > 30% within 2 weeks; counter: no incorrect cached results) →
ACCEPTANCE CRITERIA (AC1: Given repeated identical query, when submitted, then result returned in < 200ms; AC-EDGE-1: Given TTL=0, when submitted, then cache bypassed) →
OPEN QUESTIONS (Q1: should cache persist across Docker restarts? Default: no) →
EXEC BRIEF (plain English for Jajean)

**Quick spec for a small UI change:**
> "/write-spec quick: add cache hit indicator to status bar"

PROBLEM + SCOPE + ACCEPTANCE CRITERIA only → done in 10 minutes
