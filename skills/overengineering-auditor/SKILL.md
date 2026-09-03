---
name: overengineering-auditor
rationale_why: "A plan reviewed only by the team that made it is reviewed by people who are invested in it. A fresh reviewer with no session history sees what commitment blinds: the gap between what the plan does and what the task requires."
description: >
  Planning-phase skill. Fires after a plan is produced and before implementation
  begins. Spawns a context-free subagent — one that receives only the plan text,
  task description, and repo structure, never the session history — to audit the
  plan for overengineering. The subagent returns: (1) what is overengineered and
  why, (2) a simpler alternative with constraints, (3) under what specific
  circumstances the complexity would be worth it. After the developer approves a
  direction, triggers stress-test on the accepted plan. Triggers on: any M+ plan
  that has been produced and approved in outline, explicit "audit this plan",
  "is this overengineered?", "do we need all of this?", any plan produced by
  write-spec or the /build routing sequence.
---

# overengineering-auditor — Context-Free Plan Simplicity Gate

A planning-phase gate that catches overengineering by design: the auditor is a
subagent with no session history, no knowledge of why the plan was designed as it
was, and no investment in its survival. That context-blindness is the point.

The skill does not try to reject complexity. It asks the one question a fresh
reviewer always asks: **"what specifically does this plan do that the task does not
require?"** and then provides the reasoning that lets the developer make a real
choice, not just a reflex simplification.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full audit: subagent spawn → findings → simpler alternative → approval gate → stress-test |
| `quick` | Subagent audit only — top finding per category, no full stress-test |
| `dry-run` | Print the subagent prompt that would be sent — for inspection/debugging |
| `retest: [revised plan]` | Given a revised plan, re-run the subagent against it only |

---

## When This Skill Fires

**Automatic (via M+ routing):** After `plan_hook` output is produced and the developer
has silenced or accepted the plan outline. Fires before `nfr_check`.

**Manual:** Any time the developer says "audit this plan", "is this overengineered?",
"do we need all of this?", or shows a plan for review.

**Does not fire on:** XS/S tasks (no plan hook exists). Tasks where the developer
has already explicitly confirmed the complexity is required this session.

---

## Context Capture (Always First)

Before spawning the subagent, extract from session context:

```
PLAN_TEXT:       [the full plan — bullet list, numbered steps, or prose. Must be complete.]
TASK_DESC:       [the original task in one sentence — what the user asked for]
REPO_STRUCTURE:  [one-paragraph summary: language, framework, key modules, rough size]
FIXED_CONSTRAINTS: [what cannot change — stated explicitly by user this session]
PLAN_SIZE:       [estimated: LOC, files touched, new abstractions introduced]
```

**Strict content rule for subagent prompt:** Pass ONLY `PLAN_TEXT`, `TASK_DESC`, and
`REPO_STRUCTURE`. Do NOT include: session history, NFR blocks, prior challenge output,
ADR decisions, rationale for plan choices, or any context that reveals why the plan
was designed as it was. The isolation is the audit's validity guarantee.

---

## The Five Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — PREP

`[PHASE: PREP]`

1. Extract all five fields from context (see Context Capture above).
2. Confirm `PLAN_TEXT` is complete. If the plan is a stub or bullet outline without
   enough detail to audit (< 5 meaningful items), surface:
   `"Plan is too thin to audit reliably — expand it first or proceed anyway? (default: proceed)"`
3. Identify `FIXED_CONSTRAINTS` — these will be passed to the subagent as walls, not
   attack surfaces. The subagent is told explicitly: do not challenge these.
4. State: `"Spawning context-free auditor — subagent receives: plan + task + repo structure only."`

---

### Phase 2 — AUDIT (subagent)

`[PHASE: AUDIT]`

Spawn a subagent using the Agent tool with the following locked prompt template.
**Do not deviate from this template** — additions leak session context and corrupt
the isolation guarantee.

---

**Subagent prompt template (copy verbatim, fill placeholders only):**

```
You are a senior engineer doing a cold-read plan review. You have not seen any prior
discussion. You know only:

TASK: {TASK_DESC}

REPO: {REPO_STRUCTURE}

FIXED CONSTRAINTS (do not challenge these — they are decided):
{FIXED_CONSTRAINTS or "None stated."}

PLAN TO REVIEW:
{PLAN_TEXT}

---

Your job: audit this plan for overengineering. You are looking for the gap between
what the plan builds and what the task requires. You have three jobs:

1. OVERENGINEERING FINDINGS
   For each part of the plan that appears to exceed what the task requires:
   - Name it specifically (which layer, abstraction, or component)
   - State what the task requires that this part is satisfying
   - State what the task does NOT require that this part is also satisfying
   - Rate the excess: CLEAR_EXCESS (unambiguously beyond task scope) |
     CONDITIONAL (useful if certain conditions hold) | JUSTIFIED (appears necessary)

2. SIMPLER ALTERNATIVE
   Propose the simplest version of this plan that still satisfies the task.
   - List what you are removing or flattening and why
   - State what the simpler version cannot do that the original can
   - State the constraints this simpler version requires to remain valid
     (e.g. "valid only if concurrent load stays under X", "valid only if feature Y is not needed")

3. WHEN COMPLEXITY IS WORTH IT
   For each CONDITIONAL or JUSTIFIED finding, state specifically:
   - Under what condition does the complexity pay for itself?
   - What observable signal would tell the developer that condition has been met?
   - Is that condition present in this task as stated? (yes / no / unknown)

Be specific. Vague findings ("this seems complex") are not useful.
Name the specific component, layer, or pattern. Name the specific condition.
```

---

**Fallback (if subagent returns empty or fails):**
Run the three audit questions above as an inline monologue, clearly labeled:
`[FALLBACK: inline audit — subagent returned empty]`
This preserves the skill's output contract even without true context isolation. Note
the limitation: the inline audit is not context-free. Surface this to the developer.

---

### Phase 3 — FINDINGS

`[PHASE: FINDINGS]`

Present the subagent's output in a structured format. Do not editorialize — surface
the subagent's findings as-is, then add one synthesis line per section.

```
[OVERENGINEERING AUDIT — {date}]
Auditor: context-free subagent (received: plan + task + repo structure only)

FINDINGS ({n} total: {n} CLEAR_EXCESS, {n} CONDITIONAL, {n} JUSTIFIED):

  {For each finding:}
  ─ {component or layer name}
  Rating:    CLEAR_EXCESS | CONDITIONAL | JUSTIFIED
  Exceeds:   {what the task doesn't require that this provides}
  Satisfies: {what the task does require}

SIMPLER ALTERNATIVE:
  Removes: {list}
  Cannot do: {list — what is lost}
  Valid if: {constraints that must hold}

WHEN COMPLEXITY PAYS:
  {For each CONDITIONAL/JUSTIFIED finding:}
  ─ {component}: worth it when {condition} — signal: {observable indicator}
    Present in this task? {yes / no / unknown}
```

---

### Phase 4 — APPROVAL GATE

`[PHASE: APPROVAL GATE]`

Present the developer with a clear choice. **Do not default to simpler** — present both
options with their constraints:

```
Two paths forward:

  A) ACCEPT SIMPLER ALTERNATIVE
     What you keep: {list what stays}
     What you lose: {list what the simpler version drops}
     Constraints that must hold: {list}
     Stress-test will run on: the simplified plan

  B) KEEP ORIGINAL PLAN (with complexity justified)
     Reason to keep: {the specific condition from Phase 3 that applies here}
     What to watch for: {the observable signal that validates the complexity over time}
     Stress-test will run on: the original plan

  C) REVISE (partial simplification)
     [Only surface if findings include both CLEAR_EXCESS and JUSTIFIED items]
     Keep: {JUSTIFIED items}
     Remove: {CLEAR_EXCESS items}
     Stress-test will run on: the revised plan

Choose A, B, or C — or describe a different revision.
```

Wait for the developer's response before proceeding to Phase 5.

---

### Phase 5 — STRESS-TEST

`[PHASE: STRESS-TEST]`

After the developer approves a path, trigger stress-test on the **accepted plan**:

1. Compose the stress-test subject from the accepted path (A = simplified plan,
   B = original plan, C = revised plan).
2. Call `youk-code.route_to_skill("stress-test", "{accepted plan description}")`.
3. Follow the returned skill_content. The stress-test runs on the accepted plan,
   not the audit's simplified draft.

If the developer is in `quick` mode: skip Phase 5 (stress-test is optional in quick mode).
State: `"quick mode — stress-test skipped. Run /stress-test on the accepted plan to complete the gate."`

---

## Quality Bars (Non-Negotiable)

- **Subagent prompt is locked.** No additions beyond the template placeholders. Session
  reasoning, NFR blocks, ADR decisions, and rationale for plan choices must never appear
  in the subagent prompt. If you cannot assemble the prompt without including session
  context — run the fallback and label it clearly.
- **Stress-test fires on the accepted plan.** If the developer accepts the simpler
  alternative, stress-test runs on the simpler plan. If they keep the original, stress-test
  runs on the original. Never stress-test the audit's simplified draft when the developer
  chose to keep the original.
- **Approval gate is a real gate.** Do not auto-select the simpler option. Present both
  paths with constraints. The developer decides.
- **JUSTIFIED findings are not failure.** If the subagent rates a component JUSTIFIED, that
  is a clean result — the complexity is warranted. Do not press for simplification.
- **Fallback is labeled.** If the subagent returns empty and inline audit runs instead,
  the limitation must be visible to the developer.
- **Quick mode is not a shortcut through the approval gate.** Quick mode skips stress-test;
  it does not skip the findings or the approval gate.

---

## Routing Integration

This skill wires into the M+ build sequence at the **plan_hook slot**:

```
plan produced → overengineering-auditor → [approval gate] → nfr_check → 
check_nfr_gate → check_challenge_gate → dev-loop
```

In CLAUDE.md routing, this fires as step 4b (between plan_hook and nfr_check) for M+
tasks where a plan has been produced. It does not block the sequence if the developer
skips or declines — the approval gate accepts silence as "keep original."

---

## Hiring Validation

This skill passes the hiring committee if it can:

1. **Isolation guarantee:** The subagent prompt contains only `PLAN_TEXT`, `TASK_DESC`,
   `REPO_STRUCTURE`, and `FIXED_CONSTRAINTS` — nothing else. If session history appears
   in the prompt, the skill fails.
2. **Approval gate is real:** Given findings with both CLEAR_EXCESS and JUSTIFIED items,
   the skill surfaces option C (partial simplification) and waits — it does not default to
   the simpler option.
3. **Stress-test routes correctly:** If the developer accepts the simpler alternative,
   stress-test runs on the simplified plan. If they keep the original, stress-test runs on
   the original. The skill never stress-tests the wrong version.
4. **Fallback is honest:** When the subagent returns empty, the skill runs the inline
   fallback and labels it with the isolation limitation. It does not pretend the inline
   audit is context-free.
5. **JUSTIFIED is clean:** Given a plan where the subagent rates all components JUSTIFIED,
   the skill emits "all findings JUSTIFIED — complexity is warranted" and proceeds to
   stress-test without pushing for simplification.
