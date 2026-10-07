# Claude Code mods and cross-session features: do they make youk redundant?

Checked 2026-10-06 against Anthropic's docs (code.claude.com), a field guide to the mods API and press coverage. The local Claude Code is 2.1.198; cross-session messaging needs 2.1.224 or later, so none of this was run here.

## What exists

- **Mods**: TypeScript function-hook plugins. Events include `session.start`, `prompt.submit`, `prompt.compose`, `tool.call`, `command.run`, `turn.complete`, `session.end` and UI draws. A hook can pass an event through, rewrite it, or answer it; it can deny a tool call, add text the model reads, register tools and commands, and call the model. State survives reloads (`$.state`) and sessions (`$.store`). Hot reload. Limits: no Node or file access, `$.process.run(argv)` with fixed arguments only, full engine access with no sandbox. Official docs have no mods page yet; the API summary comes from a third-party field guide that calls it early access.
- **Cross-session messaging** (2.1.224+): one session writes plain text to another live session. It is never conversation history or files; the docs say to use `/resume` to move context. Both sessions must be running; messages are held or dropped by the receiver's inbound setting.
- **Sessions**: `--continue`, `--resume`, resume from a summary, `/branch`, transcripts stored locally for 30 days by default.
- **Memory**: CLAUDE.md and auto memory, loaded every session (auto memory first 200 lines or 25KB), per repository. The docs say these are context, not enforcement, and recommend a PreToolUse hook to block an action.
- **Projects** (beta, Pro and Max): a stream of related tasks run as parallel cloud sessions sharing repositories, instructions and memory.
- **`/goal`**: keep working until a completion condition holds.
- **`claude plugin eval`**: runs eval cases against a plugin and adds a no-plugin baseline arm, reporting the score delta; defaults to 3 runs per case, with `--max-cost-usd` and a pass threshold. **`claude plugin details`** reports a plugin's component inventory and projected token cost.

## Overlap with youk

| youk part | Native equivalent | Verdict |
|---|---|---|
| Session resume pointer, brief | `--resume`, resume from summary, auto memory | Partial overlap. Native restores one conversation; youk derives the next task from a durable, project-scoped task graph, works on other hosts, and survives transcript expiry |
| "Cross-session handoff" | Messaging (live text only), `/resume` (whole context), Projects (cloud, beta) | Messaging is not a handoff store. Nothing native persists a task list between sessions that are not running. Do not build live messaging in youk |
| Contracts | CLAUDE.md, rules | Native is advisory. youk's value is the mechanical enforcement of the checkable ones; the official docs recommend exactly that |
| Gates | PreToolUse hooks, mods `tool.call` deny | Same mechanism. youk supplies the policy and the check logic |
| Hook runtime | Mods run in process | Real gain: youk's command hooks cost about 41 ms each from interpreter start. A mod removes the spawn, but cannot read files, so each gate decision would call out with `$.process.run` and give the saving back unless the state sits in `$.store` |
| Goal tracking | `/goal` | Overlap with the goal-anchor drift tracking; use native `/goal` where it covers the case |
| Battery harness, footprint | `claude plugin eval` with no-plugin baseline, `plugin details` | Strong overlap, and it already implements ablation, k=3 and a cost ceiling. Use it for plugin-level with/without runs; keep our replay tasks as the case source |
| Ledger, value report, evidence | none | Not covered. This is youk's differentiator |
| Cross-host core (Codex and others) | Claude Code only | Mods cannot be the core. A mod can only be an adapter, like the Codex one |

## Verdict

youk is not redundant, but a large part of its delivery layer is now native or soon will be. What remains distinct: a durable project task graph, contracts enforced in code, a measured-outcome ledger, and a host-neutral core. Pieces that duplicate native features (resume summaries, session naming, live messaging, goal tracking) should not be built or extended.

## What to do

1. Do not rebuild youk as a mod. Keep the Python core and treat a mod as an optional Claude-only adapter.
2. After S11 and S12, trial a thin mod: `prompt.compose` injects the lean context by task size, `tool.call` calls the Python gate. Compare its hook cost and G2 result with the command hooks.
3. Use `claude plugin eval` for the with/without-youk arm; use `claude plugin details` as a cross-check on the footprint number.
4. Upgrade Claude Code to 2.1.224 or later before relying on any of this, and read the mods API from the generated type definitions in a real mod, not from third-party summaries.
5. Reassess in a month: mods are early access, and the official mods page does not exist yet.

## Not verified

- Whether a mod can write files or call a local process cheaply enough to carry youk's gates.
- Whether cross-session messaging reaches a session that is not running (the docs say the target must have an inbox socket).
- Whether the user's installed version supports mods at all.
