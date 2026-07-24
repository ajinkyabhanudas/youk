---
name: adr
rationale_why: "Undocumented decisions get re-debated, reversed silently, or forgotten. Writing the 'why not' alongside the 'why' ends the debate permanently and makes the cost of reversal visible."
description: >
  Architecture Decision Record generator. Fires whenever a significant technical decision
  is made — new module, library selection, pattern adoption, technology choice, or reversal
  of a prior decision. Forces explicit "why NOT" documentation alongside the chosen option.
  Uses a two-agent debate structure: one agent argues FOR the decision, one argues AGAINST,
  and the record documents both. Prevents the most expensive engineering pattern: re-debating
  settled decisions because the rejection reasoning was never written down. Triggers on:
  "which should we use", "how should we structure", "should we use X or Y", any CONNECT
  output from /nfr-check, or any time a new DECISIONS.md entry is warranted.
---

# adr — Architecture Decision Record Skill

A phase-gated decision documentation skill that produces DECISIONS.md entries with
mandatory rejection reasoning. Built on the principle that the most valuable part of
a design decision is not what was chosen, but why the alternatives were not — because
that's what prevents future teams (or future you) from re-debating settled ground.

Uses a two-agent debate structure to surface arguments on both sides before the decision
is locked. This is not about slowing down decisions — it's about making them stick.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full ADR: SCOPE → EXPLORE → DEBATE → DECIDE → DOCUMENT → LINK |
| `quick` | Abbreviated: SCOPE → DECIDE → DOCUMENT (skip formal debate; for small decisions) |
| `reverse: [decision ID]` | Reopen an existing decision: SCOPE → DEBATE → REVERSE → DOCUMENT |
| `review` | Audit DECISIONS.md for entries missing "why not" sections |
| `trigger: [NFR/feature]` | Generate ADR from an NFR trigger — pre-scoped for that feature |
| `enter: DOCUMENT` | Skip to DOCUMENT (decision already made externally, needs recording) |

---

## Context Capture (Always First)

Before any phase, extract or infer:

```
DECISION:     [one sentence — what is being decided]
TRIGGER:      [what prompted this decision — NFR output / new module / tech choice / incident]
SCOPE:        [module / feature / system-wide / cross-project]
CONSTRAINTS:  [existing decisions that constrain this one; technology already in use]
REVERSIBILITY:[easy | hard | very hard — how costly is it to change later?]
RELATED ADRS: [IDs of existing DECISIONS.md entries this connects to]
```

If the decision is already made and the user just needs it recorded (`enter: DOCUMENT`),
skip the debate phases and go directly to DOCUMENT.

---

## The Six Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — SCOPE

Precisely define the decision:
1. Restate the decision as a question: "Should we use X or Y for purpose Z?"
2. Identify the decision type (see `references/decision-triggers.md`)
3. State the reversal cost: easy / hard / very hard
4. List constraints that rule out some options
5. State what "good enough" looks like — the minimum bar any option must meet

> Decisions that are "very hard" to reverse get the full DEBATE phase.
> Decisions that are "easy" to reverse can use `quick` mode.

---

### Phase 2 — EXPLORE

Enumerate alternatives. Minimum: 2. Ideal: 3. Maximum: 4 (more than 4 usually means
the decision isn't scoped tightly enough).

For each alternative:
```
OPTION {N}: {name}
  What it is: {one-sentence description}
  How it addresses the need: {what problem it solves}
  Key properties: {performance / complexity / cost / maturity / ecosystem}
  Prerequisites: {what must be true for this option to work}
```

Read `references/common-trade-offs.md` for pre-built option comparisons on frequently
recurring decisions (caching backends, SQL vs. NoSQL, sync vs. async, etc.).

---

### Phase 3 — DEBATE

Two independent agents reason about the decision. Each sees the SCOPE and EXPLORE output
but not the other's reasoning.

**Agent A — Advocate:**
Argues for the strongest option as vigorously as possible.
Produces:
- Top 3 reasons to choose this option
- The specific scenario where it clearly outperforms alternatives
- What would have to be true for a different option to be better

**Agent B — Challenger:**
Argues against the strongest option as rigorously as possible.
Produces:
- Top 3 weaknesses or risks of this option
- The specific scenario where it fails or creates regret
- Which alternative is better and why (not just "it depends")

After both agents produce their reasoning, synthesize:
```
[DEBATE SUMMARY]
Strongest arguments FOR:    [1-3 bullets]
Strongest arguments AGAINST: [1-3 bullets]
Scenario where this fails:  [specific, not hypothetical]
What Agent B's best alternative would need to be true: [conditions]
```

> If both agents strongly agree, note the consensus and reduce the DECIDE phase to
> confirming the obvious choice. If they fundamentally disagree, flag that this is
> a "genuine trade-off" and make the resolution explicit.

---

### Phase 4 — DECIDE

State the decision clearly:
1. Which option is chosen
2. Why it was chosen (not just "it's better" — specific, testable reasoning)
3. For each rejected alternative: exactly why NOT — one sentence minimum
4. What conditions would trigger reversal of this decision

Emit:
```
[DECISION]
Chosen: {option name}
Reason: {the specific, testable reason — not a truism}

REJECTED:
  {Option A}: because {specific reason — not "it was worse overall"}
  {Option B}: because {specific reason}

REVERSAL CONDITIONS:
  Revisit this decision if: {specific trigger — e.g. "cache hit rate falls below 20%"}
```

> "Why NOT" is non-optional. If you cannot state a specific reason an option was rejected,
> you have not yet made a real decision — you have just expressed a preference.

---

### Phase 4.5 — SELF-CHECK

Mandatory before DOCUMENT. One question — a specific named answer is required.

**Q — Proxy check:**
"What is the decision I'm avoiding by making this one? Name it explicitly. A good ADR
records the real decision. A proxy ADR records a symptom of the real decision, which
means the real decision will resurface. If I cannot name what I'm avoiding, this ADR
may be a proxy — state that explicitly before documenting."

Emit one of:
- `[DEPTH NOTE: real decision captured / proxy avoided: {what would have been the proxy}]`
- `[PROXY RISK: {the avoided decision} — documenting the surface decision; real decision needs separate ADR]`
- `[SHALLOW: {what wasn't resolved — the decision is not yet scoped enough to be real}]`

If PROXY RISK: continue to DOCUMENT the surface decision, but add a note in Consequences
identifying the deferred real decision and its trigger.

---

### Phase 5 — DOCUMENT

Write the canonical DECISIONS.md entry using the format from `references/adr-format.md`.

Each entry must include:
- A unique ID (D{N} — next in sequence)
- Status: ACTIVE | DEFERRED | REVERSED | ARCHIVED
- Context: why this decision had to be made now
- Options and the "why not" for each rejected option
- Consequences (three mandatory subsections — all required, none optional):
  - **Enables:** what this decision makes possible that wasn't possible before
  - **Forecloses:** what future options this decision makes significantly harder or impossible — name them specifically. "Nothing" is almost never correct. If you cannot name what this forecloses, you have not thought about it hard enough.
  - **Creates:** what new decisions this decision forces — decisions that now must be made because of this one
- Reversal conditions

**Foreclosure is the L10+ field.** The difference between an engineer who sees one version ahead and one who sees five versions ahead is that the second one knows what each decision closes off. Forecloses is not "what we gave up" — it is "what we can never easily do again." That is the field that makes future architectural work faster: the foreclosed space is already mapped.

**Status definitions:**
- `ACTIVE` — decision is in force, the system it governs exists and is live
- `DEFERRED` — not yet decided; parked for a specific trigger
- `REVERSED` — was active, was overturned; the governed system still exists but took a different path
- `ARCHIVED` — no longer applicable because the governed system or feature was **removed entirely** (not reversed — gone). Mark ARCHIVED when deleting a subsystem, removing a feature entirely, or retiring an integration. An ARCHIVED ADR is historical context, not a live rule.

**Granularity rule:** If a decision affects more than 2 independent systems (e.g. "choose the auth pattern" affects API, frontend, and mobile), split into per-system ADRs with a parent ADR that links them. One decision per ADR prevents confusion when systems evolve at different rates. The parent ADR describes the cross-system constraint; child ADRs describe the per-system implementation.

The entry is written ready to paste into DECISIONS.md without further editing.

---

### Phase 6 — LINK

Check for connections:
1. Does this decision conflict with any existing ADR? (read DECISIONS.md)
2. Does this decision depend on any existing ADR remaining ACTIVE?
3. Does this decision create new NFR decisions? (emit CONNECT output compatible with /nfr-check)
4. Does this decision affect any living document? (canopy-context.md, README, schema.py)
5. Does a recent commit remove or retire the system governed by an existing ADR? If so, flag it for ARCHIVED status — don't leave stale ACTIVE ADRs for systems that no longer exist.

Emit:
```
[LINKS]
Conflicts:          [none | list with IDs]
Depends on:         [none | list with IDs — "if D3 reverses, revisit this"]
New NFR triggers:   [none | list]
Living docs to update: [none | list]
```

---

## Quality Bars (Non-Negotiable)

- **Every rejected option must have a stated reason.** "We didn't choose X" without a reason is not documentation.
- **Reversal conditions are mandatory.** Every decision has conditions under which it should be reconsidered. State them.
- **No decision IDs may be reused.** New entries always increment.
- **REVERSED entries stay in DECISIONS.md** with a note pointing to the new ACTIVE entry. History is preserved.
- **The DECIDE phase is binding.** If the debate doesn't produce a clear winner, escalate — do not pick arbitrarily.
- **`quick` mode is only for low-reversal-cost decisions.** Architectural choices always get the full debate.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Foreclosure test**: Given any decision, it produces at least one specific "Forecloses" entry — not "nothing" and not a vague "limits flexibility." "Choosing in-process cache forecloses horizontal scaling without a cache migration" is a passing foreclosure. "Limits some options" is not.
2. **Rejection test**: Given "we chose PostgreSQL for the cache", it forces out "we didn't choose Redis because [specific reason]" before accepting the decision as documented.
2. **Reversal test**: Given any decision, it produces a non-trivial reversal condition ("revisit if X" — not "revisit if the decision is wrong").
3. **Conflict detection**: Given a new decision that contradicts an existing ADR, it surfaces the conflict before documenting.
4. **Quick-mode discipline**: On a `quick` invocation, it produces a ≤10-line ADR entry without ceremony — not a full debate for a one-line config choice.
5. **Debate quality**: Agent A and Agent B produce genuinely different arguments — not two versions of the same argument. If they agree too easily, the decision was too easy for full debate mode.
6. **Living doc integration**: After every ADR, it lists which living documents need updating — it never assumes "nothing changed."

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/decision-triggers.md` | SCOPE phase — decision type classification |
| `references/common-trade-offs.md` | EXPLORE phase — pre-built option comparisons |
| `references/adr-format.md` | DOCUMENT phase — canonical DECISIONS.md entry format |

---

## Example Flows

**Technology choice:**
> "Should we use Redis or an in-process dict for the query cache?"

SCOPE (caching backend, hard to reverse mid-production) → EXPLORE (Redis, in-process LRU,
SQLite) → DEBATE (Agent A: in-process is zero-infra; Agent B: in-process doesn't survive
restart) → DECIDE (in-process, because single-process Gradio app, Docker-deployed,
restart clears it intentionally) → DOCUMENT (D{N}) → LINK (connects to D2: cache.py decision)

**NFR-triggered ADR:**
> "The /nfr-check output flagged 'external API integration pattern' as an ADR trigger."

SCOPE → EXPLORE (how to handle external API calls: direct calls, abstraction layer,
SDK wrapper) → DEBATE → DECIDE → DOCUMENT → LINK

**Reversing a past decision:**
> "Revisit D3 — the SELECT-only guard approach. We want to allow INSERT for logging."

SCOPE (reverse D3) → read existing D3 → DEBATE (is the original reasoning still valid?) →
DECIDE (maintain D3 / modify / reverse) → DOCUMENT (new entry + update D3 status) → LINK
