---
name: done
description: >
  Full session close: runs code-review, verify, humanize, and learn in sequence,
  sweeps for unsaved contracts, then calls session_end with close_cluster=True.
  This is the primary org_score driver — a session that doesn't end with /done
  barely moves the score even if capability skills ran. Triggers on: "/done",
  "ship it", "we're done", "close the session", "wrap up", "commit and close",
  "mark as done".
---

# done — Full Session Close

Closes the loop: reviews the work, encodes what was learned, and ends the session
with `close_cluster=True` so the compounding score updates.

---

## Execution sequence

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
Call `youk-core.compact_context(cwd)`  — paste the returned `brief` verbatim
Call `youk-core.session_end("done", commits_made=<bool>, explicit_contracts=explicit_contracts, close_cluster=True)`

---

## Rules

- Do NOT substitute /close for /done — /close skips code-review and learn, does not set close_cluster
- If code-review finds NEEDS REVISION issues: surface them before calling session_end; do not auto-fix
- `commits_made` is True if any `git commit` ran this session, False otherwise
- One /done per session — do not re-invoke if already run
