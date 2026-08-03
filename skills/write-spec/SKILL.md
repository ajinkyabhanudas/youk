---
name: write-spec
rationale_why: "Ambiguity discovered during implementation costs 10x more than ambiguity resolved before it. A spec makes every open question explicit while they're still cheap to answer."
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

Roadmap items (CAPs) produced by adversarial-planning are translated to implementation-ready specs with this skill.

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
| `system-prd` | Whole-product PRD — north star + metric decomposition, journeys, funnel, prioritization. See SYSTEM-PRD MODE below. Distinct phase structure, not the Eight Phases. |

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

## SYSTEM-PRD MODE

A different genre from the Eight Phases above. The Eight Phases scope one feature
before an engineer starts building it — problem sentence, ≤10 requirements, ≤3 open
questions, single primary metric. A system PRD covers a whole product: a founder or
a candidate in an interview needs to walk through why the thing exists, how it's
measured end to end, who it's for at each stage of using it, what got traded off
against what, and what's still a real gap. Forcing that into the Eight Phases'
caps produces false compression, not precision. This mode has its own phases,
its own caps, and its own honesty rules for retrospective writing.

Triggers on: `system-prd`, "write a full PRD for this product", "PRD for the whole
system", any request that names north star metrics, HEART, AARRR, user journeys,
or interview-prep framing alongside "PRD". Output goes to a project folder as its
own document, not inline in chat.

### Phase 0 — ORIGIN INTERVIEW (mandatory, before any other phase, no exceptions)

The single most common failure in this mode is reconstructing the problem statement
from artifacts (README, ADRs, code) instead of asking the person who actually had the
problem where the idea came from. An artifact tells you what was built. It does not
reliably tell you why, and a plausible-sounding "why" inferred from a tech stack or a
feature list can be confidently wrong in a way that undermines the entire document
built on top of it, no matter how well-tagged the rest of the PRD's claims are.

Before writing PROBLEM & WHY NOW, ask the developer directly, in this order, and do
not proceed on inference alone:

1. "Where did this idea actually come from? A specific event, a prior project, a
   conversation, a frustration you lived through — not the general category of
   problem the product now addresses."
2. "Who is the real first user, by name or by the actual role they hold, not a
   generic persona invented to fit the product?"
3. "What's the real alternative this replaces or competes with? Not the nearest
   AI-tool competitor, the thing a person would actually otherwise do."

If the developer has already stated the origin earlier in the conversation, do not
re-ask, but do restate it back in one line and confirm before drafting: "Confirming
before I write this: the origin is {X}, the real first user is {Y}, is that right?"
Proceeding to draft PROBLEM & WHY NOW without this confirmation, on a retrospective
PRD, is the single highest-risk step in the whole mode. A wrong problem statement at
the top corrupts the north star, the users section, and the journey maps built on
top of it, since all three take their shape from what the top of the document says
the problem actually is.

### Mode selection: prospective vs. retrospective

State this explicitly at the top of the output, in one line:

```
MODE: [PROSPECTIVE — written before/during build] or [RETROSPECTIVE — system already exists]
```

**Retrospective is the harder, riskier mode and needs its own discipline.** When the
product already exists, every claim about "why we built it this way" is either:
(a) a decision that was actually made before the code, verifiable against ADRs,
commit history, or PLAN docs — cite the source; or
(b) a reasonable reconstruction written after the fact because the reasoning was
never captured at the time.

Tag every non-trivial claim in the DESIGN & TRADEOFFS section with one of:
`[decided-before-build — see {ADR/commit/doc}]` or `[reconstructed]`.
Never blend the two without the tag. Presenting a reconstructed narrative as if it
were the original reasoning is the exact confidence-inflation this discipline
exists to prevent — the PRD's credibility depends on this distinction being visible,
not smoothed over.

### Voice rules (apply to every phase, no exceptions)

Write like a person explaining their own product, not like a model narrating one.

- No em-dashes.
- No "it wasn't X, it was Y" or "not just X, but Y" constructions, in any variant.
- No "load-bearing," no "the real question is," no theatrical framing words.
- No inflated transition phrases ("crucially," "fundamentally," "at its core").
- Plain declarative sentences. Say the thing, then the next thing.
- If a sentence would sound natural read aloud in a normal conversation, keep it.
  If it sounds like a keynote slide, cut it.

### The Phases

Each phase begins with: `[PHASE: NAME]`. No hard requirement caps in this mode —
the caps in the Eight Phases exist to stop feature-scope creep, which does not
apply to a whole-product document. Depth here is the point.

---

**Phase 1 — CONTEXT**

```
[CONTEXT]
Product:        {name, one line on what it is}
Mode:           {PROSPECTIVE / RETROSPECTIVE}
Stage:          {idea / building / shipped / live with users}
Primary source: {repo, docs read, ADRs reviewed — what grounds this doc}
```

**Phase 2 — PROBLEM & WHY NOW**

Same discipline as the Eight Phases' PROBLEM phase (one clear sentence a reader
could re-scope from), but add:

```
[PROBLEM & WHY NOW]
{User} cannot {do specific thing} because {specific constraint}.
Why this, why now: {what changed that makes this worth building today, not
  a defensible-sounding generic problem statement}
Who else has tried to solve this and what happened: {real alternatives in the
  market, or "not researched" if genuinely not known}
```

**Phase 3 — NORTH STAR & METRIC DECOMPOSITION**

The metric structure the Eight Phases cannot produce (they cap at one primary,
one secondary, one counter metric for a single feature).

```
[NORTH STAR]
Metric: {the single number that best represents value delivered}
Why this metric and not a nearby alternative: {the actual tradeoff — e.g. why
  "verdicts delivered" beats "queries run" as the north star}

[DECOMPOSITION TREE]
North star
  driver 1: {metric} — moved by {which part of the product}
    input metric: {metric} — moved by {specific feature/mechanism}
    input metric: {metric} — moved by {specific feature/mechanism}
  driver 2: {metric} — moved by {which part of the product}
    input metric: ...

[OKRS — the numbers that decide if this worked]
{2-3 objectives, ordered by what matters most, not by what's easiest to measure.
  Each objective gets 1-3 key results. Every KR is either a real number with a
  real date ("70% of navigation queries answered without escalation within 8
  weeks of launch"), or explicitly marked NOT YET TRACKABLE with the specific
  reason (no live user yet, instrumentation not built yet) and what has to
  happen before it becomes trackable. There is no third option. A KR that is
  neither a committed number-and-date nor explicitly marked untrackable is not
  a real KR, it is filler, and it reads as filler to anyone who's seen a real
  OKR set.}

Objective 1: {the thing that matters most}
  KR 1.1: {number}, by {date/milestone}, measured by {method} — or NOT YET
    TRACKABLE: {why, and what unblocks it}
  KR 1.2: ...

Objective 2: ...
```

**"Cannot measure it, cannot treasure it."** An objective with no committed number
and no named path to getting one is not evidence of intellectual honesty, it is the
thing a sharp reviewer calls fluff. The bar this mode holds itself to is not "we
were honest that we don't have data." It's "we named the exact number, the exact
date, and if we don't have it yet, the exact thing that has to happen for us to get
it." Distinguish real absence (genuinely no live user, correctly stated as
untrackable with a plan) from lazy absence (a number that could be defined and
tracked now but wasn't, because it was easier to write "not measured").

[HEART / HAPPINESS METRICS — supporting detail under the OKRs above, not a
  replacement for them]
Happiness:    {how satisfaction is measured or would be measured}
Engagement:   {depth of use signal}
Adoption:     {new-user signal}
Retention:    {return-use signal}
Task success: {did the user complete what they came to do}

[FUNNEL / AARRR]
Acquisition:  {how a user arrives}
Activation:   {the moment value is first felt}
Retention:    {what brings them back}
Referral:     {does this product spread, and how — or state why it doesn't}
Revenue:      {if applicable — or state why not applicable at this stage}

[DELIGHT — separate from the funnel above]
{The specific moment(s) in the product that exceed the user's expectation,
  not just meet the functional requirement. If none exist yet, say so plainly
  rather than manufacturing one.}
```

**Phase 4 — USERS & JOURNEY MAPS**

```
[USERS]
Primary:    {role} — {context, frequency, what they need}
Secondary:  {role} — {how affected}
Out of scope: {who this explicitly does not serve, and why}

[JOURNEY: {primary user, primary flow}]
Stage:            {name}
Trigger:          {what starts this stage}
User does:        {action}
Product does:     {response}
Friction/risk:     {where this stage can go wrong}
Emotional state:  {confidence, doubt, relief — named plainly, not decorated}
  ... repeat per stage through to outcome ...

Add a second journey only if a genuinely different persona or flow exists.
Do not pad with a journey that is a trivial variant of the first.
```

**Phase 5 — PRIORITIZATION & TRADEOFFS**

The reasoning layer the Eight Phases push into "out of scope, deferred" without
explaining the comparison. Here, show the comparison.

```
[PRIORITIZATION]
What we built first and why: {reasoning, not just the choice}
What we deliberately did not build yet: {each item, with the actual tradeoff
  against something else competing for the same time/risk budget}
What we would build next if unconstrained: {and what's actually constraining it}

[DESIGN & TRADEOFFS]
Decision: {the choice made}
  Alternative considered: {the real alternative, not a strawman}
  Why not the alternative: {the specific cost, not a vague "more complex"}
  Tag: [decided-before-build — see {source}] or [reconstructed]
  ... repeat per major decision ...

[BUILD ORDER AND SIGNIFICANCE — RETROSPECTIVE MODE ONLY, mandatory when applicable]
{Prospective PRDs skip this block, there's no build history yet. Retrospective
  PRDs must include it, and it is not the same exercise as walking the ADRs (or
  equivalent decision records) in their own numbering. ADR/decision numbers are
  usually assigned when a decision is formalized in writing, which is often not
  the order the underlying work actually happened. Verify true build order
  against primary evidence (git log, commit dates, each ADR's own stated
  underlying-decision date) before writing this section — do not assume
  numbering equals sequence.

  Walk the true chronological order. For each major step: what was built, which
  north star driver it moved (or state plainly that it moved none yet, if it was
  a prerequisite other drivers needed before they could be measured at all), and
  tag retrospective claims the same way the rest of this mode does
  ([decided-before-build — see {source}] or [reconstructed]).

  Close with one synthesis paragraph connecting the build order itself to the
  forward-looking BUILD PRIORITY ranking below: which driver got built first and
  why (often a prerequisite, not the most important driver in the abstract),
  which got built most thoroughly measured, and which is newest and thinnest —
  and state directly why that leftover thinness is what the forward-looking
  ranking should address first. The build order is not just history. It's the
  actual evidence for why the next list is shaped the way it is.}

[BUILD PRIORITY — RANKED BY NORTH STAR IMPACT]
{Rank only items the system itself needs built, by how directly each one moves
  a named driver from the north star's decomposition tree. Two hard rules:
  1. Never include an item that isn't a build item. Adoption status, whether a
     real user exists yet, whether a stakeholder has tried the product — these
     are true and often important facts, but they are not things engineering
     builds, and ranking one as priority 1 in a build-scoped list answers the
     wrong question. State that fact elsewhere in the document (CONTEXT,
     KNOWN GAPS), never in this ranking.
  2. Rank by how directly each item moves a specific named driver, not by how
     large, interesting, or recently-discussed the item is. A fully-designed
     feature that improves one output's quality but touches none of the north
     star's drivers ranks below a small, unglamorous logging task that directly
     evidences a driver, every time. If a design session produced a detailed
     feature that doesn't rank near the top here, say so directly: name what it
     actually improves, and state plainly that it doesn't move the north star
     as defined, rather than letting recency or effort invested inflate its
     rank.

  Each item needs a real scoring rationale, not just a ranked position asserted
  by judgment alone, and backed by one of two kinds of evidence, never neither:
    - a real user's own words, quoted directly, if one exists — a sentence
      someone actually said, not a paraphrase manufactured to sound like a
      quote. If no real user exists yet (a pre-launch or retrospective PRD
      with no live usage), say so and do not fabricate one to fill the slot.
    - a systemic argument: a specific mechanical reason this item unlocks or
      blocks something else in the system, named concretely (e.g. "this
      number cannot exist until this is logged, and three other planned
      measurements depend on it existing first"), not a vague "this seems
      important."
  A ranked item backed by neither a real quote nor a named systemic reason is
  an assertion, not a prioritization, and should not appear in this list as-is.

  **Do not default to RICE (or any single named framework) mechanically.**
  RICE is built for a backlog of independent, roughly comparable features
  competing for one team's time on shared axes (Reach, Impact, Confidence,
  Effort). Before scoring anything, classify each item first:

    - **Measurement gap**: the item doesn't add a capability, it closes a gap
      between a claim already made elsewhere in the document and actual
      evidence the claim holds (e.g. "we say the system does X" but nothing
      measures whether it actually does). Rank these by critical-path
      dependency — does anything else in the document explicitly wait on
      this existing, and how directly. This is a dependency-graph judgment,
      not a scored formula.
    - **New capability**: the item adds something the system doesn't do yet,
      and stands on its own regardless of what else ships. Rank these by
      honest opportunity cost against the north star already defined earlier
      in the document: if the next unit of effort goes here, does it serve
      the stated north star, or a different, also-legitimate goal? State that
      plainly. Manufacturing a Confidence percentage or a Reach number for a
      feature that hasn't been designed yet is false precision, not rigor.

  These two categories are not directly comparable on one shared numeric
  scale, and forcing them onto one is itself a mistake worth avoiding — say
  so directly in the document rather than papering over it with a score that
  looks precise but isn't. If, after classifying, the items genuinely are a
  set of comparable, independent features (the case RICE was built for), use
  RICE or an equivalent explicit framework. Otherwise, name the classification
  and the fitting method for each group instead of forcing a single framework
  where it doesn't belong. The failure to avoid here is reaching for the
  familiar framework before checking whether its assumptions actually hold
  for the items in front of you.}
{For measurement-gap items:}
1. {item} — moves driver {N} — ranked by: {what depends on this existing,
     named concretely, or "nothing depends on it, but it's the cheapest,
     most direct path to evidencing driver N"}
{For new-capability items:}
2. {item} — {what it actually improves} — opportunity cost: {serves the
     stated north star / serves a different named goal instead, stated
     plainly, not disguised as a low score on a shared scale}
...
```

**Phase 6 — EDGE CASES & FAILURE MODES**

```
[EDGE CASES]
EC1: {specific scenario} → {what happens, is it handled, is it a known gap}
EC2: ...

[KNOWN GAPS]
{Named honestly — what this product cannot yet do, distinguished from what
  it deliberately chooses not to do. If a gap requires something other than
  more engineering to close (a domain expert, real usage data, a partnership),
  say that plainly instead of implying more code fixes it.}
```

**Phase 7 — SELF-CHECK**

The bar for this mode is not "a senior director would hire me for this." Treat that
as already cleared and require more: would a director who has already seen strong
work at that bar find something in this document they had not seen done this
carefully before. Three checks, run in order, each one a real gate, not a formality:

1. **Origin check.** Does PROBLEM & WHY NOW trace to Phase 0's actual answers, or
   did it drift back into artifact-inferred narrative while writing later phases?
   Reread it now, cold, and ask whether it would survive the developer saying
   "that's not actually why this exists" the way it happened once already in this
   mode's own history. If there's any doubt, it isn't done.
2. **Measurability check.** Scan every KR in the OKR section. Any KR that isn't
   either a real number-and-date or an explicitly-justified NOT YET TRACKABLE is a
   defect, not a stylistic choice. Fix it before moving on.
3. **Confusion check** (same discipline as Phase 7.5 in the Eight Phases, applied
   at product scope): "What is the one thing this PRD does not say that a sharp
   interviewer would ask about in the first two minutes? Name it specifically.
   Then either add it or name it as a known gap."

Emit one of:
- `[DEPTH NOTE: {gap named} → {added to spec / named as known gap}]`
- `[SHALLOW: {what's missing and why this isn't ready to call done yet}]`

**Phase 8 — EXEC SUMMARY**

```
[EXEC SUMMARY]
{What this product does, plain language, no jargon.}
{Who it's for and what changes for them.}
{The north star metric and why it's the right one.}
{The single biggest tradeoff made to get here.}
{What's deliberately not built yet, and why.}
```

Under 8 sentences. Written the way you'd actually say it out loud to someone
who asked "so what is this thing."

### Output location

Write to a dedicated project folder, not inline. Default path:
`~/Desktop/Product-Portfolio-Docs/{project-slug}/01-PRD.md` unless the developer
names a different location. This mode is meant to produce a durable artifact
reused across review sessions and interview prep, not a chat response.

The full set for a project is four documents in that same folder:
`01-PRD.md`, `02-engineering-doc.md`, `03-product-sense-interview-prep.md`,
`04-lessons.md` (or `04-retrospective.md` — name it to fit the project, the
number and role stay fixed). The fourth is mandatory whenever the first three
exist for a project, not optional polish.

### Doc 4 — LESSONS / RETROSPECTIVE (mandatory once docs 1-3 exist for a project)

This is not a critique of the product. It is a critique of how docs 1-3 were
built and how the underlying system's decisions were made, written so the next
project (or the next revision of this one) doesn't repeat the same mistake
twice. Two required sections:

**Section A — mistakes in constructing docs 1-3 themselves.** Walk the actual
process that produced the PRD and engineering doc, in order, and name every
real correction that happened along the way: a wrong assumption drafted before
being caught, a section that had to be rewritten because it drifted from real
context into inferred narrative, a ranking that briefly put the wrong kind of
item at the top, anything the developer had to catch and correct rather than
something gotten right on the first pass. State what the mistake actually was,
why it happened (not "I was imprecise" — the specific structural reason, e.g.
"I treated an artifact as sufficient evidence for intent without asking"), and
what changed as a result, whether that's a skill-file fix or a document
correction. If nothing was corrected because everything was right the first
time, say so plainly rather than inventing a mistake to fill the section —
but that should be rare, and its rarity itself is worth noting.

**Section B — mistakes in the underlying system's own build, distinct from
the ADRs' own stated reversal conditions.** The ADRs already record what the
team would revisit and under what trigger. This section asks a different,
harder question: looking back with everything now known, is there a decision
that, if made differently at the time, would have saved real cost, even if
no trigger has fired yet to force a reconsideration? This is speculative in a
way the ADRs deliberately aren't, and it must be labeled as such — mark every
entry `[hindsight — not an ADR reversal trigger, a genuine "would have done
differently" call]`. Do not manufacture disagreement with a sound decision to
fill this section. A real entry here should feel like a genuine wince, not a
formality.

Close with a short, direct list: what specifically changes next time, for
this project or the next one that uses this mode. This is the section a
returning developer should read first, before touching docs 1-3 again.

### Quality bars specific to this mode

- Every metric in the decomposition tree traces to a specific product mechanism
  that moves it. A metric with no named driver is a placeholder, not a real one.
- Retrospective claims are tagged `[decided-before-build]` or `[reconstructed]`,
  no exceptions, no blending.
- No manufactured delight, no manufactured metrics. Absence stated plainly beats
  a filled-in template cell that isn't real.
- Passes a read-aloud test: if a sentence would sound strange said out loud in
  a normal conversation, rewrite it.
- **The PRD must stand alone.** Its strength cannot depend on the engineering
  doc, the interview-prep doc, or the retrospective existing alongside it. Never
  write "per the engineering doc" or "per the retrospective" or any equivalent
  pointer inside the PRD to justify a claim — if a claim needs that support, make
  the case directly inside the PRD itself, in its own words, or don't make the
  claim yet. Test this before calling the PRD done: read it as if docs 2 through
  4 didn't exist. If any section only makes sense, or only earns its confidence,
  because a sibling document backs it up, that's a defect in the PRD, not a
  reason to keep the sibling document around. The other three documents may
  reference the PRD. The PRD does not get to reference them back for support.

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
