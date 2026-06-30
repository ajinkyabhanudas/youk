# Project Type Playbooks — Default Skill Sequences

Used in INTAKE and PLAN phases. Each playbook is the default skill sequence for a
project type. Adjust based on what's already done and what the current state is.

---

## New Project (Greenfield)

Starting a new product or tool from scratch.

**Default sequence:**
```
1. /pm-review          → Is this the right thing to build? Who is it for?
2. /write-spec         → PRD: what exactly are we building?
3. /nfr-check          → What are the non-functional requirements?
4. /adr                → What architectural decisions need documenting?
5. /stress-test        → Does the design hold up?
6. /context-sync       → Set up L2 project context file
7. /dev-loop           → Implement (per feature, repeats)
8. /ux-designer        → If user-facing: design UI states
9. /code-review        → Quality gate
10. /verify            → Confirm live behavior
11. /humanize          → Commits and documentation
12. /learn             → Knowledge capture
```

**Checkpoints (founder approves before advancing):**
- After /write-spec: "Does this spec match what you want to build?"
- After /adr + /stress-test: "Is the architecture sound?"
- After each /dev-loop iteration: "Does this feature work as specified?"

---

## New Feature (Existing Project)

Adding a significant capability to an existing codebase.

**Default sequence:**
```
1. /pm-review          → Is this the right feature to build now?
2. /nfr-check          → NFRs for this specific feature
3. /adr                → Any new architectural decisions?
4. /dev-loop           → Implement
5. /ux-designer        → If user-facing
6. /code-review        → Quality gate
7. /verify             → Confirm
8. /humanize           → Commit
9. /learn              → Session end
```

**Skip /pm-review** if the feature is already P0/P1 and scope is clear.
**Skip /adr** if the feature follows existing patterns with no new decisions.

---

## Bug Fix / Hotfix

Fixing a known defect in production or development.

**Default sequence:**
```
1. Diagnose           → Understand root cause before any code changes
2. /nfr-check quick   → Does the fix introduce any new risks?
3. /dev-loop          → Fix + test
4. /verify            → Confirm fix works and doesn't regress
5. /humanize          → Commit (explains the root cause)
```

**Do not run /pm-review or /adr on hotfixes** unless the fix reveals an architectural issue.
**Flag for /adr** if the bug reveals a systemic design gap.

---

## Research Spike

Understanding an unknown before committing to an approach.

**Default sequence:**
```
1. Define the question  → What exactly are we trying to learn?
2. /stress-test         → What assumptions are we stress-testing?
3. Explore / prototype  → Via /dev-loop write-only mode or direct exploration
4. /adr                 → Document what was learned and what was decided
5. /pm-review           → Updated recommendation based on findings
```

**Output:** a decision (build / don't build / build differently), not working code.

---

## Handover / Documentation Sprint

Preparing a project for someone else to receive.

**Default sequence:**
```
1. /context-sync audit  → Is all context current?
2. /write-spec          → Produce handover spec / README update
3. /code-review         → Final quality check
4. /skill-health        → Org health check before handoff
5. /humanize            → Final commit + release notes
6. /learn               → Full session knowledge capture
```

---

## Architectural Review

Reviewing the design of an existing system for issues or improvements.

**Default sequence:**
```
1. /context-sync        → Load current state
2. /stress-test         → Attack the existing design
3. /adr                 → Document any decisions that should be recorded
4. /nfr-check review    → Audit existing NFR coverage
5. /skill-health        → Org health
```

---

## Mid-Sprint Check-in

Founder checking in during active development.

**What the orchestrator does on session start with active work:**
```
1. Read prd-status.md  → Current step
2. Report health       → CEO compact report
3. Plan next          → Next 1-3 steps
4. Brief              → What the next skill needs
```

No new phase — this is the default orchestrate behavior when invoked without a directive.

---

## Skill Sequence Quick Reference

| Type | First skill | Gate 1 | Middle | Gate 2 | End |
|---|---|---|---|---|---|
| New project | /pm-review | spec approval | /dev-loop | feature approval | /learn |
| New feature | /nfr-check | NFR approval | /dev-loop | code review | /humanize |
| Bug fix | Diagnose | root cause | /dev-loop | /verify | /humanize |
| Research spike | Define question | N/A | Explore | /adr | /pm-review |
| Handover | /context-sync | N/A | /write-spec | /code-review | /learn |
