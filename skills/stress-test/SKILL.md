---
name: stress-test
description: >
  Red team skill. Takes any plan, architecture, design decision, or proposed implementation
  and attacks it from three independent angles before commitment. Spawns three agents, each
  assigned a distinct failure mode lens — scale, edge cases, and hidden assumptions — and
  synthesizes their findings into a SURVIVES / NEEDS REVISION / BLOCKED verdict. The goal
  is not to find reasons to reject good ideas, but to find the specific conditions under
  which good ideas fail, so those conditions can be addressed before they reach production.
  Triggers on: "does this design hold up?", "stress test this", "challenge this plan",
  "what could go wrong with", any major architectural decision before commitment, any
  /adr DECIDE phase output, and any /pm-review RECOMMEND output.
---

# stress-test — Red Team Skill

A three-agent attack skill that pressure-tests plans, designs, and decisions before
they are committed. Inspired by pre-mortem methodology and adversarial ML evaluation:
the most effective way to find a plan's weaknesses is to assign people specifically
tasked with finding them.

This skill is not a debate — it is a structured attack. The agents are not looking
for a "balanced view." They are looking for the specific, concrete scenario in which
the plan fails. That specificity is what makes findings actionable.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full red team: all three agents, full synthesis, verdict |
| `quick` | Abbreviated: top attack vector per agent only, no deep synthesis |
| `scale only` | Agent A (scale) only |
| `edge only` | Agent B (edge cases) only |
| `assumptions only` | Agent C (hidden assumptions) only |
| `target: [specific concern]` | All three agents focused on one specific risk |
| `retest` | Given a revised plan that addressed prior findings, re-run the attack |

---

## Context Capture (Always First)

Before any phase, extract or infer:

```
SUBJECT:         [what is being stress-tested — plan / design / decision / code design]
SUBJECT SUMMARY: [one paragraph describing the subject — enough for agents to attack it independently]
SCOPE:           [module / feature / system / cross-project]
CONSTRAINTS:     [what cannot be changed — these are walls, not attack surfaces]
PRIOR FINDINGS:  [any previous stress-test findings being addressed — for retest mode]
STAKES:          [low / medium / high — what breaks if this plan fails?]
```

If STAKES is high (system-wide, production-facing, irreversible), all three agents
run at full depth. If STAKES is low, `quick` mode is appropriate.

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — SCOPE

State what is being attacked and what a successful attack looks like:
1. Restate the subject in one sentence
2. Identify what "failure" means for this subject (produces wrong output / crashes / scales poorly / creates security risk / is unmaintainable)
3. State the three attack angles that will be used
4. Identify any parts of the subject that are explicitly OUT OF SCOPE (constraints, already-decided)

---

### Phase 2 — ATTACK

Three agents reason independently. **Critical rule: agents do not see each other's
output during this phase.** Each agent receives only the SCOPE and SUBJECT SUMMARY.

Read `references/attack-vectors.md` before assigning each agent their lens.

---

**Agent A — Scale & Load**

Lens: What happens to this design at 10x, 100x, and 1000x the assumed load?

Areas to probe:
- Does the caching strategy break under concurrent cache misses? (thundering herd)
- Does the database query pattern produce N+1 problems at scale?
- Does the retry logic create load amplification at failure time?
- Does the queue / thread model exhaust resources under sustained load?
- Does the data structure choice become a bottleneck with large inputs?
- What is the worst-case latency? Is it bounded?

Output format:
```
[AGENT A: SCALE]
Attack surface: {what was targeted}
Finding {n}:
  Scenario: {specific load scenario, not hypothetical — "when 100 users query simultaneously"}
  Failure mode: {what breaks and how}
  Severity: CRITICAL | HIGH | MEDIUM | LOW
  Evidence: {what in the current design causes this}
```

---

**Agent B — Edge Cases & Error Paths**

Lens: What inputs, states, or sequences of events were not considered?

Areas to probe:
- What happens with empty inputs, zero-row results, null values?
- What happens when an external dependency returns a partial response?
- What happens when the operation is interrupted mid-way?
- What happens when the input is valid but semantically unexpected? (e.g., a query that returns 50,000 rows)
- What happens when two operations happen in an unexpected order?
- Are all error types caught and handled, or only the expected ones?
- What is the behavior on the first run when caches and state are empty?

Output format:
```
[AGENT B: EDGE CASES]
Attack surface: {what was targeted}
Finding {n}:
  Scenario: {specific input/state/sequence — concrete, not "some cases"}
  Failure mode: {what breaks and how}
  Severity: CRITICAL | HIGH | MEDIUM | LOW
  Evidence: {what in the current design fails to handle this}
```

---

**Agent C — Hidden Assumptions**

Lens: What does this design assume that is not explicitly stated, and which assumptions
could be wrong?

Read `references/assumption-taxonomy.md` for categories of hidden assumptions.

Areas to probe:
- What does this design assume about the user's behavior?
- What does this design assume about the infrastructure it runs on?
- What does this design assume about the data it processes?
- What does this design assume about the team maintaining it?
- What does this design assume about the external services it calls?
- What does this design assume about the time horizon? (built for now vs. built to last)
- What would change if any of these assumptions were wrong?

Output format:
```
[AGENT C: ASSUMPTIONS]
Attack surface: {what was targeted}
Finding {n}:
  Assumption: {the hidden assumption, stated explicitly}
  Risk if wrong: {what breaks when the assumption doesn't hold}
  Probability: HIGH | MEDIUM | LOW (how likely is this assumption to fail?)
  Evidence: {what in the design depends on this assumption}
```

---

### Phase 3 — TRIAGE

Synthesize all findings from the three agents:

1. Deduplicate: merge findings that attack the same root cause from different angles
2. Rank by severity: CRITICAL first
3. Identify compound failures: where one finding makes another finding worse
4. Identify root causes: sometimes five findings trace back to one root design choice

Emit a ranked finding list:
```
[TRIAGE]
Total findings: {N} ({n} CRITICAL, {n} HIGH, {n} MEDIUM, {n} LOW)

CRITICAL findings:
  {Finding summary — agent + scenario + failure mode in one line}
  Root cause: {if multiple findings share a root, name it once}

HIGH findings:
  {same format}

MEDIUM findings:
  {same format}

LOW findings:
  {same format}

Compound failures: {any pairs of findings where both occurring together is worse than either alone}
```

---

### Phase 4 — VERDICT

Based on the triage, issue a verdict:

| Verdict | Condition |
|---|---|
| **SURVIVES** | Zero CRITICAL, ≤2 HIGH findings, no compound failures |
| **NEEDS REVISION** | Any HIGH finding, or compound failure involving ≥2 MEDIUM findings |
| **BLOCKED** | Any CRITICAL finding |

For NEEDS REVISION and BLOCKED, emit a remediation list:

```
[REMEDIATION]
For each CRITICAL or HIGH finding:
  Finding: {summary}
  Recommended fix: {specific, implementable change}
  Alternative: {if there are multiple ways to address this}
  Impact on plan: {minor tweak | significant redesign | rethink the approach}
```

---

### Phase 5 — RETEST (conditional)

If the subject is revised based on remediation suggestions, run a focused retest:
1. For each CRITICAL/HIGH finding from the original run: does the revision address it?
2. Did the revision introduce any new attack surfaces?
3. Issue a new verdict.

> Retest is faster than the full attack — agents focus only on the changed areas and
> prior findings, not the full surface.

---

## Quality Bars (Non-Negotiable)

- **Findings must be specific.** "This could fail under load" is not a finding. "When 50 simultaneous users submit queries, the thread pool exhausts at 10 threads and new requests queue indefinitely" is a finding.
- **Agents must be independent.** If the three agents produce identical findings, the attack was not independent. Revise.
- **SURVIVES does not mean "perfect."** It means "no CRITICAL or HIGH findings in this pass." LOW findings still get documented.
- **BLOCKED is not a rejection.** It means "fix the CRITICAL issue first, then re-run." The plan may still be the right plan.
- **Remediation must be concrete.** "Improve the error handling" is not remediation. "Add a 30-second timeout with exponential backoff (max 3 retries) to the LLM call in query/loop.py" is remediation.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Independence test**: Agent A and Agent B find different issues on the same plan. They cannot both produce "the cache could be a bottleneck" as their top finding — they attack from different angles.
2. **Specificity test**: Every CRITICAL finding includes a concrete scenario (not "in some cases"). "When the LLM API returns 429 during peak load and the retry loop runs 3 times, the total request timeout becomes 3×60s = 180s, blocking the Gradio thread" passes. "The retry logic could be slow" fails.
3. **Compound failure test**: On a plan with both a retry issue and a threading issue, the triage phase identifies that these compound (retry amplifies thread exhaustion).
4. **False positive discipline**: On a well-designed plan with no real issues, it produces a SURVIVES verdict with only LOW findings — it doesn't invent problems to seem thorough.
5. **Actionable remediation**: Every HIGH+ finding produces a remediation that names a specific file/module/line range and a specific change.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/attack-vectors.md` | ATTACK phase — before assigning agents |
| `references/assumption-taxonomy.md` | Agent C — categories of hidden assumptions |
| `references/scale-patterns.md` | Agent A — how scale changes system behavior |

---

## Example Flows

**Stress testing a caching design:**
> "Stress test the canopy cache design: SHA-256 key, 24h TTL, LRU eviction, JSON file storage."

SCOPE → ATTACK (Agent A: concurrent cache misses → thundering herd to LLM API; Agent B: what if cache file is corrupted? what if TTL=0? Agent C: assumes single-process — what if Docker runs two instances?) → TRIAGE → VERDICT: NEEDS REVISION (thundering herd is HIGH) → REMEDIATION (add cache lock or singleflight pattern)

**Pre-commit architecture review:**
> "Stress test the query loop design before we ship v1."

SCOPE → ATTACK (all three agents at full depth) → TRIAGE → VERDICT → REMEDIATION list fed into /nfr-check and /adr

**Quick check on a small change:**
> "Quick stress test: adding a sleep(0.1) between retries instead of exponential backoff."

SCOPE → ATTACK (quick mode: top finding per agent) → TRIAGE → VERDICT → REMEDIATION
