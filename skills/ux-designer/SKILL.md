---
name: ux-designer
description: >
  Multi-agent UX design skill for data-heavy tools and domain-expert interfaces.
  Activate when designing or reviewing UI/UX: layout decisions, error states, loading
  feedback, information hierarchy, user flows, or any request involving how a non-technical
  user will experience the product. Uses a Karpathy-style team of focused agents to
  reason through design decisions — more thinking at design time means fewer rework cycles.
  Triggers on: "design the UI", "review this UX", "how should we show X", "what happens
  when Y fails", "improve the user experience", "what would a user expect", "empathy map".
---

# ux-designer — Multi-Agent UX Design Skill

A phase-gated design loop that spawns a team of focused agents, each reasoning
independently, then synthesises their proposals into an implementation-ready spec.

Modelled after Karpathy's "scale test-time compute" principle: allocate more
reasoning at design time rather than iterating on shipped UI.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full loop: all phases |
| `empathy only` | UNDERSTAND → EMPATHY MAP → stop |
| `spec only` | UNDERSTAND → SPEC (quick, skip team session) |
| `review this` | UNDERSTAND → CRITIC REVIEW of existing design |
| `full team` | All phases with 3-agent independent team session |
| `enter: SPEC` | Skip to SPEC (assumes UNDERSTAND + EMPATHY already done) |

---

## Context Capture (Always First)

Before any phase, extract:

```
USER TYPE:      [technical level, domain expertise, frequency of use]
TASK:           [what the user is trying to accomplish — one sentence]
HAPPY PATH:     [ideal flow from question to answer]
FAILURE MODES:  [what can go wrong — errors, slow responses, no data]
CONSTRAINTS:    [branding, accessibility, framework, existing components]
DOMAIN:         [e.g. bioacoustic monitoring, finance, healthcare]
```

If context is already in the conversation, infer and state assumptions. Only ask
if a failure mode or constraint is genuinely blocking.

---

## The Seven Phases

Each phase begins with: `[PHASE: NAME]`

---

### Phase 1 — UNDERSTAND

1. Parse the design task. Restate it: what does the user need to do, and what
   does success look like?
2. Identify the user type: technical level, domain knowledge, use frequency.
3. Check `references/patterns.md` for matching UI patterns in data-heavy tools.
4. Flag the top 2–3 failure modes that the design must handle explicitly.
5. Declare which phases will run and why.

> Output: CONTEXT BLOCK (≤10 lines) carried into all subsequent phases.

---

### Phase 2 — EMPATHY MAP

Map what the user **knows / feels / does / says** — and crucially, what they
**don't know** and **don't expect**.

```
KNOWS:     [domain concepts, vocabulary, data shape]
DOESN'T KNOW: [what SQL is, what "validation_status" means, why it takes 30s]
FEELS:     [curious? anxious about wrong answers? impatient during waits?]
DOES:      [types a question, reads the answer, copies data into a report]
SAYS:      [example questions they'd actually ask]
EXPECTS:   [immediate feedback, plain English, no jargon]
DOESN'T EXPECT: [error codes, empty screens, raw SQL]
```

Derive design implications from each row. A "doesn't know / doesn't expect"
row is worth at least one concrete design decision.

---

### Phase 3 — TEAM SESSION

Spawn three agents independently (no shared reasoning):

**Agent A — Designer**
Focus: visual hierarchy, layout, component choice, information density.
Produce: a component list + rough layout description (no wireframe tools needed —
prose description of spatial arrangement is sufficient).

**Agent B — Cognition**
Focus: cognitive load, progressive disclosure, mental models, working memory.
Produce: a state table showing what the user sees in each UI state, and a list
of cognitive load reduction decisions.

**Agent C — Domain**
Focus: the specific domain (e.g. bioacoustics, conservation data) and user type.
Produce: domain-specific vocabulary decisions, what to explain vs. assume, and
how to frame outputs for a non-technical domain expert.

Each agent produces their proposal independently before synthesis.

---

### Phase 4 — SYNTHESIS

Merge the three proposals:

1. List decisions where all three agents agree → these are consensus wins.
2. List decisions where agents conflict → resolve each with a stated rationale.
3. Identify gaps: what did no agent address?

Emit as:
```
[CONSENSUS] Decision — rationale
[RESOLVED CONFLICT] Decision — what conflicted, why this was chosen
[GAP FILLED] Decision — what was missing, what was decided
```

---

### Phase 5 — SPEC

Produce an implementation-ready design spec:

**State table** — every UI state the user can be in:

| State | Trigger | What user sees | What user can do |
|-------|---------|---------------|-----------------|
| Idle | Page load | Empty question box, history sidebar | Type a question |
| Loading | Submit | Progress messages, spinning indicator | Wait (or cancel) |
| Success | Query returns | Answer, results table, SQL | Read, copy, ask another |
| Guard error | Bad SQL generated | Explanation + SQL shown | Rephrase question |
| DB error | Query fails | Clear error message | Try again |
| Empty result | 0 rows | Explicit "no results" message | Rephrase question |

**Copy strings** — exact text for each state (no Lorem Ipsum, no "message here").

**Interaction flows** — numbered steps for the happy path and top 2 failure modes.

**Component decisions** — for each output area: what component, why, what it shows
in each state.

---

### Phase 6 — CRITIC REVIEW

A fresh agent reads the spec with no prior context and audits it against
`references/checklist.md`.

Emit findings as:
```
[FINDING: SEVERITY] Category — Description
  Risk: what the user experiences if this is wrong
  Fix: one concrete change to the spec
```

Severity: `BLOCKING` | `HIGH` | `MEDIUM` | `LOW`

After all findings: state whether the spec is ready to implement, needs revisions,
or is blocked.

---

### Phase 7 — HANDOFF

Produce two outputs:

1. **Implementation spec** — final, clean version of the spec after critic fixes.
   Structured as: component list, state table, copy strings, interaction flows.

2. **Open questions** — decisions that require product/stakeholder input before
   implementation (max 5, each with a "default if unanswered" so work can proceed).

---

## Quality Bars (Non-Negotiable)

- Every error state must have explicit copy — no "something went wrong"
- Loading states must communicate *what* is happening, not just that it's busy
- Empty states must explain *why* and suggest a next action
- No jargon in user-facing copy unless the user is confirmed technical
- Cognitive load: the user should never need to hold more than 3 things in
  working memory at once
- The happy path must be achievable in ≤3 interactions from page load

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/cognition.md` | EMPATHY MAP + TEAM SESSION (Agent B) |
| `references/patterns.md` | UNDERSTAND + TEAM SESSION (Agent A) |
| `references/checklist.md` | CRITIC REVIEW phase |

---

## Example Flows

**Full design session:**
> "Design the error state for when canopy generates invalid SQL."

Claude: UNDERSTAND → EMPATHY MAP → TEAM SESSION (3 agents) → SYNTHESIS →
SPEC (state table + copy strings) → CRITIC REVIEW → HANDOFF

**Quick spec:**
> "How should we show query progress to a non-technical user? spec only."

Claude: UNDERSTAND → SPEC → stop (no team session, faster output)

**Review existing design:**
> "Review the current canopy UI for cognitive load issues. review this."

Claude: UNDERSTAND → CRITIC REVIEW against checklist → findings + fix list

**Empathy-first:**
> "I need to understand what Jajean actually experiences. empathy only."

Claude: UNDERSTAND → EMPATHY MAP → stop
