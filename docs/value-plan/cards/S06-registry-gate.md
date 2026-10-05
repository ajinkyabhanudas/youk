# S06 Registry completeness gate

Size M. Depends: S02. Status: todo. Metric: traceability of anything new.

**Goal.** CI fails if a new tool, skill, hook or gate is not registered and traceable. This is the rule that keeps
the system honest as it grows.

**Why.** The registry covers 32 stages of 3 subsystems. 18 have no real log, 3 never fired. The wiring pulse
checks name reachability only and runs on every session start.

**Load.** `docs/system-map.yaml`, `tests/test_system_map.py`, `scripts/system_status.py`, `scripts/host_inventory.py`,
`servers/core/src/wiring_pulse.py` (reuse `_defined_tools`).

**Build (as shipped).**
- A stage declares how it is observed: `real_log`, or `emits` (ledger kinds), or `untraced_reason`. A test requires one and rejects both.
- Other surfaces are covered by rule, not by 86 hand entries: tools by the server-span wrapper (a test asserts every registered tool is wrapped), gates by `tool_spans.GATE_CHECKS`, skills by the usage tap matching `Skill`, hooks by a registry entry per script.
- The 24 stages with no log now say why (pure function, read-only, session output logged elsewhere) or what they emit. Nothing was deleted: the registry's value is the deterministic-versus-judgment label, and a pure function legitimately has no log.
- The wiring orphan check runs in CI (`TestOrphans`) against the shipped CLAUDE.md template. S14 removes it from session start.
- `system_status.py` reports a `traced via the event ledger` state and shows the reason for untraced stages.

**Tests.** Adding a tool without an entry fails; entry without emit fails; the shipped registry passes.

**Out of scope.** Rewriting stage logic.

**DoD.** Standard DoD. Registry count and list of deletions recorded in the anchor.

**Kill criterion.** None (gate).

**Handoff.** List removed stages and why.
