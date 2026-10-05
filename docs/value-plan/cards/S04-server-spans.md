# S04 Server spans and gate events

Size M. Depends: S02. Metric: V3, gate compliance.

**Goal.** Record what only the server knows: internal latency, gate transitions, task lifecycle.

**Why.** Hooks see calls from outside. Gate state (challenge, nfr, unblocked, done) lives in `task-graph.db`
and needs to be an event stream to answer "did the ceremony change outcomes".

**Load.** `servers/core/src/server.py` (registration area only), the task-graph module behind `set_gate` and `mark_task_done`,
`servers/core/src/routing.py`, `servers/shared/events.py`, `tests/test_mcp_tool_contracts.py`.

**Decide at start.** Avoid double counting with S03: server spans carry `src=server` and only record latency
and errors for tools; hooks own the call counts. Gate and task events come from the server only.

**Build.**
- One wrapper at tool registration (no per-tool edits) that records ms and status.
- `gate` events from `set_gate`, `check_*_gate` (cleared, blocked).
- Task lifecycle events keyed by the task-graph id: start, size, done, commits.
- Task id propagated into every later event in that session.

**Tests.** Extend `test_mcp_tool_contracts.py` so every registered tool is covered by the wrapper. Gate transitions emit exactly one event.

**Out of scope.** Removing legacy gate JSON files (S12).

**DoD.** Standard DoD.

**Kill criterion.** If wrapper overhead exceeds 2 ms p95 per call, sample instead of recording all.

**Handoff.** Note the task id format.
