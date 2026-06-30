---
name: orchestrate
description: >
  Project orchestrator and CEO reporting layer. The founding-layer skill that routes work
  to the right skills in the right order. Takes a goal and produces a rolling plan —
  next step only, approved before advancing. Reports org health upward in a format a
  founder can read in 60 seconds: progress, blockers, health score, next action. Does not
  do implementation work itself — it coordinates, plans, and reports. Triggers on: any
  new project, any "what should we do next", any check-in on current project state, and
  at the start of every session when there is active work in flight.
---

# orchestrate — Project Orchestrator

The project management and CEO reporting layer. Routes work to the right skills,
tracks progress, surfaces blockers, and gives the founder a clear view of how the
org is performing without requiring them to read every artifact.

Rolling plan: produces the next step, not the full waterfall. The founder approves
before the next step runs. This keeps the plan agile without losing visibility.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| `new: [goal]` | New project kickoff — intake, plan first step, set up context |
| `next` | What is the next step given current state? |
| `report` | CEO health report — current state, progress, blockers, score |
| `check: [concern]` | Assess a specific concern against the plan |
| `unblock: [blocker]` | Given a blocker, what are the options? |
| *(no directive)* | Read current state and produce report + next step |

---

## Context Capture (Always First)

```
PROJECT:     [name — or "new" if starting fresh]
GOAL:        [one sentence — what done looks like]
USER:        [who benefits — specific person]
DEADLINE:    [hard date or "none"]
CONSTRAINTS: [team size, tech stack, scope limits]
CURRENT STATE: [read from .claude/prd-status.md or "new project"]
```

For a new project: ask for GOAL, USER, DEADLINE, CONSTRAINTS.
For an existing project: read `.claude/prd-status.md` — do not ask the user to re-explain.

---

## The Five Phases

Each phase begins with: `[PHASE: NAME]`

---

### Phase 1 — INTAKE

For new projects only. Build the project context that all other skills will reference.

1. Restate the goal as a one-sentence success condition: "Done when [user] can [do X]."
2. Identify project type — read `references/project-type-playbooks.md` for the matching playbook.
3. Identify what already exists: code, decisions, context files, prior sessions.
4. State the 3 most important constraints.
5. Create the L2 context stub (`.claude/[project]-context.md`) if it doesn't exist.

Emit:
```
[PROJECT BRIEF]
Name:       {project name}
Goal:       {one sentence success condition}
Type:       {new feature | new project | bug fix | research spike | handover}
Playbook:   {which playbook from references/}
Constraints: {top 3}
First step: {name of first skill to invoke}
```

---

### Phase 2 — PLAN

Produce the next 1-3 steps only. Not the full project plan — just enough to act on now.

Read the relevant section of `references/project-type-playbooks.md` for the default
skill sequence for this project type. Then adjust based on:
- What's already been done (from prd-status.md)
- What gaps exist (from skill-health review if recent)
- What the current blocker is (if any)

Emit:
```
[ROLLING PLAN]
Step N (now):   /[skill] — {one sentence: what this skill will do and what its output is}
Step N+1 (next): /[skill] — {pending approval of step N}
Step N+2 (horizon): /[skill] — {pending approval of steps N and N+1}

Approval gate: {what the founder reviews before step N+1 begins}
```

---

### Phase 3 — BRIEF

For the current step: generate the context the invoked skill needs.

This is the handoff package — the skill should be able to run from a cold start using
only this brief plus the project context files.

```
[SKILL BRIEF: /{skill name}]
Invocation: /[skill] [directive if any]
Context to load: {L2 file path, relevant sections}
Key inputs: {what this skill needs to know — not already in L2}
Expected output: {what this skill should produce}
Acceptance bar: {what "good" looks like for the founder to approve}
```

---

### Phase 4 — CHECKPOINT

After a skill produces output, assess before advancing:

```
[CHECKPOINT]
Output quality:  ACCEPTED | NEEDS REVISION | BLOCKED
If NEEDS REVISION: {specific gap — one sentence}
If BLOCKED: {what is blocking and what options exist}
If ACCEPTED: next step is {skill name} — proceed? [Y/N]
```

The founder answers Y/N. This is the approval gate.

If BLOCKED, emit options:
```
[UNBLOCK OPTIONS]
Option A: {approach} — {trade-off}
Option B: {approach} — {trade-off}
Recommendation: {A or B} — {one-sentence reason}
```

---

### Phase 5 — REPORT

CEO health report. Read on any `report` invocation and at the start of every session.
Read `references/ceo-report-format.md` for the full format.

Compact by default. Full detail only if founder asks.

```
[ORG HEALTH — {date}]
Project:     {name}
Progress:    {N}/{M} steps ({%})
Health:      {score}/10  [{what's driving the score}]
Velocity:    FAST | ON TRACK | SLOW | BLOCKED
Blocker:     {none | one-line description}
Last done:   {what was completed most recently}
Next action: {the one thing to do next — skill + directive}
Est. finish: {rough — days/weeks/unknown}

Team utilisation:
  Active:  {skills used this sprint}
  Idle:    {skills in roster but not yet needed}
  Flagged: {any skill that underperformed or was skipped when it should have run}
```

Score interpretation: 8-10 clean, 6-7 one concern, 4-5 needs attention, <4 escalate.

---

## Quality Bars

- **Never produce a full waterfall plan.** The plan has 3 steps maximum visible at once.
- **The report is readable in 60 seconds.** If the founder needs to read more than the compact report to understand project state, the report failed.
- **Blockers surface immediately.** A blocked step never silently converts to "skipped."
- **Approval gates are explicit.** The founder always knows what they're approving and what comes next.
- **Context files are the source of truth.** Never ask the founder to re-explain state that is already in prd-status.md or canopy-context.md.

---

## Hiring Validation

1. **Agility test**: Given a mid-project change in requirements, it revises the rolling plan without starting over or producing a full new waterfall.
2. **Report test**: The CEO report can be read in under 60 seconds and produces a clear next action.
3. **Blocker test**: When a skill produces a BLOCKED output, it surfaces options immediately rather than stalling.
4. **Cold start test**: Given only prd-status.md and canopy-context.md, it reconstructs current state and produces the correct next step without asking the founder to re-explain.
5. **Handoff test**: The SKILL BRIEF it produces gives a cold-start skill enough context to run without further input.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/project-type-playbooks.md` | INTAKE + PLAN — skill sequence by project type |
| `references/ceo-report-format.md` | REPORT — full health report format and scoring rubric |
