# Founder Deployment Guide

*How to run your AI agent team as founder and technical lead.*
*Read once. Reference before each new project or sprint.*

Last updated: 2026-06-27

---

## What You're Running

You have a 10-skill agent team structured like a stealth startup:

| Layer | Team | Skills |
|---|---|---|
| Strategy | Product + Spec | `/pm-review`, `/write-spec` |
| Architecture | Systems + Architect | `/nfr-check`, `/adr`, `/stress-test` |
| Build | Engineering | `/dev-loop`, `/ux-designer` |
| Quality | QA + Security | `/code-review`, `/security-review`, `/verify` |
| Ship | Writing | `/humanize` |
| Learn | Knowledge | `/learn` |
| Ops | Context + Meta | `/context-sync`, `/skill-health`, `/orchestrate` |

You are the founder and CEO. `/orchestrate` is your COO — it plans, routes, and reports.

---

## Scenario A: New Project

### Before you start

Two questions to answer yourself before calling any skill:
1. What does success look like in 6 months? (metric, not vibes)
2. Who is the first real user and what is their most painful day-to-day problem?

If you can't answer both, you're not ready to build. Open a note and write them down first.

---

### Step 1: Establish context

```
/context-sync start
```

This loads your global memory, any project context that exists, and reports what's
already known. If this is day one of a new project, it will note that no L2 context
exists — that's expected.

---

### Step 2: Orchestrate the plan

```
/orchestrate: new project — [one sentence description]
```

Output: rolling 3-step plan with skill routing. You approve each step before it executes.
This is the first checkpoint. Read the plan. If it's wrong, correct it here, not mid-sprint.

---

### Step 3: Product brief

```
/pm-review: [project description]
```

Output: P0/P1/P2 priority brief, "do nothing" alternative, risk assessment.
You are looking for: is the problem real? Is the user specific? Is there a case for NOT building?

Approve or push back on the recommendation before proceeding.

---

### Step 4: Spec the core feature

```
/write-spec: [core feature from pm-review]
```

Output: full PRD — problem, scope, requirements, success metrics, acceptance criteria.
Use the "I'd hire you" check: would a senior director trust this? Is every ambiguity resolved?

**Do not hand this to dev-loop until the spec is clean.** An ambiguous spec produces
ambiguous code.

---

### Step 5: NFR + architecture decisions

For a new project, always run the full NFR check:

```
/nfr-check full: [core feature]
/adr: founding architecture decision — [database, framework, deployment model, etc.]
```

For major architectural decisions, also:
```
/stress-test: [the proposed architecture]
```

These three skills produce the architectural record that every future dev-loop session
will reference. Getting this right here saves hours of refactoring later.

---

### Step 6: Build

```
/dev-loop: [first feature from spec]
```

The dev-loop will pick up the NFR Decision Block and architecture context automatically
if they're loaded. If it doesn't reference them, remind it to.

After each feature: `/code-review`, `/verify`, `/humanize`.

---

### Step 7: End of session

```
/context-sync end
/learn
```

This writes the audit log entry and persists the session's knowledge. Two minutes at
the end of every session. Skipping this is skipping the institutional memory.

---

### Step 8: Track your org health

After every 2-3 sessions or sprints, run:

```
/orchestrate report
```

Output: health score 1-10, progress, blockers, what the team missed.

Every 2-3 weeks:
```
/skill-health
```

Output: which skills are working, which are being skipped, org efficiency score, proposals.

---

## Scenario B: Mid-Project

You have code, a running app, some tests, and some decisions already made.
Some things were done before the skill ecosystem existed.

### What to do first: establish current state

```
/context-sync start
```

Read what it loads. The resume point tells you what the agent team knows about the project.
If L2 context is stale or missing, update it.

Then get the current org health:
```
/orchestrate: check-in — [project name]
```

This orients the COO. It will ask: what was done last session? What's the current goal?
Answer both. You get back: a 3-step plan and a health score based on what's in context.

---

### Filling architectural gaps

The pre-ecosystem decisions (before /adr existed) aren't documented. Don't try to
backfill everything. Pick the 2-3 most consequential decisions that could change
and document those:

```
/adr: retrospective — [the most consequential undocumented decision]
```

Good candidates to backfill:
- Caching strategy (in-process vs. external store)
- Data access enforcement strategy (read-only guarantees, connection isolation)
- UI framework choice (if a framework is central to the architecture)

---

### Adding features mid-project

Same as new project, but:
- Step 1 (`/context-sync`) will load existing L2 context — faster to resume
- `/nfr-check` defaults to quick (4 questions) — skip full ceremony for S/M features
- `/adr` only fires for genuinely new architectural decisions, not incremental adds

For a medium feature (2-5 days):
```
/pm-review: [feature idea]
/write-spec quick: [feature]
/nfr-check: [feature]     ← 4 questions only, ~ 5 min
/dev-loop: [feature]
/code-review
/verify
/humanize
/learn
```

Total overhead before coding starts: ~20 minutes if you've done it a few times.
That 20 minutes eliminates the most common re-work cycles.

---

## What to Approve vs. Let Run

As founder, your job is not to approve every step. It's to hold the gates that matter.

**Always approve:**
- `/orchestrate` plan (before each sprint)
- `/pm-review` recommendation (build vs. defer vs. reject)
- `/write-spec` output (scope and requirements)
- Major `/adr` decisions (anything that forecloses future options)

**Let run without approval:**
- `/nfr-check` quick block (4 questions — just read the output)
- `/dev-loop` individual files (review in `/code-review` instead)
- `/context-sync` flush (routine hygiene)
- `/learn` (accumulates knowledge, no action required)

**Required before session is considered complete:**
- `/context-sync end` — flush to L2/L3, write audit log entry (2 min)
- `/humanize` — final commit message if any commits were made this session
- `/learn` — knowledge capture, quick mode acceptable (5 min)

These three are not optional hygiene — they are what makes the org smarter over time.
A session without them produces good work with no institutional memory.
If nothing was committed and no new knowledge was gained, `/context-sync end` alone is sufficient.

**Periodically review (not per-session):**
- `/skill-health` output (every 2-3 weeks)
- Audit log in `.claude/audit/YYYY-MM.md` (monthly)

---

## Health Signals: What Good Looks Like

| Signal | Healthy | Concerning |
|---|---|---|
| Orchestrate health score | 7-10 | < 6 for two consecutive sessions |
| Audit log | Entry per session | Multiple sessions with no entries |
| NFR blocks | Exist before dev-loop runs | Dev-loop with no NFR reference |
| DECISIONS.md | Updated per architectural decision | Stale, last entry > 2 weeks ago |
| /learn invocations | Every 2-3 sessions | Never |
| Spec quality | Exec brief passes Jajean test | "Build it and we'll see" |

---

## The One-Line Version

**New project:** Orchestrate → PM review → Spec → NFR + ADR → Build → Ship → Learn.

**Mid-project:** Context sync → Orchestrate check-in → Quick NFR → Build → Ship → Learn.

**Weekly:** Orchestrate report. Every 2-3 weeks: Skill health.

---

## Appendix: Skill Quick Reference

| Skill | What you say | What you get |
|---|---|---|
| `/orchestrate` | `/orchestrate: new project — X` | 3-step rolling plan + health score |
| `/pm-review` | `/pm-review: X` | Build/defer/reject + P0/P1/P2 brief |
| `/write-spec` | `/write-spec: X` or `/write-spec quick: X` | Full PRD or quick scope + ACs |
| `/nfr-check` | `/nfr-check: X` (auto-quick for S/M) | NFR Decision Block — 4-25 lines |
| `/adr` | `/adr: decision about X` | DECISIONS.md entry with "why not" |
| `/stress-test` | `/stress-test: design for X` | SURVIVES / NEEDS REVISION / BLOCKED |
| `/dev-loop` | `/dev-loop: implement X` | Code, tests, verified |
| `/humanize` | `/humanize: commit for X` | Ajinkya-voice commit message |
| `/learn` | `/learn` (end of session) | 5-bullet knowledge update |
| `/context-sync` | `/context-sync start` or `/context-sync end` | Context health report or flush |
| `/skill-health` | `/skill-health` | Org efficiency score + skill scorecards |
