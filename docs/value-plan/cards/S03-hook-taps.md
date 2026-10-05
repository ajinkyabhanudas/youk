# S03 Hook taps

Size M. Depends: S02. Metric: V1, V3 inputs.

**Goal.** Capture usage mechanically from hooks, with no cooperation from the model.

**Why.** Hooks see every tool call. Model-reported logging fails (1 skill record ever). Corrections,
test results and commits are the raw material for V1 and V2.

**Load.** `plugin/hooks/hooks.json`, `plugin/scripts/{pre_tool_use,post_tool_use,user_prompt_submit,session_start,youk_hook_utils}.py`,
`servers/shared/events.py`.

**Verify first.**
- PostToolUse can match the `Skill` tool and the payload carries the skill name.
- A Stop (or equivalent) hook exists for session end events.
- Bash tool responses expose an exit code in the hook payload.
- Python hook start-up cost; measure ms per call before adding more hooks. If a dispatcher script is needed, build one.

**Build.**
- `tool` events for matched tools (name, ms, status). `skill` events from the Skill tool.
- `test` events when a Bash command matches known runners (pytest, ruff, npm test, go test, cargo test). Store runner enum and exit code only.
- `commit` events on `git commit` success.
- `correction` events from deterministic regex on the user prompt: contract phrases (`_CONTRACT_PHRASES`) and revert/undo/wrong-approach phrases. Store the enum, never the text.
- `session` open and close events.
- Record each hook's own latency in `ms`.

**Tests.** Fixture stdin payloads map to expected events. Any exception inside a hook still exits 0.

**Out of scope.** Server-side events (S04), reports (S05).

**DoD.** Standard DoD. Hook p95 at or under 50 ms, or a documented reason and a plan.

**Kill criterion.** A tap that produces no event in 10 real sessions is removed.

**Handoff.** Record measured hook p95 and which verify-first items held.
