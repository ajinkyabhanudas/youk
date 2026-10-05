# S06 Registry completeness gate

Size M. Depends: S02. Status: todo. Metric: traceability of anything new.

**Goal.** CI fails if a new tool, skill, hook or gate is not registered and traceable. This is the rule that keeps
the system honest as it grows.

**Why.** The registry covers 32 stages of 3 subsystems. 18 have no real log, 3 never fired. The wiring pulse
checks name reachability only and runs on every session start.

**Load.** `docs/system-map.yaml`, `tests/test_system_map.py`, `scripts/system_status.py`, `scripts/host_inventory.py`,
`servers/core/src/wiring_pulse.py` (reuse `_defined_tools`).

**Build.**
- Generator lists every `@mcp.tool`, skill, hook and gate; the test requires a registry entry for each, with
  `grounding` and `emits` (an S02 event kind, or `diagnostic: true` plus a reason).
- Resolve the 18 no-log stages. Default: delete the stage if nothing consumes it; otherwise add its emit.
- Remove `servers/core/src/domain_edge_case_review.py` (117 lines, referenced only by a design doc) unless a consumer turns up.
- Move the orphan check from every-session startup to this CI test (the S14 card finishes the removal from startup).

**Tests.** Adding a tool without an entry fails; entry without emit fails; the shipped registry passes.

**Out of scope.** Rewriting stage logic.

**DoD.** Standard DoD. Registry count and list of deletions recorded in the anchor.

**Kill criterion.** None (gate).

**Handoff.** List removed stages and why.
