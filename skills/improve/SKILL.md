---
name: improve
description: >
  Run youk's self-improvement loop: call self_heal(), find skill gaps with 2+ signals,
  assess each affected skill, and auto-apply SKILL_EDIT improvements immediately.
  CODE_EDIT/CONFIG_EDIT proposals are queued in PENDING.md for founder review.
  Triggers on: "/improve", "improve the skills", "run improvement cycle",
  "self-heal youk", "update skills based on gaps".
---

# improve — youk Self-Improvement Loop

Audits accumulated skill gaps from the session history and applies safe improvements
without waiting for the next health cycle.

---

## Execution sequence

**Step 1 — Audit**

Call `youk-core.self_heal()`. Extract:
- `org_score` — current health (0–10)
- `findings` — top findings list
- `skill_gap_signals` — dict of skill name → gap count

Report one line: `org_score: {n}/10. Running improvement cycle...`

If `skill_gap_signals` is empty or no entry has count ≥ 2:
report "No recurring gaps found — org health nominal." and stop (no session_end).

**Step 2 — Assess each gap (improve existing skills)**

For each skill in `skill_gap_signals` where count ≥ 2:
1. Call `youk-code.assess_skill(skill_name)` — read `proposed_additions`
2. For each addition where `change_type == "SKILL_EDIT"` and `content` is non-empty:
   - Call `youk-core.add_proposal(...)` with the addition details
   - Call `youk-core.apply_proposal(confirmed=True, safe_types=["SKILL_EDIT", "FILE_CREATE"])`
   - If `blocked=True`: surface the reason, move to next
3. For CODE_EDIT or CONFIG_EDIT additions: `add_proposal()` only — do NOT apply

**Step 2b — Generate missing skills for this project type**

Also check `coverage_gaps` in the self_heal() response.
For each gap in `coverage_gaps` (skills expected for this project type but absent):
1. Call `youk-code.generate_skill(name, purpose, context, signal_type)` where:
   - `context` = "Project type: {project_type_description}. Stack: {stack from session context}."
   - `signal_type` = "session_trigger"
2. Call `youk-core.add_proposal(...)` with FILE_CREATE targeting `skills/{name}/SKILL.md`
3. Call `youk-core.apply_proposal(confirmed=True, safe_types=["FILE_CREATE"])`
4. Report inline: "Generated skill '{name}' for {project_type_description}."

**Step 3 — Report and close**

Report:
```
Improvement cycle complete.
  Skills updated: {list of updated skills or "none"}
  Proposals queued for review: {count} (in PENDING.md)
```

Call `youk-core.track_tokens(approx_input, approx_output, "improve")`
Call `youk-core.session_end("done", commits_made=False, close_cluster=True, skills_used=["self_heal", "assess_skill"])`

---

## Rules

- Never apply CODE_EDIT or CONFIG_EDIT — these require founder review
- If `apply_proposal` returns `blocked=True`, surface the reason once, do not retry
- Run once per session — do not loop or re-call self_heal after applying
