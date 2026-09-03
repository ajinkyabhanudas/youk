---
name: proposal-review
rationale_why: "CODE_EDIT proposals in PENDING.md accumulate faster than they're reviewed. A proposal written for a function that no longer exists, or a gap that was already closed, wastes founder time on apply_proposal decisions. This skill audits validity before the decision is presented."
description: >
  Proposal validity auditor. Reviews accumulated CODE_EDIT and CONFIG_EDIT proposals in
  PENDING.md and determines whether each is still valid, stale, or conflicting. For each
  proposal: checks whether the target function/file still exists, whether the gap was closed
  by other means (another commit, a SKILL_EDIT, a refactor), and whether the proposed change
  conflicts with current codebase state. Produces a triage table: APPLY NOW / DEFER /
  CLOSE-STALE / CONFLICT. Does not apply proposals — outputs the triage for founder review.
  Triggers on: "/improve" cycle (automatically, after SKILL_EDIT phase), "review pending
  proposals", "what's in PENDING.md", "are these proposals still valid", or any session where
  get_proposals() returns ≥ 3 PENDING items. Do NOT trigger for: SKILL_EDIT proposals
  (auto-applied by improve cycle); closed proposals; or proposals already reviewed this session.
---

# proposal-review — Pending Proposal Validity Auditor

Proposals accumulate. Code changes underneath them. A CODE_EDIT proposal written for a
function that was refactored two sessions ago is noise, not signal — it costs founder time
to re-read and reject it manually at apply_proposal time. This skill sweeps PENDING.md
ahead of that decision point and separates the still-valid from the stale.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full audit: all PENDING CODE_EDIT and CONFIG_EDIT proposals |
| `quick` | LOAD → TRIAGE only — skip deep file verification, flag obvious staleness |
| `target: {proposal_id}` | Audit a single proposal by ID |
| `age: {N}` | Audit only proposals older than N sessions |
| `enter: VERIFY` | Skip LOAD (proposals already listed in context), go to VERIFY |

---

## Context Capture (Always First)

```
PENDING_COUNT:    [count from get_proposals() — if 0 PENDING: stop immediately]
PROPOSAL_IDS:    [list of PENDING proposal IDs and their targets]
PROJECT_DIR:     [current working directory — for file existence checks]
SESSION_COUNT:   [current session number — to compute proposal age]
SKIP_TYPES:      [SKILL_EDIT, FILE_CREATE — these are handled by improve cycle, not this skill]
```

Call `youk-core.get_proposals()` first. Filter to status == "PENDING" and change_type in ["CODE_EDIT", "CONFIG_EDIT"]. If no proposals match: emit "No pending CODE_EDIT proposals to review." and stop.

---

## The Three Phases

### Phase 1 — LOAD

1. Call `youk-core.get_proposals()`. Extract all proposals where `status == "PENDING"` AND `change_type in ["CODE_EDIT", "CONFIG_EDIT"]`.
2. For each proposal, record: `{id, target, change_description, proposed_date, rationale}`.
3. Compute age: `session_count - session_at_proposal` (use proposed_date as proxy if session not stored). Flag any proposal older than 5 sessions as `age: STALE_CANDIDATE`.
4. Group by target file: proposals hitting the same file should be reviewed together — a second proposal may supersede the first.

> Compact phase summary: N proposals loaded, M flagged as stale candidates by age. VERIFY phase needs the proposal list with target paths.

---

### Phase 2 — VERIFY

For each proposal in the loaded list:

**Step 1 — Target existence check:**
- Read the `target` field. If it's a file path: check whether the file exists at that path.
- If it's a function name or section: grep the target file for the function/section name.
- Result: `target_exists: yes | no | partial (file exists, symbol missing)`

**Step 2 — Gap still open check:**
- Read the proposal's `rationale` — it states the problem being fixed.
- Search the target file (and adjacent files it calls) for evidence the gap was already closed:
  - If rationale says "function X has no error handling": check whether error handling was added in a later commit by reading the current function body.
  - If rationale says "missing unit test for Y": grep for `test_Y` or `def test.*Y` in the test directory.
  - If rationale says "config key Z missing": check the current config file for key Z.
- Result: `gap_open: yes | no (already fixed) | unclear`

**Step 3 — Conflict check:**
- Read the proposal's `before` field (the code it expects to find).
- Compare against the current file content at the target section.
- If `before` content doesn't match current content: flag `conflict: yes` — the proposal was written against a version of the code that no longer exists.
- If `before` is empty or "(inline)": skip conflict check, mark `conflict: unknown`.

**Step 4 — Supersession check:**
- If two proposals target the same file and function: the newer one may make the older one redundant. Flag `superseded_by: {newer_id}` if the newer proposal's `change` covers the older one's gap.

> Compact phase summary: each proposal has target_exists, gap_open, conflict, and superseded_by assessed. TRIAGE phase needs this verdict per proposal.

---

### Phase 3 — TRIAGE

Emit a triage table for all reviewed proposals:

```
[PROPOSAL TRIAGE — {date}]
Reviewed: {N} proposals | PENDING CODE_EDIT/CONFIG_EDIT only

{proposal_id} — {target} ({age} sessions old)
  Gap still open:    YES | NO | UNCLEAR
  Target exists:     YES | NO | PARTIAL
  Conflict:          YES | NO | UNKNOWN
  Superseded by:     {id} | NONE
  Verdict:           APPLY NOW | DEFER | CLOSE-STALE | CONFLICT
  Reason:            {one sentence}

...

SUMMARY
  APPLY NOW ({n}):    {id list} — gaps confirmed open, targets exist, no conflict
  DEFER ({n}):        {id list} — gaps open but target changed; need re-scoping
  CLOSE-STALE ({n}):  {id list} — gap already closed or target no longer exists
  CONFLICT ({n}):     {id list} — proposal's before-state no longer matches codebase
```

**Verdict rules:**
- `APPLY NOW`: target_exists=yes, gap_open=yes, conflict=no, superseded_by=NONE
- `DEFER`: target_exists=partial OR gap_open=unclear OR conflict=unknown — needs re-scoping before apply
- `CLOSE-STALE`: target_exists=no OR gap_open=no OR superseded_by is set
- `CONFLICT`: conflict=yes — proposal's expected before-state doesn't match current code; must be rewritten before apply

Do not call `apply_proposal` — this skill produces the triage table only. The founder acts on APPLY NOW items via `/improve` or direct `apply_proposal(confirmed=True)`.

For each `CLOSE-STALE` item: call `youk-core.apply_proposal({id})` with status_override="CLOSED — {reason}" to clear it from the PENDING list. This is the only apply_proposal call this skill makes, and it only closes stale items.

---

## Quality Bars (Non-Negotiable)

- **No skip on age alone:** A proposal being old is not sufficient to mark CLOSE-STALE. Age flags it as a candidate; the gap_open check is required before closing. Failure: skill closes a 10-session-old proposal without checking whether the gap was actually fixed.

- **before-state comparison is required for CONFLICT verdict:** A CONFLICT verdict requires reading the current file at the target section and comparing against the proposal's `before` field. "The code might have changed" is not a conflict finding. Failure: skill marks CONFLICT without reading the current target file.

- **Supersession requires content comparison:** Marking proposal A superseded by proposal B requires that B's change covers A's gap — not just that they target the same file. Failure: skill marks two proposals on the same file as superseded without comparing their change descriptions.

- **CLOSE-STALE calls apply_proposal:** For every proposal given a CLOSE-STALE verdict, `apply_proposal` with a CLOSED status must be called before the session ends — not just listed in the triage table. Failure: triage table shows 3 CLOSE-STALE items but no apply_proposal calls were made.

- **APPLY NOW does not apply:** This skill surfaces what can be applied; it does not apply it. The only apply_proposal calls are for closing CLOSE-STALE items. Failure: skill calls apply_proposal(confirmed=True) on an APPLY NOW item.

### Hiring Validation

1. **Gap already closed:** Proposal says "add error handling to `_load_session_plan()`". Current `session.py` has a try/except block in that function added in a commit last week. Expected: skill reads the current function body, detects the error handling, marks gap_open=no, verdict=CLOSE-STALE.

2. **Target function removed:** Proposal targets `_detect_project_type_legacy()`. That function was removed in a refactor. Expected: target_exists=partial (file exists, symbol missing), verdict=CLOSE-STALE with reason "target function no longer exists".

3. **Conflict detection:** Proposal's `before` field shows `def route_task(task, intent):` but current `server.py` has `def route_task(task, intent_brief, file_context=None):`. Expected: conflict=yes, verdict=CONFLICT, skill does not close or apply.

4. **Two proposals on same function:** Proposal A (session 30) adds a null check to `_generate_findings()`. Proposal B (session 35) rewrites `_generate_findings()` entirely. Expected: A is superseded_by B — applying A after B would be a no-op or regression.

5. **APPLY NOW threshold:** Proposal targets `health.py` function that still exists, gap (missing staleness check) still open, no conflict. Expected: APPLY NOW verdict, proposal appears in SUMMARY APPLY NOW list, no apply_proposal call made by this skill.

---

## Reference Files

None required — this skill operates on get_proposals() output and file reads.

---

## Example Flows

**Full sweep before /improve:**
> "Review pending proposals before we run the improve cycle."

LOAD → 4 PENDING CODE_EDIT proposals → VERIFY each (target check + gap check + conflict check) → TRIAGE: 1 APPLY NOW, 1 DEFER, 1 CLOSE-STALE, 1 CONFLICT → apply_proposal(CLOSED) for stale item → triage table surfaced for founder.

**Quick age-based scan:**
> "proposal-review quick"

LOAD → flag any proposal older than 5 sessions → TRIAGE without deep file reads: 2 stale candidates surfaced, gap_open marked UNCLEAR → founder decides.

**Single proposal audit:**
> "proposal-review target: PENDING-20260730180108"

LOAD (one proposal) → VERIFY: target=nfr-check SKILL.md, gap=Q7 trigger breadth — read current SKILL.md → gap_open=no (already contains the broadened trigger) → TRIAGE: CLOSE-STALE → apply_proposal(CLOSED).

**Post-refactor sweep:**
> "A big refactor just landed — check which proposals are still valid."

LOAD → N proposals → VERIFY each with conflict check prioritized (refactors most likely cause before-state drift) → TRIAGE: surface CONFLICT items first, then CLOSE-STALE, then APPLY NOW.
