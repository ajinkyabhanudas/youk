# S14 Startup and pulse consolidation

Size M. Depends: S05. Metric: V3 (session_start ms, plan noise).

**Goal.** Session start does only what the session needs. Upkeep moves to CI or explicit commands.

**Why.** `start_session` runs doc freshness, doc data refresh, wiring pulse, file index and more on every start, and fills the plan
with housekeeping lines. Wiring orphans are static and belong in CI. Several overlapping health signals exist (wiring pulse,
pipeline pulse, doc sync, org score, self_heal, skill signals).

**Load.** `servers/core/src/session.py` (`start_session` sections), `wiring_pulse.py`, the pipeline pulse module,
`servers/core/src/doc_graph.py`, `servers/shared/events.py`, `scripts/value_report.py`.

**Build.**
- Measure `session_start` ms from events first and record the baseline.
- Wiring orphan check lives only in the S06 CI test; remove the startup call and the plan line.
- Doc data refresh and doc sync move to `make docs-refresh` and a pre-commit check.
- File index runs lazily or in the background, not on the start path.
- Plan keeps only actionable items; housekeeping goes to `/health`.

**Tests.** Start path calls none of the removed functions; plan has no PULSE or doc-sync lines; latency budget test.

**Out of scope.** Deleting health checks themselves.

**DoD.** Standard DoD. session_start p95 target set from the baseline (aim for half).

**Kill criterion.** None (simplification with a measured latency target).

**Handoff.** Before and after session_start ms.
