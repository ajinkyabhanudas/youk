# S13 Evidence packet

Size M. Depends: S03. Status: todo. Metric: V2.

**Goal.** Every M+ change ends with a deterministic, review-ready summary produced by code, not by the model.

**Why.** Developers name verification as the top bottleneck (96% do not fully trust AI code; reviewing it is the biggest delivery constraint).
Superpowers relies on a reviewer subagent. A code-computed packet costs no tokens and cannot be argued with.

**Load.** `servers/shared/events.py`, `plugin/scripts/post_tool_use.py`, `servers/core/src/project_detection.py`,
`servers/core/src/contract_verifier.py`, `servers/core/src/verification_contract.py` (check for overlap first).

**Verify first.** Whether `verification_contract.py` already runs checkers deterministically. If yes, reuse; if it is LLM-driven, keep separate.

**Build.** `servers/core/src/evidence.py`:
- Detect lint and test commands from CI config, then Makefile, then pyproject or package.json (matches the saved "read the project's CI config" contract).
- Run with timeout; capture exit codes and test counts.
- Diff stat versus declared task files (`active_task.json`); flag files outside scope, new skips or xfails, deleted tests, new TODOs.
- Digest of at most 6 lines shown to the user at stop or pre-commit; failures returned to the model as actionable lines.
- Emit an `outcome` event with packet fields (all scalars).

**Tests.** Fixture repos for Python and Node; flagged cases; timeout path; packet never blocks, only reports.

**Out of scope.** Fixing failures automatically.

**DoD.** Standard DoD.

**Kill criterion.** If first-pass acceptance does not improve over 20 live M+ tasks, reduce to test-run only.

**Handoff.** First-pass acceptance with and without the packet, with n.
