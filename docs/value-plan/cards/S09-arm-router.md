# S09 Arm router

Size M. Depends: S02, S03. Status: todo. Metric: enables arm comparison.

**Goal.** The SessionStart hook chooses what context to inject per arm, and every event carries the arm.

**Why.** CLAUDE.md is static, so arms must be switched by the hook. This also sets up the lean design:
a tiny CLAUDE.md that defers to the hook payload.

**Load.** `servers/shared/ab_experiments.py`, `plugin/scripts/session_start.py`, the `/session-start-hook` route in
`servers/core/src/server.py`, `servers/shared/agent_host.py`, `plugin/scripts/youk_hook_utils.py`.

**Verify first.**
- What a SessionStart hook can inject, and whether it overrides or adds to CLAUDE.md.
- `assign_variant` is two-arm; extend to three arms or run two experiments.
- PreToolUse gates can read the arm, so `bare` really runs ungated.

**Build.**
- Arm in {full, lean, bare}, assigned per session by hash, overridable by `YOUK_ARM`.
- `bench/arms/{arm}/context.md` injected by the hook. `bare` injects nothing but events still flow.
- Arm written into every event and the session record.

**Tests.** Deterministic assignment, override wins, bare disables gates, all events carry arm.

**Out of scope.** Writing the lean content (S11).

**DoD.** Standard DoD.

**Kill criterion.** If the hook cannot control injection, fall back to separate config dirs per arm (S10 already needs them).

**Handoff.** Record what the hook can and cannot inject.
