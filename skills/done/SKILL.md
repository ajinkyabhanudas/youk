---
name: done
description: >
  Full session close: runs code-review, verify, humanize, and learn in sequence,
  sweeps for unsaved contracts, then calls session_end with close_cluster=True.
  This is the primary org_score driver — a session that doesn't end with /done
  barely moves the score even if capability skills ran. Triggers on: "/done",
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

**Step 5b — Doc-staleness sweep**

Call `youk-core.check_doc_graph()`.

For each stale concept returned, check whether files changed this session touch
the concept's `derived_in` list in `docs/doc-map.yaml`. If any derived file was
NOT updated despite the authority changing: surface it as a one-line item:
"Doc gap: '{concept}' changed in {authority} — update {stale_file} before closing."

This catches prose claims (install requirements, command syntax, behavioural contracts)
drifting across docs without requiring a human to remember to check.

Skip silently if check_doc_graph() returns no stale concepts.

**Step 6 — Close**

Call `youk-core.track_tokens(approx_input, approx_output, "final")`
Call `youk-core.compact_context(project_dir)`  — paste the returned `brief` verbatim
Call `youk-core.session_end("done", commits_made=<bool>, explicit_contracts=explicit_contracts, close_cluster=True)`

---

## Rules

- Do NOT substitute /close for /done — /close skips code-review and learn, does not set close_cluster
- If code-review finds NEEDS REVISION issues: surface them before calling session_end; do not auto-fix
- `commits_made` is True if any `git commit` ran this session, False otherwise
- One /done per session — do not re-invoke if already run
