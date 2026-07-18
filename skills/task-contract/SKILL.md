---
name: task-contract
description: >
  Task intake contract: converts a developer's request into a filled, editable
  contract before heavy work — surfacing what youk understood, adversarial
  provocations from frame rotation, and what this pass will NOT include.
  Fill, don't interrogate: present a complete interpretation for editing.
  Triggers on: M+ tasks at /build time, "contract this task", "spec this task",
  "what did you understand", explicit /task-contract invocation.
  Does NOT trigger on XS/S tasks (below contract line).
---

# task-contract — Task Intake Contract

Stop before going deep. Surface interpretation and risks first.

This skill fires on M+ tasks before heavy work starts. It produces a filled contract
that the developer edits — not a questionnaire the developer fills from scratch.

---

## Invocation

```
youk-core.task_contract(task, size=None)
→ present returned `contract` markdown
→ developer edits (any field, including provocations)
→ youk-core.approve_task_contract(contract_id, as_approved, disposition_map)
→ for L/XL: youk-core.check_task_contract_gate(size) → proceed only when blocked=False
```

---

## Contract Template (L/XL full)

```
TASK CONTRACT <id> — <date> — size <M|L|XL>
GOAL (in youk's words):        <1-2 lines>
DONE-MEANS (observable):       <what a reviewer could check>
SCOPE-IN:                      <bullets, max 5>
SCOPE-OUT (will NOT touch):    <bullets, max 5 — the highest-value field>
ASSUMPTIONS:                   <each tagged stated-by-you|inferred|default>
APPROACH:                      <2 lines max>
PROVOCATIONS (dispositions required before work starts):
  P1 [frame LABEL] <risk, 1 line> (<personalization citation if any>)
          → IN-SCOPE | DEFER | ACCEPT-RISK | N/A
  ... (5-7 items for L/XL, ranked by severity × miss-likelihood)
CUT-LIST (L/XL only):
  <bullets — honest one-shot triage, reprioritizable before work>
LOWEST-CONFIDENCE FIELD: <field name> — <why>
OPEN QUESTION (max 1):   <or "none">
```

MINI contract (M size) omits CUT-LIST and has ≤3 provocations.

---

## SCOPE-OUT — the highest-value field

Write SCOPE-OUT first and most carefully. It forces honest scope triage:
- What adjacent problems WON'T be touched (and why not now)?
- What refactors won't be done even if the area is touched?
- What related improvements are deferred to CUT-LIST?

A good SCOPE-OUT prevents the most expensive class of bugs: scope creep that isn't caught
until the PR review or the next session.

**Example (good):**
```
SCOPE-OUT:
  - Auth middleware — related but separate risk surface; separate task
  - Retry logic — would double scope; ACCEPT-RISK that failures aren't retried
  - Metrics schema changes — additive-only this pass
```

**Example (bad):**
```
SCOPE-OUT:
  - Out-of-scope items
  - Things not needed
```

---

## Disposition Semantics

Each provocation requires a disposition before L/XL work starts:

| Disposition | Meaning | Effect |
|-------------|---------|--------|
| `IN-SCOPE` | This risk is addressed by the planned work | No follow-up needed |
| `DEFER` | Valid risk, not this pass — tracked as follow-up | Written to session summary |
| `ACCEPT-RISK` | Aware of risk, proceeding anyway | Appended to `state/risk-ledger.jsonl` |
| `N/A` | Frame doesn't apply to this specific task | No action |

`ACCEPT-RISK` entries are personalized in future contracts: "you accepted this risk N times."
After a FAILED outcome, the bite-rate metric links accepted risks to confirmed failures.

---

## Provocation Generation

Provocations use frame rotation from `skills/adversarial-planning/references/frames.md`
(single source of truth — never forked). For each frame, one trigger question is applied
against the task. Top 5-7 by (severity × miss-likelihood) are kept; padding is never done.

Personalization ranks higher: if the developer previously accepted a risk on the same
frame or a recurring gap theme matches the task, the provocation cites it.

---

## Example — Good ACCEPT-RISK

```
P3 [F5 TRUST] State/compact-count.json is shared across sessions — concurrent writes
   from multiple Claude instances could corrupt the counter.
          → ACCEPT-RISK
```

The developer knows the risk, documents it, accepts it. If a future FAILED outcome names
"concurrent file corruption" as a cause, the bite-rate metric catches this automatically.

---

## Example — Good DEFER

```
P2 [F7 SCALE/FAILURE] compact-count.json grows unboundedly if session_end never fires
   (tab-close sessions leave stale count files).
          → DEFER
```

Written to session summary as a follow-up item. Does not block this pass.

---

## Metrics (visibility-only, R10-labeled)

- `contract_edit_rate [R10]`: fields materially edited / fields presented, trailing mean
  over last 10 contracts. Declining trend = direct per-developer compounding evidence.
- `accept_risk_bite_rate [R10]`: ACCEPT-RISK entries later linked to FAILED outcome,
  over total ACCEPT-RISK entries.
- Neither metric affects org_score.

Accessible via `youk-core.self_heal()` findings section.

---

## Wired into /build

See `skills/build/SKILL.md` Step 1.5 — contract gate runs between route_task and NFR check
for M+ tasks. For L/XL, check_task_contract_gate() gates dev-loop entry.
