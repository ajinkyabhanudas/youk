---
name: build
description: >
  Start a build task with proper routing: calls route_task to size the work, runs
  nfr_check before any code on M+ tasks, then hands off to dev-loop. Enforces
  the planning gate — M+ tasks never start without a plan_hook and nfr_check.
  Triggers on: "/build", "build this", "implement this", "let's build", "start
  coding", "write this feature", "start implementing".
---

# build — Task Start with Full Gate

Routes the task, enforces planning and NFR gates on M+ work, then executes.

---

## Execution sequence

**Step 0 — Global state override (before route_task)**

Before calling route_task, check: does this task involve any of the following?
- Writing to `~/.claude/` (skills, MCP config, CLAUDE.md, settings.json)
- Adding to a shared namespace used by multiple tools (skill names, MCP server names, config keys)
- Modifying files outside the current project directory that affect other projects or sessions

If yes: **force size = M** regardless of what route_task returns. Global state mutations
look small (a few files, one config entry) but their blast radius spans every Claude Code
session on this machine. Namespace collision, irreversibility, and cross-tool interference
are M-level risks even when the implementation is trivial.

**Step 1 — Size and route**

If the input is vague or multi-part: call `youk-core.optimize_intent(raw_input)` first.
Use the returned `problem` field as the task for route_task.

Call `youk-core.route_task(task)`. Extract:
- `size` (XS/S/M/L/XL) — override with M if Step 0 triggered
- `plan_hook` (may be empty)
- `skills` list
- `token_budget`

Call `youk-core.track_tokens(0, 0, "route_task", token_budget=<budget>)`

**Step 2 — Planning gate (M+ only)**

If `plan_hook` is non-empty: output it VERBATIM. Wait for one response.
- Silence or approval → proceed
- Redirect → update the task and re-route

**Step 3 — NFR check (M+ only)**

If size is M, L, or XL:
Call `youk-code.route_to_skill("nfr_check", task)`. Follow returned skill_content.
Answer the NFR questions yourself from context. This gate is non-negotiable.

If the tool call fails or returns an error: emit "nfr_check unavailable (MCP offline?). M+ task proceeding without safety gate — run `make -C ~/.claude/youk up` then re-run /build to restore the gate." Then continue to Step 4.

**Step 4 — Execute**

Call `youk-code.route_to_skill("dev-loop", task)`. Follow returned skill_content.

If route_task returned additional skills (e.g. security-review, write-spec): invoke
them in the order returned after dev-loop completes.

---

## Rules

- Never skip nfr_check on M+ tasks — it runs before a single line of code
- Never skip plan_hook output on M+ tasks — one redirect accepted, silence = proceed
- XS/S tasks: skip Steps 2 and 3, go straight to dev-loop — UNLESS Step 0 triggered
- If route_task surfaces soft rule warnings: state them once, then proceed
