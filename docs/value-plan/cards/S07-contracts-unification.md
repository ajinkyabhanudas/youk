# S07 Contracts unification

Size M. Depends: none. Status: todo. Metric: V1 (repeat-gap rate), V3.

**Goal.** One function returns the effective contracts, and every consumer uses it.

**Why.** Observed bug: the session brief printed "Pinned Contracts: none saved" next to "Active contract: ..."
because brief and plan read different sources. Loaders are duplicated in `compaction.py`, `youk_hook_utils.py`
(project and global), `pre_compact.py`, `session.py` (plan item) and `agent_host.py`.

**Load.** `servers/core/src/compaction.py` (`_load_contracts`), `plugin/scripts/youk_hook_utils.py`,
`plugin/scripts/pre_compact.py`, `servers/core/src/session.py` (around the "Active contract" line),
`servers/shared/agent_host.py`, `knowledge/default-contracts.md`, `config/guardrails.yaml`.

**Build.**
- `effective_contracts(slug)`: global plus project, deduped, in `servers/shared/`. All consumers call it.
- Classify each contract `mechanical` (a command, a path rule, a branch rule) or `judgment`. Write the list to
  `knowledge/contracts-classified.json` (reviewed by hand). Mechanical ones feed S12 and S13.
- Remove the "Active contract" plan item (the brief carries contracts).
- Unify the correction phrase lists (done: `servers/shared/phrases.py`, guarded by `tests/test_phrases.py`).
- Fix `post_tool_use.py` reading `tool_result` where the host sends `tool_response` (done).

**Tests.** All consumers return identical lists for the same slug. Brief never says "none" when global contracts exist.

**Out of scope.** Compiling mechanical contracts into checks (S12).

**DoD.** Standard DoD.

**Kill criterion.** None (bug fix).

**Handoff.** Count of mechanical vs judgment contracts.
