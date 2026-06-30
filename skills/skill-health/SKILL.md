---
name: skill-health
description: >
  Meta-skill. Reviews the health of the entire skill ecosystem: which skills are in
  use, which are being skipped and why, what keeps falling through the cracks despite
  the skills existing, and what new skills or updates are needed. Produces a living
  registry update and a health brief. The system that examines itself. Triggers on:
  "review the skill ecosystem", "what skills do we have", "what's missing from our
  process", "update the skill registry", after any session where a gap was observed
  despite skills being in place, or on a periodic review cadence (every 2-3 weeks).
---

# skill-health — Skill Ecosystem Meta-Skill

A self-examination skill that reviews the engineering team's own processes and tools.
The skill ecosystem is a living system — skills become stale, gaps emerge from new
work, and the workflows between skills need adjustment over time.

This skill's job: make sure the team (the skills) stays as sharp as the work demands.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full health review — inventory, usage, gaps, proposals |
| `inventory` | List all skills with status — no gap analysis |
| `gap: [observed miss]` | Log a specific gap that slipped through despite skills being in place |
| `update registry` | Update SKILL-REGISTRY.md with current state |
| `propose: [skill idea]` | Evaluate a new skill proposal against the hiring bar |
| `check: [skill name]` | Deep review of one specific skill's quality and completeness |

---

## Context Capture (Always First)

```
TRIGGER:         [what prompted this review — periodic | observed gap | post-incident | new project]
RECENT SESSIONS: [brief description of work done since last review]
OBSERVED GAPS:   [anything that slipped through despite skills being in place]
NEW REQUIREMENTS: [any new types of work that existing skills don't cover]
```

---

## The Seven Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — AUDIT LOG READ

Read `.claude/audit/YYYY-MM.md` for the current and prior month.
Extract per-session data: health scores, skills invoked, first-pass acceptance rates, gaps flagged.

If no audit log exists: note this as a gap. Proceed with qualitative assessment only.

Build a summary table:
```
[AUDIT SUMMARY]
Sessions reviewed: {N}
Avg health score:  {X}/10
Trend:             IMPROVING | STABLE | DEGRADING

Per-skill invocation:
  {skill}: invoked {N} times, {M} gaps flagged
  ...

First-pass acceptance rate: {N}/{M} ({%}) outputs accepted without revision
Most common gap: {which skill missed / what fell through}
```

---

### Phase 2 — INVENTORY

List all skills with their performance grade derived from the audit log.

```
[SKILL SCORECARD]
Skill           Grade   Invocation   Gap Rate   Status
/dev-loop       A/B/C/D  HIGH/MED/LOW  LOW/MED/HIGH  HEALTHY/REVIEW/UPDATE
/nfr-check      ...
...
```

Grade rubric:
- **A**: Invoked correctly, high first-pass acceptance, zero or rare gap
- **B**: Mostly correct, occasional revision needed, minor gaps
- **C**: Inconsistent invocation or frequent rework — needs update
- **D**: Frequently skipped when needed, high gap rate — needs significant revision or replacement

---

### Phase 3 — USAGE ANALYSIS

From audit data, assess invocation discipline:

**Under-invocation:** Skills skipped when they should have run.
**Skip patterns:** Why they were skipped — is it the trigger description, ceremony, or genuine inapplicability?
**Over-invocation:** Skills invoked when unnecessary, adding friction.

```
[USAGE ANALYSIS]
Under-invoked: {skill} — skipped in {N}/{M} sessions where it should have run
  Likely reason: {trigger not clear | too much ceremony | founder bypassed}
Skip pattern:  {specific scenario where bypass happened}
Over-invoked:  {skill} — invoked {N} times unnecessarily
```

---

### Phase 4 — GAP ANALYSIS

Gaps observed in audit log entries ("Gap: ..." field) plus qualitative assessment.

```
[GAP ANALYSIS]
[GAP: SEVERITY] {description}
  Type:     between-skill | within-skill | new-work
  Evidence: {audit date + session description where observed}
  Fix:      update {skill} | new skill: {name} | process change
```

---

### Phase 5 — ORG EFFICIENCY SCORE

Quantified rating of how efficiently the agentic org is functioning.

```
[ORG EFFICIENCY REPORT]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall score:      {X}/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Skill utilisation:  {%} of skills invoked correctly
First-pass rate:    {%} outputs accepted without revision
Gap catch rate:     {%} of potential gaps caught by skills vs. slipping through
Decision quality:   {all ADRs filed | gaps in decision record}
Knowledge health:   {/learn run consistently | gaps in knowledge base}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
vs. last review:    {+N | -N | no change}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Top strength:       {what's working well}
Top priority fix:   {single most impactful improvement}
```

Score interpretation: see `/orchestrate/references/ceo-report-format.md` for the rubric.
The skill-health score should align with the orchestrate health score — if they diverge, flag it.

---

### Phase 6 — PROPOSALS

For each GAP or C/D graded skill: a concrete proposal.

**New skill:**
```
[NEW SKILL: {name}]
Gap addressed:      {which gap}
Hiring bar test:    Does this do something no existing skill does? {yes/no + reason}
Scope:              {one sentence}
Priority:           HIGH | MEDIUM | LOW
```

**Skill update:**
```
[UPDATE: {skill}]
Current grade:  {C or D}
Gap:            {specific miss}
Change:         {targeted, specific}
Priority:       HIGH | MEDIUM | LOW
```

---

### Phase 7 — REGISTRY UPDATE

Update `SKILL-REGISTRY.md` change log and per-skill health status.
Append to `.claude/audit/YYYY-MM.md`:
```
### SKILL-HEALTH REVIEW — {YYYY-MM-DD}
Org score: {X}/10 (prev: {Y}/10)
Key finding: {one sentence}
Actions: {list of updates and new skills approved}
```

---

## Quality Bars (Non-Negotiable)

- **A gap is only a gap if it slipped through despite the skills existing.** Pre-skill issues are not gap evidence.
- **Every proposal passes the hiring bar test.** A proposed skill must do something no existing skill does.
- **The registry must stay scannable.** Entries become verbose or the index becomes long → the registry becomes useless.
- **Updates are specific.** "Improve dev-loop" is not a proposal. "Add NFR gate check at UNDERSTAND phase start" is.

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Self-awareness test**: It can identify its own weaknesses — what does /skill-health tend to miss?
2. **False negative test**: It doesn't flag healthy skills as degraded because they're invoked rarely (rare invocation can be correct behavior for a gate-style skill like /adr).
3. **New-skill bar**: When evaluating a new skill proposal, it asks "does this do something NO OTHER SKILL does?" and refuses duplicative proposals.
4. **Registry hygiene**: After a review, SKILL-REGISTRY.md is cleaner and more accurate than before — not longer.

---

## Reference Files

| File | When to read |
|------|-------------|
| `../SKILL-REGISTRY.md` | INVENTORY phase — the living registry |

---

## Example Flows

**Periodic review:**
> "Review the skill ecosystem."

INVENTORY → USAGE (noting /nfr-check has not been invoked in 3 sessions despite new features built) → GAP (caching slipped through before /nfr-check existed — confirmed fixed) → PROPOSALS (none this cycle) → REGISTRY UPDATE

**Post-observed gap:**
> "gap: we built a new endpoint without checking security surface"

INVENTORY (skip) → USAGE (skip) → GAP (/nfr-check section 10 covers security surface, but was not invoked) → PROPOSALS (update /nfr-check: add security surface to mandatory list for new endpoints) → REGISTRY UPDATE
