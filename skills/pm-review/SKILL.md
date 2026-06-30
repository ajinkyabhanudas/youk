---
name: pm-review
description: >
  Product thinking gate. Answers "should we build this, in this order, for these users?"
  before any implementation begins. Forces explicit problem definition, user impact
  estimation, technical cost assessment, and "what are we NOT building" reasoning.
  Produces a one-paragraph decision memo ready to share with stakeholders. Calibrated
  for solo or small-team development — not enterprise process overhead. Triggers on:
  any new feature request, scope expansion, prioritization question, "what should we
  build next", or any time a user story needs to be assessed before entering dev-loop.
  Also functions as an AI PM layer: tracks what's been deferred and why, surfaces
  priority debt when deferred items become urgent.
---

# pm-review — Product Thinking Gate

A phase-gated product review skill that applies PM thinking to any feature request
before implementation begins. Combines the rigor of product management frameworks
with the technical depth of an engineering perspective — because the best product
decisions require both.

This skill is not a bureaucratic gate. It is a structured way to make sure the next
thing built is the right thing — for the right reason, at the right time, with an
honest account of what is not being built and why.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full review: PROBLEM → USER → COST → ALTERNATIVES → RISK → RECOMMEND → BRIEF |
| `quick` | Abbreviated: PROBLEM → RECOMMEND → BRIEF (for small features with obvious value) |
| `prioritize: [list]` | Given a list of features, rank them by P0/P1/P2 with reasoning |
| `defer check` | Review the deferred backlog — has any deferred item become urgent? |
| `why not: [feature]` | Articulate specifically why this feature is NOT being built (now or ever) |
| `scope: [feature]` | Define and bound the scope of a feature before design begins |

---

## Context Capture (Always First)

Before any phase, extract or infer:

```
FEATURE:      [one sentence describing what would be built]
REQUESTOR:    [who is asking — user, stakeholder, tech debt, regulatory]
DEADLINE:     [any time constraint — handover date, event, user expectation]
CONSTRAINTS:  [what cannot change — existing commitments, tech stack, team size]
CURRENT P0s:  [what is already in flight and must not be delayed]
KNOWN DEFERREDS: [features already explicitly deferred with reasoning]
```

---

## The Seven Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — PROBLEM

Define the problem being solved — not the feature being built. Features are solutions.
Problems are what matter.

1. State the problem in one sentence: "Users cannot do X, which means Y fails."
2. Verify the problem is real: Is this observed behavior, or an assumption?
3. State who has this problem and how often.
4. State what currently happens instead — what workaround exists (if any)?
5. Ask: Is this the right level of abstraction? (Are we solving a symptom of a deeper problem?)

Emit:
```
[PROBLEM DEFINITION]
Problem:     {one sentence}
Evidence:    {observed / inferred / assumed}
Frequency:   {every use / daily / weekly / rare}
Current workaround: {what users do today}
Root problem check: {is this the actual problem, or a symptom of {deeper problem}?}
```

> If EVIDENCE is "assumed" — flag this. Assumed problems are the most common source
> of built features that don't get used.

---

### Phase 2 — USER

Map the user who benefits. One feature, one primary user. If it benefits multiple
distinct users differently, treat as separate features.

Read `references/user-framework.md` for the user impact assessment framework.

1. Who is the primary user? (specific person / role, not abstract "user")
2. What does this change about their experience?
3. How does this change their outcome (not just their experience)?
4. What is the frequency of impact? (every use vs. rarely)
5. Is this a nice-to-have or does the product fail without it?

Emit:
```
[USER IMPACT]
Primary user: {specific person / role}
Change to experience: {what changes for them}
Change to outcome: {what they can now accomplish that they couldn't before}
Frequency: {how often they'd benefit}
Criticality: {product works without this | product works better | product fails without this}
```

---

### Phase 3 — COST

Assess the technical cost honestly. Read `references/cost-estimation.md`.

1. Complexity estimate: S / M / L / XL (see cost-estimation.md for calibration)
2. New surface area introduced (new modules, new dependencies, new failure modes)
3. Ongoing maintenance cost (does this require updates as other things change?)
4. Technical debt impact (does this incur new debt or pay off existing debt?)
5. Time estimate in developer-days

Emit:
```
[COST ASSESSMENT]
Complexity: S | M | L | XL
Dev-days estimate: {N}
New surface area: {none | list}
Ongoing maintenance: {none | low | medium | high}
Debt impact: {incurs debt | neutral | pays off: [describe]}
Risk: {low — well-understood; medium — some unknowns; high — significant unknowns}
```

---

### Phase 4 — ALTERNATIVES

What else could we do instead? This phase prevents tunnel vision around the originally-proposed solution.

1. List at least 2 alternatives (one must be "do nothing / defer")
2. For each alternative: user impact, technical cost, key trade-off
3. State which alternative is the current proposal and why it's preferred over the others

```
[ALTERNATIVES]
Option A — {name}: {impact} | {cost} | {trade-off}
Option B — {name}: {impact} | {cost} | {trade-off}
Option C — Do Nothing: {impact of NOT building} | cost: zero | trade-off: {what users continue to experience}

Preferred: {option} because {specific reason}
```

> "Do Nothing" must always be listed as an option. If it's clearly worse than building,
> say why. If it's unclear, that's a signal to defer.

---

### Phase 5 — RISK

What could go wrong? Two types of risk:

**Product risk**: We build it and users don't use it / don't value it / it doesn't solve the problem.
**Technical risk**: We build it and it breaks other things / takes longer than estimated / creates maintenance burden.

```
[RISK ASSESSMENT]
Product risk:   {probability} — {specific scenario where this fails to deliver value}
Technical risk: {probability} — {specific technical failure mode}
Mitigation:     {what reduces the product risk | what reduces the technical risk}
Early signal:   {how will we know within N days if this is failing?}
```

---

### Phase 6 — RECOMMEND

Issue a clear recommendation. No hedge words.

| Recommendation | Meaning |
|---|---|
| **BUILD P0** | This blocks current P0 work or is directly requested by a key stakeholder for an imminent deadline |
| **BUILD P1** | High value, understood cost, ready to implement after current P0s |
| **BUILD P2** | Real value but not urgent; implement after P1s are clear |
| **DEFER** | The problem is real but this is not the right time. State the trigger. |
| **REJECT** | This should not be built. State why permanently. |
| **SCOPE FIRST** | The request is unclear or too large. Define scope before deciding. |

```
[RECOMMENDATION]
Decision: {BUILD P0 | BUILD P1 | BUILD P2 | DEFER | REJECT | SCOPE FIRST}
Rationale: {one sentence — specific, not "it's important"}
If DEFER — trigger: {specific condition under which this becomes P1}
If REJECT — reason: {why this is permanently not the right investment}
What we are NOT building (and why): {the adjacent thing that could have been requested}
```

---

### Phase 7 — BRIEF

A one-paragraph summary written in Ajinkya's voice, ready to share with a stakeholder
or to paste into a project document.

```
[BRIEF]
{One paragraph. States the problem, the decision, and the key reason. Mentions the most
significant thing NOT being done and why. Written in first person, present tense. No
technical jargon for a non-technical audience; the right level of detail for a technical
audience. Maximum 5 sentences.}
```

**Quality gate: domain-expert reader test** (see `references/exec-brief-test.md`).

Read the BRIEF aloud as if explaining it to someone who knows the problem domain but not the implementation. They must be able to answer without a follow-up: (1) what was built, (2) who it helps and how, (3) what we decided not to do and why. If they would ask "what does that mean?" — rewrite. This test is non-optional.

---

## Quality Bars (Non-Negotiable)

- **No feature without a problem.** "It would be nice to have" is not a problem statement.
- **REJECT requires a permanent reason.** "Not now" is DEFER, not REJECT.
- **DEFER requires a trigger.** "Later" is not a trigger. "When daily active users exceed 10" is.
- **"Do Nothing" is always a valid option.** If you can't articulate why building is better than not building, don't build.
- **The BRIEF is mandatory.** Decisions that can't be summarized in 5 sentences are not clear decisions.
- **Cost and user impact must be independent assessments** — they must not be co-constructed. High user impact doesn't lower the cost.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Problem definition test**: Given "add dark mode", it produces "Users cannot use the tool in low-light environments" as the problem — not "add dark mode" as the problem.
2. **Do Nothing test**: On any feature request, it produces a concrete "Do Nothing" assessment with the honest cost of not building.
3. **Reject vs. Defer discipline**: "This will never be in scope because X" (REJECT) is handled differently from "This is valuable but not yet" (DEFER). It never confuses the two.
4. **Brief test**: The BRIEF passes a non-technical stakeholder read — they understand what was decided and why, without needing the full analysis.
5. **Tunnel vision test**: On a request with an obvious implementation, it surfaces at least one non-obvious alternative that the requester hadn't considered.
6. **Priority conflict test**: When a new P0 feature is proposed while other P0s are in flight, it surfaces the conflict explicitly and asks for a priority call.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/user-framework.md` | USER phase — impact assessment templates |
| `references/cost-estimation.md` | COST phase — S/M/L/XL calibration |
| `references/prioritization-framework.md` | RECOMMEND phase — P0/P1/P2 criteria |

---

## Example Flows

**Standard feature review:**
> "Should we add an export-to-CSV button?"

PROBLEM (users need to share results outside the tool) → USER (the non-technical stakeholder
who exports to share with donors or partners) → COST (S — one UI component) →
ALTERNATIVES (do nothing, copy-paste workaround) → RISK (low — clear scope) →
RECOMMEND (BUILD P1 — after cache-hit UI) →
BRIEF ("Stakeholders can now share query results directly as a CSV without manual copying...")

**Scope-first case:**
> "We should add external data source integration."

PROBLEM (external data enriches answers) → ... → RECOMMEND (SCOPE FIRST —
the request could mean: API lookup per result, cached database, or manual tagging.
Each is a different cost. Define before deciding.)

**Prioritization:**
> "Prioritize: IUCN integration, export CSV, user authentication, semantic caching."

PROBLEM (each assessed) → COST (each estimated) → RECOMMEND (P0: auth if multi-user;
P1: semantic caching — saves API costs; P2: export CSV; DEFER: IUCN — needs API key)
