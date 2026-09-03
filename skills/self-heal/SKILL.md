---
name: self-heal
description: >
  Behavioral execution protocol for youk's self-improvement loop. Makes health and
  improvement work register as a capability skill in the audit — without this SKILL.md,
  /health and /improve sessions log "Skills: none" even when real improvement happened.
  Fires when: /health is typed, /improve is typed, "how is youk doing?", "org_score check",
  "what gaps exist?", "run self_heal", recurring gap mentioned in session. Produces:
  org_score, top findings, gap assessment, SKILL_EDIT proposals applied in-session,
  and a closed improvement cycle. Do NOT use for code review (code-review skill),
  challenge (challenge/adversary-loop skills), or spec writing (write-spec skill).
---

# self-heal — youk Self-Improvement Execution Protocol

Makes every /health and /improve session a registered capability skill invocation.
The primary leverage point: a session that runs self_heal() but has no SKILL.md
cannot register "self_heal" in the audit — this file closes that gap.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full loop: AUDIT → ASSESS → GENERATE → APPLY → CLOSE |
| `quick` | AUDIT only — report org_score + top 2 findings, no apply |
| `assess: {skill}` | ASSESS a single named skill, skip AUDIT and GENERATE |
| `gaps only` | AUDIT + ASSESS, skip GENERATE and APPLY — queue proposals only |
| `enter: APPLY` | Skip to APPLY — proposals already queued in PENDING.md |

auto-skip: |
  If self_heal() was already called this session and no new commits or skill edits
  have been made since — skip AUDIT, re-use previous findings, jump to ASSESS.

---

## Context Capture (Always First)

```
PROJECT_DIR:     [infer from session context — the youk root or the active project]
LAST_ORG_SCORE:  [from session_start brief, or "unknown" if not loaded]
PENDING_COUNT:   [from session_start brief, or read state/session.json]
TRIGGER:         [/health | /improve | session_start (health_check_due=True) | explicit ask]
SESSION_CAP:     [has self_heal() already run this session? yes → skip AUDIT]
```

---

## The Five Phases

### Phase 1 — AUDIT

1. Call `youk-core.self_heal()`. Extract:
   - `org_score` — current health (0–10)
   - `findings` — top findings list (already ranked by impact)
   - `skill_gap_signals` — dict of skill name → gap count
   - `skill_generation_pending` — list of skill names with no SKILL.md
   - `coverage_gaps` — skills missing for this project type

2. Emit one line: `org_score: {n}/10. {N} gap signal(s). {M} pending proposals.`

3. Surface top 2 findings verbatim from the `findings` list (not paraphrased).

4. If `skill_gap_signals` is empty AND `skill_generation_pending` is empty:
   emit "No recurring gaps — org health nominal." and skip to CLOSE (no proposals, no apply).

> Compact phase summary: org_score known, gap signals enumerated, generation candidates identified.

---

### Phase 2 — ASSESS

For each skill in `skill_gap_signals` where count ≥ 2 AND `skills/{name}/SKILL.md` exists:

1. Call `youk-code.assess_skill(skill_name)` — read `proposed_additions`.
2. For each `proposed_addition`:
   - If `change_type == "SKILL_EDIT"` and `content` is non-empty: mark as APPLY candidate
   - If `change_type == "CODE_EDIT"` or `"CONFIG_EDIT"`: mark as QUEUE-ONLY (no auto-apply)
   - If `content` is empty: skip — do not propose an empty edit

3. If a skill in `skill_gap_signals` has NO SKILL.md: add to generation candidates (Phase 3).

4. Emit per-skill: `{skill}: {N} proposed edits ({M} auto-applicable, {K} queued for review)`

> Compact phase summary: proposed_additions collected per skill; APPLY and QUEUE-ONLY lists ready.

---

### Phase 3 — GENERATE (net-new skills only)

Merge `skill_generation_pending` + skills from ASSESS that had no SKILL.md.
Deduplicate against:
- `skills/{name}/SKILL.md` existence (skip if present)
- SKILL-REGISTRY.md descriptions (semantic overlap check — skip if covered)

For each remaining candidate, classify:
> "Can Claude execute this reliably in-session using existing MCP tools, or does it require a net-new persistent tool capability (new MCP tool, new Docker container, new external API)?"

- **SKILL** → generate_skill path
- **MCP_CANDIDATE** → CODE_EDIT proposal path (note specific MCP shape)

Present the classified list:
```
Candidates ({n} total):
  1. [SKILL] {name} — {one-line: why the gap exists + why it's a skill}
  2. [MCP_CANDIDATE] {name} — {one-line: what tool is missing + which server}
  ...
Approve all / approve subset (numbers) / skip?
```

Wait for response. Only proceed for approved candidates.

For each approved **SKILL**:
1. Call `youk-code.generate_skill(name, purpose, signal_type="demand_gap")`
2. Write SKILL.md using skill-schema as template
3. Stress-test (silent): BLOCKING → revise once; still BLOCKING → drop
4. Call `youk-core.add_proposal(change_type="FILE_CREATE", review_required=True)`
5. Call `youk-core.apply_proposal(confirmed=True, review_required_override=True)` — live now
6. Add entry to SKILL-REGISTRY.md

For each approved **MCP_CANDIDATE**:
1. Call `youk-core.add_proposal(change_type="CODE_EDIT", target="{server}/src/server.py", change_description="Add {tool_name}: {what it does, why not in-session}", review_required=True)`
2. Report: "Queued '{name}' in PENDING.md — requires founder implementation."

> Compact phase summary: net-new skills generated and live (or queued); SKILL-REGISTRY.md updated.

---

### Phase 4 — APPLY

For each SKILL_EDIT proposal from ASSESS (Phase 2):
1. Call `youk-core.add_proposal(change_type="SKILL_EDIT", target=..., target_section=..., content=<full section content — not just the addendum>, reason=..., review_required=False)`
2. **CRITICAL**: `content` must be the FULL desired section text, not just the new lines. apply_proposal replaces the entire target_section — partial content destroys the rest.
3. Call `youk-core.apply_proposal(confirmed=True, safe_types=["SKILL_EDIT", "FILE_CREATE"])`
4. If `blocked=True`: surface reason once, move to next. Do NOT retry.
5. If `diff_preview` is returned: show it before continuing.

For each CODE_EDIT/CONFIG_EDIT: `add_proposal()` only — do not apply. Surface in CLOSE.

> Compact phase summary: SKILL_EDIT proposals applied; CODE_EDIT/CONFIG_EDIT queued in PENDING.md.

---

### Phase 5 — CLOSE

Report:
```
Improvement cycle complete.
  org_score:         {n}/10
  Skills assessed:   {list or "none"}
  Skills updated:    {list of SKILL_EDIT applied or "none"}
  Skills generated:  {list of new SKILL.md written or "none"}
  Queued for review: {count} proposals in PENDING.md
```

Call `youk-core.track_tokens(approx_input, approx_output, "improve")`
Call `youk-core.session_end("done", commits_made=False, close_cluster=True, skills_used=["self_heal", "assess_skill"])`

---

## Quality Bars (Non-Negotiable)

- **SKILL_EDIT content must be the full section**: apply_proposal replaces entire target_section. Sending only the new lines destroys the rest of the section. Always read the current content, merge the addition, send the complete result.
- **Never apply CODE_EDIT or CONFIG_EDIT**: these change server code or global config — founder review required. Surface in CLOSE, mark PENDING.
- **Classification before generation**: never present unlabeled candidates. Every candidate gets [SKILL] or [MCP_CANDIDATE] before the list is shown.
- **review_required_override only after user confirms**: do not pass `review_required_override=True` on FILE_CREATE proposals until the user has approved the candidate list in Phase 3.
- **Run once per session**: do not re-call self_heal() after applying. The findings are from the same audit snapshot — re-running produces noise, not signal.
- **Empty content = skip**: if `proposed_addition.content` is empty, do not add_proposal. An empty SKILL_EDIT corrupts the target section.

## Hiring Validation

1. **SKILL_EDIT destructive write test**: If the skill is given a proposed addition that is 2 new lines, does it read the full current section before writing, merge the addition, and send all lines — or does it send only the 2 new lines and destroy the rest? Correct: full section content always.
2. **Classification gate test**: Given `skill_generation_pending=["install-checker"]`, does it classify before presenting? Correct: shows `[SKILL] install-checker — {rationale}`, waits for approval, does not call `generate_skill` until user responds.
3. **CODE_EDIT block test**: Given a proposed_addition with `change_type="CODE_EDIT"`, does it call `add_proposal` only (no `apply_proposal`)? Correct: queued, not applied.
4. **Audit registration test**: After this skill runs and session_end is called, does the audit log show `skills_used: ["self_heal", "assess_skill"]`? Correct: yes — this is the entire point of the SKILL.md existing.
5. **Empty gap test**: Given `skill_gap_signals={}` and `skill_generation_pending=[]`, does it emit "No recurring gaps — org health nominal." and stop? Correct: yes, no phantom proposals.

---

## Reference Files

| File | When to read |
|------|-------------|
| `knowledge/SKILL-REGISTRY.md` | Phase 3 — dedup candidates against existing skill descriptions |
| `servers/shared/models.py` | Phase 4 — understand Proposal fields before calling add_proposal |

---

## Example Flows

**Full /improve triggered by health_check_due:**
> `health_check_due=True` at session_start → `/improve` auto-fires

AUDIT (self_heal returns org_score=6.2, skill_gap_signals={"dev-loop": 3}, skill_generation_pending=["self-heal"]) →
ASSESS (assess_skill("dev-loop") → 1 SKILL_EDIT: add escalation block) →
GENERATE (candidate: [SKILL] self-heal — present, user says "approve all") →
generate_skill("self-heal") → write SKILL.md → apply_proposal(FILE_CREATE) →
APPLY (add_proposal + apply_proposal for dev-loop SKILL_EDIT) →
CLOSE (report: 1 updated, 1 generated, 0 queued)

**Quick health check:**
> "/health"

AUDIT only → emit `org_score: 7.1/10. 2 gap signals. 3 pending proposals.` →
Surface top 2 findings → skip ASSESS/GENERATE/APPLY → emit quick report → no session_end

**Single skill assessment:**
> "assess: nfr-check"

Jump to ASSESS for nfr-check only → assess_skill("nfr-check") → surface proposed additions →
If user says apply: APPLY phase for that skill only → no CLOSE/session_end

**MCP_CANDIDATE surfaced:**
> Session with skill_generation_pending=["install-verifier"]

GENERATE → classify: install-verifier requires a tool that runs `make build` and checks exit codes
in a subprocess — that's a new MCP tool, not in-session execution →
[MCP_CANDIDATE] install-verifier — requires new tool in youk-code server that shells out to make →
User approves → add_proposal(CODE_EDIT, target="servers/code/src/server.py") →
CLOSE: "Queued 'install-verifier' in PENDING.md — requires founder implementation."
