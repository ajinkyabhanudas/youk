# S17 Portable install and lean pack

Size M. Depends: G2. Metric: time to first value.

**Goal.** A new user gets the lean arm in about 60 seconds with no Docker, unless S15 concluded otherwise.

**Why.** Superpowers installs from a marketplace in one command on 15+ agents. youk needs Docker plus `make install`.
Install friction is a market constraint, not a nice-to-have.

**Load.** `plugin/` tree, `scripts/install.sh`, `docs/youk-lite.md`, `docs/getting-started.md`, `bench/arms/lean/`, the S15 ADR.

**Build.**
- Package the lean arm (hooks, minimal context, essential skills) as a plugin.
- Generate `youk-lite` from the lean arm so both stay in sync.
- Clean-machine install test (fresh container) with a stopwatch in CI.

**Tests.** Fresh-container install reaches a working session; uninstall is clean.

**Out of scope.** Team features.

**DoD.** Standard DoD. Install time recorded.

**Kill criterion.** If install exceeds 5 minutes on a clean machine, fix before any public claim.

**Handoff.** Install time and supported hosts.
