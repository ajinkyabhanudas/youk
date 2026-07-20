---
name: improve
description: >
  Run youk's self-improvement loop: call self_heal(), find skill gaps with 2+ signals,
  assess each affected skill, and auto-apply SKILL_EDIT improvements immediately.
  Also runs proactive stack scan and presents a MECE skill generation list to the user
  for confirmation before generating any net-new skills.
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
- `skill_generation_pending` — list of skill names with no SKILL.md (Track A candidates)

Report one line: `org_score: {n}/10. Running improvement cycle...`

If `skill_gap_signals` is empty or no entry has count ≥ 2:
report "No recurring gaps found — org health nominal." and stop (no session_end).

**Step 2 — Assess each gap (improve existing skills)**

For each skill in `skill_gap_signals` where count ≥ 2 AND `skills/{name}/SKILL.md` exists:
1. Call `youk-code.assess_skill(skill_name)` — read `proposed_additions`
2. For each addition where `change_type == "SKILL_EDIT"` and `content` is non-empty:
   - Call `youk-core.add_proposal(...)` with the addition details
   - Call `youk-core.apply_proposal(confirmed=True, safe_types=["SKILL_EDIT", "FILE_CREATE"])`
   - If `blocked=True`: surface the reason, move to next
3. For CODE_EDIT or CONFIG_EDIT additions: `add_proposal()` only — do NOT apply

**Step 2b — Proactive stack scan**

Call `youk-code.analyze_stack_for_skills()` with the current project's stack and framework
(from session context or state/session.json). Merge the returned `missing_skills` list with
`skill_generation_pending` from Step 1. Deduplicate against:
- `skills/{name}/SKILL.md` existence (skip if file exists)
- SKILL-REGISTRY.md descriptions (skip if semantic overlap with existing skill name)

**Step 2c — Classification + confirmation gate (before any generation)**

For each candidate in the merged list, classify using one question:
> "Can Claude execute this reliably in-session using existing MCP tools, or does it require a net-new persistent tool capability (new MCP tool registered in a server, new Docker container, new external API)?"

- **SKILL**: Claude can do this in-session → `generate_skill` path
- **MCP_CANDIDATE**: needs a new persistent tool capability → `CODE_EDIT` proposal path; note the specific MCP shape (e.g. "new tool in youk-code server" vs. "new MCP server")

Present the classified candidate list to the user:

```
Candidates ({n} total):
  1. [SKILL] {name} — {one-line rationale: why this gap exists, why it's a skill}
  2. [SKILL] {name} — {one-line rationale}
  3. [MCP_CANDIDATE] {name} — {one-line rationale: what tool is missing, which server it belongs in}
  ...

Approve all / approve subset (numbers) / skip?
```

Wait for response. Only proceed for approved candidates. If user says "skip": proceed to Step 3.

**Step 2d — Generate approved candidates**

For each approved **SKILL** candidate:
1. Call `youk-code.generate_skill(name, purpose, signal_type="demand_gap")`
2. Research phase: use WebSearch (2–3 searches) to find best SKILL.md format and reference
   file patterns for this skill's domain. Synthesize findings into the skill content.
3. Write SKILL.md content using skill-schema.md as template + research findings
4. If reference files are warranted (domain knowledge, best-practices): generate them too
   under `skills/{name}/references/`
5. Stress-test the draft (silent): if BLOCKING → revise once; still BLOCKING → drop
6. Call `youk-core.add_proposal(change_type="FILE_CREATE", review_required=True)`
7. Call `youk-core.apply_proposal(confirmed=True, review_required_override=True)` —
   the skill is live for the rest of this session
8. Add entry to SKILL-REGISTRY.md
9. Report: "Generated skill '{name}' — live this session."

For each approved **MCP_CANDIDATE** candidate:
1. Call `youk-core.add_proposal(change_type="CODE_EDIT", target="{server}/src/server.py or new-server-name", change_description="Add {tool_name} tool: {what it does and why it can't be done in-session}", review_required=True)`
2. Report: "Queued MCP_CANDIDATE '{name}' in PENDING.md — requires founder implementation."
   Do NOT call generate_skill, apply_proposal, or write any SKILL.md for MCP_CANDIDATE items.

**Step 2e — Generate missing skills for this project type (coverage gaps)**

Also check `coverage_gaps` in the self_heal() response.
For each gap in `coverage_gaps` NOT already handled by Step 2d:
- Follow the same generation flow (Steps 2d.1–2d.9)

**Step 3 — Report and close**

Report:
```
Improvement cycle complete.
  Skills updated: {list of updated skills or "none"}
  Skills generated: {list of generated skills or "none"}
  Proposals queued for review: {count} (in PENDING.md)
```

Call `youk-core.track_tokens(approx_input, approx_output, "improve")`
Call `youk-core.session_end("done", commits_made=False, close_cluster=True, skills_used=["self_heal", "assess_skill"])`

---

## Rules

- Never apply CODE_EDIT or CONFIG_EDIT — these require founder review
- If `apply_proposal` returns `blocked=True`, surface the reason once, do not retry
- Run once per session — do not loop or re-call self_heal after applying
- Never auto-generate skills without the confirmation gate (Step 2c) — user must approve
- review_required_override=True is only passed AFTER the user has confirmed the candidate list
- Never call generate_skill for MCP_CANDIDATE items — they route to add_proposal(CODE_EDIT) only
- Classification is mandatory before presenting the candidate list — never show unlabeled candidates
