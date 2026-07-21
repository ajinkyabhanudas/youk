---
name: done
description: >
  Full session close: runs code-review, verify, humanize, and learn in sequence,
  sweeps for unsaved contracts, then calls session_end with close_cluster=True.
  Completion bonus (weight 0.5) — capability skill invocation (weight 2.0) is the
  primary org_score driver. A session where skills ran but /done was skipped still
  moves org_score. A session where /done ran but no skill fired barely moves it. Triggers on: "/done",
  "done", "ship it", "commit", "ok thanks", "that's all", "that's all for now",
  "looks good", "we're done", "we're done here", "let's call it", "alright",
  "perfect", "good enough", "that'll do", "wrap it up", "let's wrap",
  "we can stop here", "nothing else", "I think we're good".
---

# done — Full Session Close

Closes the loop: reviews the work, encodes what was learned, and ends the session
with `close_cluster=True` so the compounding score updates.

---

## Execution sequence

**Step 0 — Goal check (before anything else)**

Read `state/session-goal.json` if it exists (path: `~/.claude/youk/state/session-goal.json`).

If the file exists and `goal_met` is `false`:
1. Surface: "Goal not yet met: {success_criteria}"
2. State what observable outcome the user set at session start
3. Derive the next concrete task that moves toward that outcome
4. Continue working — do NOT proceed to Step 1 (code-review / session close)

If the file does not exist, or `goal_met` is `true`, proceed to Step 1.

**Goal close:** If you determine the goal is now met (all criteria satisfied by work done this session), call `youk-core.task_checkpoint(project_dir, "goal achieved: {stated_goal}", size="M")` — this persists `goal_met=True` and returns `goal_check.goal_met=True`. Then proceed to Step 1.

**Step 1 — Code review**

Call `youk-code.route_to_skill("code-review", "end-of-session review")`.
Follow the returned skill_content. Complete the review before proceeding.

**Step 2 — Verify**

Call `youk-code.route_to_skill("verify", "verify session work")`.
Follow the returned skill_content.

**Step 3 — Humanize**

Call `youk-code.route_to_skill("humanize", "session close")`.
Follow the returned skill_content.

**Step 4 — Learn**

Call `youk-code.route_to_skill("learn", "session close — encode patterns")`.
Follow the returned skill_content.

**Step 5 — Contract sweep**

Scan the conversation for any contract trigger phrases that were spoken but where
`save_contract` was NOT confirmed (look for "always", "never", "from now on",
"make sure you", "every time", "commit format", "don't do that", "wrong approach",
"use this instead").

For each unsaved contract found:
- Call `youk-core.save_contract(contract_text, cwd)`
- Confirm inline: "Saved — '{contract}' will load at the start of every future session."

Collect the list as `explicit_contracts`.

**Step 5a — Loop-dry retrospective check**

Scan the conversation for every `[CHALLENGE PASSED]` or `[CHALLENGE PASSED — revised direction]` verdict emitted this session.

For each verdict found:
1. Determine the rotated lens: `lens_number = (session_number % 4) + 1` where session_number comes from the session_start return value.
2. Re-run that single lens silently against the challenged direction.
3. If the lens finds a new objection: set `loop_gap_detected = True`. Surface: "Retrospective lens {N} found a gap in the challenge loop: {objection}. Running assess_skill('challenge') now."
4. Then call `youk-code.route_to_skill("assess_skill", "challenge — retrospective gap found")` and apply any SKILL_EDIT proposals immediately before session closes.

Also scan the conversation for correction language after any verdict token ("you missed", "what about", "unchallenged", "you didn't consider", "still not at floor", "loop not dry"). If found: set `loop_correction_detected = True`.

Count total ITERATE phases across all challenge invocations this session → `challenge_rounds`.

If no `[CHALLENGE PASSED]` verdicts exist this session: skip silently.

**Step 5b — Doc-staleness sweep**

Call `youk-core.check_doc_graph()`.

For each stale concept returned, check whether files changed this session touch
the concept's `derived_in` list in `docs/doc-map.yaml`. If any derived file was
NOT updated despite the authority changing: surface it as a one-line item:
"Doc gap: '{concept}' changed in {authority} — update {stale_file} before closing."

This catches prose claims (install requirements, command syntax, behavioural contracts)
drifting across docs without requiring a human to remember to check.

Skip silently if check_doc_graph() returns no stale concepts.

**Step 5c — Growth loop sweep**

Scan the conversation to collect three growth signals (answered by reading context — do not ask):

1. **Decision retrospectives:** Were any prior decisions validated or invalidated this session?
   Look for: prior architectural decisions being confirmed ("caching worked"), or revisited ("retry failed").
   Collect as: `decision_retrospectives=[{"decision": "...", "outcome": "VALIDATED|INVALIDATED", "evidence": "..."}]`
   If none found: pass `decision_retrospectives=[]` (empty is fine — data accumulates over sessions).

2. **Autonomy depth:** Did the developer pre-empt any skill (nfr_check, challenge, adversary-loop)?
   If yes, assess depth using the rubric in each skill's SKILL.md (SURFACE/WORKING/DEEP/ELITE).
   Collect as: `autonomy_depth={"nfr_check": "DEEP", "challenge": "WORKING"}` (only include caught skills).

3. **Contract violations:** Were any behavioral contracts (from contracts.md) NOT followed this session?
   Look for: commits without lint, gates skipped, rules overridden.
   Collect as: `contract_violations=["always run ruff check — skipped before commit at 14:30"]`
   If none found: pass `contract_violations=[]`.

4. **Outcome:** What happened to the work at the end of this session?
   Scan the conversation for commit/push/deploy signals:
   - SHIPPED = committed and pushed / deployed to production or staging
   - STAGED = committed to a branch but not pushed / awaiting review
   - ABANDONED = work started but discarded (direction reversed, approach dropped)
   - NONE = no code work this session (planning, review, exploration only)
   Collect as: `outcome="SHIPPED"` (or STAGED / ABANDONED / NONE).

5. **Outcome result:** If work was SHIPPED or STAGED, does the developer know the result yet?
   - WORKED = confirmed functional in the target environment
   - FAILED = errors, regressions, or reverted
   - PENDING = shipped but not yet observed (deployed and awaiting)
   - UNKNOWN = result not applicable or not known
   Collect as: `outcome_result="WORKED"` (or FAILED / PENDING / UNKNOWN).
   Default to PENDING when outcome is SHIPPED/STAGED but result isn't yet confirmed.

**Step 6 — Close**

Call `youk-core.track_tokens(approx_input, approx_output, "final")`
Call `youk-core.compact_context(project_dir)`  — paste the returned `brief` verbatim
Call `youk-core.session_end("done", commits_made=<bool>, explicit_contracts=explicit_contracts, close_cluster=True, loop_correction_detected=<bool>, loop_gap_detected=<bool>, challenge_rounds=<int>, decision_retrospectives=decision_retrospectives, autonomy_depth=autonomy_depth, contract_violations=contract_violations, outcome=outcome, outcome_result=outcome_result)`

---

## Rules

- Do NOT substitute /close for /done — /close skips code-review and learn, does not set close_cluster
- If code-review finds NEEDS REVISION issues: surface them before calling session_end; do not auto-fix
- `commits_made` is True if any `git commit` ran this session, False otherwise
- One /done per session — do not re-invoke if already run
