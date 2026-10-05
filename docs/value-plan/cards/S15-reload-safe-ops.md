# S15 Reload-safe ops

Size L (investigate first, then implement). Depends: none. Status: todo. Metric: restart under load causes zero failed calls.

**Goal.** Restarting or updating youk-core never disrupts another running task.

**Why.** Observed 2026-10-05: a change could not be loaded because another task was using the shared youk-core server,
and a restart "might disrupt it". That is an operational scale limit today. Every pending code change is stuck behind it.
All youk state is files and SQLite, so a singleton Docker server may not be needed.

**Load.** `servers/core/src/server.py` (module-level state), `scripts/update.sh`, `scripts/com.youk.core-server.plist.tmpl`,
`Makefile` targets for build and update, `servers/core/src/state_paths.py`.

**Step 1 (timebox to one session, output is an ADR).**
- Audit in-memory state and singletons (call counters, caches) and what an in-flight call loses on restart.
- Check write paths for atomicity (SQLite WAL, temp-file-and-rename, locks).
- Options: (a) keep Docker singleton plus graceful drain and reload; (b) per-session stdio local Python, no Docker; (c) status quo.
- Pick one with a stated reason.

**Step 2.** Implement the chosen option. Include `make reload` that drains in-flight calls.

**Tests.** Restart while N concurrent clients call tools: zero failed calls, no state corruption.

**Out of scope.** Multi-machine deployment.

**DoD.** Standard DoD plus ADR in `DECISIONS.md`.

**Kill criterion.** If (b) is chosen, Docker artifacts are removed in the same change, not left behind.

**Handoff.** ADR link; whether the install path changes (feeds S17).
