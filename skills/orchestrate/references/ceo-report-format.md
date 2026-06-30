# CEO Report Format — Health Dashboard and Scoring

Used in the REPORT phase. The founder reads this in 60 seconds. Compact by default.

---

## Compact Report (Default)

```
[ORG HEALTH — {YYYY-MM-DD}]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project:      {name}
Progress:     {N}/{M} steps  {▓▓▓▓▓░░░░░} {%}
Health:       {score}/10
Velocity:     FAST | ON TRACK | SLOW | BLOCKED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Last done:    {skill invoked + one-line output}
Blocker:      {none | description}
Next action:  /{skill} {directive} — {what it will do}
Est. finish:  {N days | N weeks | unknown — reason}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Team:
  Active:     {skills run this sprint}
  Pending:    {skills queued}
  Flagged:    {any skill that missed or underperformed — or "none"}
```

---

## Full Report (on request: `orchestrate report full`)

Adds to the compact report:

```
DECISIONS LOG (this sprint):
  D{N}: {decision in one line — active}
  D{M}: {decision in one line — active}

NFR STATUS:
  Covered: {categories with decisions}
  Open:    {any mandatory NFR not yet decided}

KNOWLEDGE GAPS (from /learn):
  {top 1-2 active gaps relevant to current work}

SKILL PERFORMANCE (since last /skill-health):
  {any skills that needed rework or were skipped}

RISK:
  {top 1 risk to current plan — specific, not vague}
```

---

## Health Score Rubric

Score from 1-10. Weighted average of four factors:

### Factor 1: Progress Health (30%)
- 10: On track or ahead of estimated pace
- 7: 1-2 steps behind, recoverable
- 4: More than 2 steps behind, requires scope or deadline adjustment
- 1: Blocked, no progress possible without intervention

### Factor 2: Decision Quality (25%)
- 10: All architectural decisions documented, NFRs covered, no open ambiguities
- 7: 1-2 undocumented decisions or open NFRs
- 4: Multiple undocumented decisions, known gaps not addressed
- 1: Major architectural debt or unresolved blockers

### Factor 3: Code Quality (25%)
- 10: All tests passing, linting clean, no known HIGH+ audit findings
- 7: Tests passing, minor issues
- 4: Failing tests or unresolved MEDIUM+ findings
- 1: Broken build or CRITICAL findings unaddressed

### Factor 4: Knowledge Health (20%)
- 10: Context files current, /learn run, knowledge persisted
- 7: Context files 1-2 sessions behind
- 4: Context significantly stale, re-derivation happening
- 1: No context files, every session starts cold

### Score Interpretation

| Score | Meaning | Action |
|---|---|---|
| 9-10 | Excellent — operating at high efficiency | Continue |
| 7-8 | Good — one area needs attention | Address flagged item |
| 5-6 | Needs attention — visible inefficiency | Pause and fix |
| 3-4 | Poor — multiple issues, slowing delivery | Stop and resolve blockers |
| 1-2 | Critical — org is not functional | Escalate to skill-health full review |

---

## Velocity Definitions

**FAST:** Completing steps faster than estimated. Quality maintained.
**ON TRACK:** Completing steps at estimated pace.
**SLOW:** 20-30% slower than estimated. No blocker, but friction exists.
**BLOCKED:** Cannot advance on the current step without external input or resolution.

---

## Audit Log Connection

At session end (/context-sync FLUSH), the health score from this session's report
is written to `.claude/audit/YYYY-MM.md` so skill-health can trend it over time.

Entry format:
```
### {YYYY-MM-DD}
Session health: {score}/10
Steps completed: {N}
Skills invoked: {list}
First-pass acceptance: {N}/{M} outputs accepted without revision}
Key insight: {one sentence — what was learned or what changed}
```
