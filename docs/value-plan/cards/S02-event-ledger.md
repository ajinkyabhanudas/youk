# S02 Event ledger core

Size M. Depends: none. Metric: enables V1 to V3 and B.

**Goal.** One typed, append-only event ledger that every later card writes to. Nothing is wired yet.

**Why.** Today there is no per-call trace. Model-reported skill logging produced 1 record in all sessions.
Without a ledger, "what delivers value" cannot be answered, and new components cannot be held accountable.

**Load.** `servers/shared/jsonl_lock.py`, `servers/shared/schemas.py`, `servers/core/src/observability.py`
(the `_ALLOWED_METADATA_KEYS` pattern), `docs/adr-011-trace-content-invariant.md`,
`tests/test_observability_privacy.py` (drift sentinel pattern).

**Verify first.** `locked_jsonl_append` is safe across processes (hooks and server write at once). Write a 4-process test before relying on it.

**Build.** `servers/shared/events.py`:
- `Event`: `v, eid, ts, session, task, arm, kind, name, status, ms, n, tok_in, tok_out`.
  `kind` in {tool, skill, gate, hook, correction, test, commit, outcome, session}. `status` in {ok, fail, block}.
- `emit(youk_root, event)` never raises. Writes `state/events/{slug}/{YYYY-MM}.jsonl`.
- Sanitizer: allow-listed keys only; rejects strings longer than 64 chars and anything that is not an enum, hashed id or number.
- `read_events(slug, since, kinds)` streams; dedupes by `eid`.

**Tests.** Allow-list drift sentinel, never-raises, multi-process append, dedupe, month sharding.

**Out of scope.** Hook or server wiring (S03, S04), reports (S05).

**DoD.** Standard DoD. Add the ledger itself to `system-map.yaml`.

**Kill criterion.** None (infra). If append latency exceeds 5 ms p95, switch the shard to SQLite WAL before building on it.

**Handoff.** Record the event schema version and kind list in the anchor.
