---
name: surface-options
rationale_why: "A single confident answer to an open question is a silent choice the developer never got to make. Naming the real options — and their real costs — is what actually sharpens judgment, not just resolves the request."
description: >
  Fires on ambiguous, open-ended, or judgment-call requests where a single answer would
  flatten a real decision — "how should we approach X", "what do you think about Y",
  "what's the best way to Z", naming choices, structuring something with no single
  right shape, or any request where a competent senior engineer would say "it depends."
  Instead of picking silently, surfaces 2-4 materially different framings with their
  costs, plus one explicit recommendation. Triggers on: exploratory questions ("what
  could we do about X", "how should we approach this", "what do you think"), any
  request with an unstated but real fork in direction, ADR-adjacent decisions too
  small to warrant a full ADR. Does NOT trigger on: requests with only one reasonable
  approach, tasks where the user has already stated their chosen direction, pure
  factual/lookup questions, XS/S mechanical tasks. Distinct from challenge (which
  attacks a direction already chosen) and adr (which records a decision already made) —
  surface-options runs BEFORE a direction exists, when the fork itself hasn't been named.
fast-path: |
  If the request has exactly one reasonable approach (no real fork — a typo fix, a
  named library call, a fully-specified spec) → skip straight to answering. Naming
  fake options where none exist is worse than naming none.
auto-skip: |
  Skip if the user already stated their chosen approach this session ("let's use X"),
  if this exact fork was already surfaced and resolved in the last 5 exchanges, or if
  route_task sized the task M+ (challenge/nfr-check own the direction gate for M+ —
  surface-options only owns S-tier and pre-route_task exploratory questions; never
  double-surface the same fork through two skills). Also skip — full OFFER — if
  mid-dev-loop with an active phase: surface the fork as a one-line flag inside that
  phase's compact summary instead, and only run a full OFFER between phases or before
  dev-loop starts. Cap firing at roughly one full OFFER per 3 exchanges unless STAKES
  is high — a skill that interrupts every exchange trains the user to skim past it.
---

# surface-options — Decision Surface Skill

Picking silently is a service until it isn't. When a request has one right answer,
answering it directly is correct — asking would just be noise. But when a request
has a real fork — a judgment call with more than one defensible path — collapsing it
into a single confident answer removes the developer's chance to weigh in on their
own decision. This skill exists to catch that second case and hand the fork back,
named and costed, instead of resolved in silence.

Not a hedge. A recommendation is mandatory every time this fires — "here are some
options" with no pick is abdication, not nuance.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full: DETECT → SHAPE → OFFER, 2-4 options with recommendation |
| `quick` | DETECT → OFFER only — top 2 options, one-line tradeoff each, no SHAPE elaboration |
| `options only` | Enumerate options without a recommendation — only when the user explicitly asked to decide themselves |
| `deepen: [option]` | User picked one surfaced option — expand it into a normal answer/plan, drop the others |
| `why not: [option]` | User wants the rejected-option reasoning made explicit — one paragraph, cite the cost that ruled it out |

---

## Context Capture (Always First)

```
REQUEST:        [the user's question or ask, verbatim or paraphrased]
REAL_FORK:      [the actual axis of disagreement a competent engineer would have — name it in one clause]
STAKES:         [low / medium / high — medium and low share the same OFFER behavior, only high changes it]
ALREADY_STATED: [any constraint or preference the user already gave this session — these narrow options, they don't get re-offered as options]
IN_DEV_LOOP:    [is an active dev-loop phase in progress? if yes, this fires as a one-line flag inside that phase's output, not a full OFFER]
RECENT_FIRES:   [how many full OFFERs in the last 3 exchanges — 1+ means lean toward fast-path or fold this fork into the current answer instead of a new OFFER]
```

If REAL_FORK cannot be named in one clause, there isn't one — take the fast-path
and answer directly instead of manufacturing options.

---

## Phases

### Phase 1 — DETECT

1. Ask: does this request have more than one defensible approach, or exactly one?
2. If exactly one (a named tool, a fully-specified request, a mechanical task) → fast-path, skip to a direct answer.
3. If genuinely open, name REAL_FORK — the specific axis the options will differ on (e.g. "build vs. buy", "consistency vs. latency", "one skill vs. a mode inside an existing one").
4. Falsifiability check: state one concrete scenario where each side of REAL_FORK would actually win. If only one side has a real winning scenario, this was a fast-path case wearing a fork's clothes — answer directly instead.
5. Check STAKES. Low/medium stakes + quick invocation → cap at 2 options. High stakes → allow up to 4, no more.
6. Check IN_DEV_LOOP and RECENT_FIRES per auto-skip — downgrade to a one-line flag or fold into the current answer if either applies.

> Compact phase summary: "Fork identified: {REAL_FORK}. Stakes: {STAKES}. Option count target: {N}."

### Phase 2 — SHAPE

1. Generate 2-4 options that differ on REAL_FORK, not on cosmetic details. Two options that share the same tradeoff profile are one option, not two.
2. For each option, state: what it is (one clause), what it costs (the real tradeoff, not a strawman downside), and when it's the right call.
3. Discard any option that has no realistic scenario where it wins — that's not an option, it's a distractor.
4. If an option itself splits into sub-options mid-generation, that split is evidence STAKES was undercounted for that branch — collapse it back to the outer fork, note the nested split as a one-line caveat on that option's cost line, and do not expand past 4 top-level options.
5. Pick a recommendation. State the one factor that tips it — not "it depends," the actual thing that made the call.

> Compact phase summary: "{N} options shaped, each with a distinct cost. Recommendation: {option} because {tipping factor}."

### Phase 3 — OFFER

1. Match output length to STAKES: low/medium stakes → 2-3 sentences total, one line per option. High stakes → structured list acceptable, but every option still gets exactly one tradeoff line, not a paragraph.
2. State the recommendation and its tipping factor plainly, before or after the list — never buried.
3. Frame it as redirectable, not a question blocking progress: state the pick and proceed, don't wait for the user to choose, for low/medium stakes.
4. If STAKES is high (irreversible, cross-system, or explicitly asked "what do you think"): stop and wait for the user's steer instead of proceeding on the recommendation. This is the one place efficiency yields to the skill's actual purpose — a genuinely high-stakes fork is exactly where the developer needs to be the one to clear it, not have it resolved for them.

> Compact phase summary: "Options offered, recommendation stated. {Proceeding on recommendation | Waiting for steer} based on STAKES."

---

## Quality Bars (Non-Negotiable)

- **No option without a cost:** every option lists what it gives up, not just what it gains. An option with no stated downside is marketing, not analysis.
- **No abdication:** a recommendation is mandatory whenever this fires in default mode. "Here are some options" with nothing picked is not a valid OFFER output.
- **Material difference only:** options must differ on REAL_FORK. Two options that differ only in naming or phrasing collapse to one — SHAPE must catch this before OFFER.
- **Fork or nothing:** if DETECT cannot name a one-clause REAL_FORK, the skill does not fire — it answers directly. Manufacturing a fork where none exists trains the user to distrust every future "here are your options."
- **Length matches stakes:** low-stakes forks get 2-3 sentences, not a five-option table. Over-ceremony on a small call is its own failure mode.
- **Redirectable, not blocking:** default posture is "here's my pick and why, redirect me if wrong" — not "please choose," except when STAKES is genuinely high.
- **Falsifiable fork, not a fluent one:** naming a fork in one clause is not enough — DETECT must state a concrete winning scenario for each side. If only one side has one, it wasn't a fork.
- **No silent under-firing:** the fast-path is for genuine single-approach requests, not an escape hatch from doing SHAPE work on a real fork. If DETECT's falsifiability check produces two real winning scenarios, it does not get waved through as a fast-path.
- **Respect the interruption budget:** at most one full OFFER per ~3 exchanges outside high-stakes cases, and never a full OFFER mid-dev-loop-phase — a one-line flag instead. A skill that interrupts constantly gets skimmed past, defeating its own purpose.

**Hiring Validation** — does this skill run for real, or go through the motions?
1. Given "what do you think about X" with a genuine fork, does it name the fork explicitly before listing options — or does it jump straight to a listicle with no shared axis?
2. Given a request with exactly one reasonable approach, does it fast-path to a direct answer — or does it manufacture two fake options to look thorough?
3. Does every option carry a real cost, or does one option get a strawman downside so the recommendation looks obviously correct?
4. On a low-stakes exploratory question, is the output 2-3 sentences — or does it produce a five-paragraph decision memo for a throwaway call?
5. Does OFFER ever end without a stated recommendation in default mode? (Should never happen.)
6. Given a request mid-dev-loop with a real embedded fork, does it downgrade to a one-line flag instead of a full interrupting OFFER?
7. Across a session, does it ever fire a full OFFER on 3+ consecutive exchanges — or does the interruption budget actually throttle it?

---

## Example Flows

**Low-stakes exploratory question:**
> "what could we do about the flaky test in the payments suite?"

DETECT: fork = retry-the-flake vs. fix-the-race-condition. STAKES: low (test-only, reversible).
SHAPE: option A (add retry) — fast, costs nothing but leaves the real bug live; option B (fix the race) — slower, actually resolves it.
OFFER (2-3 sentences): "This is either a quick retry-wrap or an actual race-condition fix — retry is faster but leaves the bug live, fix is slower but real. I'd fix it since it's a payments path; flag if you want the fast patch instead."

**High-stakes architectural fork:**
> "how should we handle the cache invalidation for the new query-plan cache?"

DETECT: fork = TTL-based vs. event-driven invalidation. STAKES: high (cross-system, hard to reverse once callers depend on the semantics).
SHAPE: 3 options (TTL-only, event-driven, hybrid) each with cost (staleness window vs. plumbing complexity vs. both).
OFFER: structured list, one tradeoff line each, recommendation stated with tipping factor, then STOP and wait — stakes are high enough that proceeding without a steer is the wrong call.

**Fast-path (no real fork):**
> "add a null check before this Redis call"

DETECT: exactly one reasonable approach. Fast-path — no options manufactured, direct answer given.

**`deepen:` follow-up:**
> "deepen: the event-driven one"

Previous OFFER surfaced 3 options. User picked one. Skill drops the other two and expands the chosen option into a normal implementation-ready answer — no re-litigation of the fork.
