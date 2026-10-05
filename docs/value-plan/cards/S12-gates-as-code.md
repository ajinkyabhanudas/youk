# S12 Gates as code

Size L (split S12a protocol, S12b legacy removal). Depends: G1, S10. Metric: V3, B, gate compliance.

**Goal.** The model no longer holds the 8-step routing chain. A hook enforces order, and each youk tool returns the single next required action.

**Why.** Rules that are deterministic and that the model skipped belong in code (a youk saved pattern). The routing chain is
dozens of directives in CLAUDE.md. State is also duplicated: legacy gate JSON files plus `task-graph.db`.

**Load.** `servers/core/src/routing.py`, the ceremony sequencer, `intake_gate.py`, `check_*_gate` in `server.py`, `set_gate`,
`plugin/scripts/pre_tool_use.py`, `config/guardrails.yaml`, `scripts/cleanup.sh`, `knowledge/contracts-classified.json` (S07).

**Build.**
- S12a: PreToolUse is the sole enforcer of ceremony order. Tool results carry `next` (one action or null). Arm-aware (bare ungated).
  Mechanical contracts from S07 compiled into `guardrails.yaml` checks.
- S12b: remove legacy gate JSON files and dual-state reads after verifying `task-graph.db` health (`make cleanup-gate-files`).
- Delete the prose routing steps from the lean context.

**Tests.** Out-of-order tool call is blocked with the right `next`; each compiled contract blocks its violation; no code path reads legacy gate files.

**Out of scope.** New gates.

**DoD.** Standard DoD. Gate-skip events are zero by construction in lean; pass rate not below S11 baseline.

**Kill criterion.** A gate that blocks in more than 20% of tasks without catching a defect (events plus outcome) is loosened or removed.

**Handoff.** Gate list with block counts from the ledger.
