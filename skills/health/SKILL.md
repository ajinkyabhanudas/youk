---
name: health
description: >
  Report youk's current org_score, top findings, and pending proposal count.
  Read-only health check — does not close the session or trigger improvements.
  Triggers on: "/health", "how are we doing", "org health", "check health",
  "what's the org score", "show me the health", "system health check".
---

# health — youk Org Health Check

A read-only snapshot of youk's current state. Run after any session to see
whether compounding is happening.

---

## Execution

Call `youk-core.self_heal()`. Output this card:

```
org_score: {n}/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Findings
  1. {findings[0]}
  2. {findings[1]}      ← omit if fewer than 2

{IF improvement_velocity.verdict is "STEADY" for >= 3 cycles}
  Score unchanged for {N} cycles — run /audit to check for project-type skill gaps.
{END IF}

{IF close_cluster_rate == 0 for >= 3 sessions}
  Sessions not closing — check if your project has .claude/skills/done overriding youk's.
  Use 'ship it' phrase as fallback if /done is overridden.
{END IF}

Pending proposals: {count}   ← omit line if 0

{IF org_score < 6}
Run /improve to apply queued skill improvements.
{END IF}
```

Do not call session_end. Do not suggest next tasks. The card is the output — wait
for the user to direct.

---

## What the score means

| Score | State |
|---|---|
| 8–10 | Compounding well — skills firing, sessions closing properly |
| 5–7 | Partial — some skills skipped or sessions not closing with /done |
| < 5 | Stale — capability skills haven't fired recently; run /improve |

The primary driver is `skill_invocation_rate` (weight 2×) — did capability skills
(nfr-check, code-review, dev-loop, learn) run this session?
`close_cluster_rate` (weight 0.5×) — did /done run?
