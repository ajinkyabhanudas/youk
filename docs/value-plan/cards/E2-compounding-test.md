# E2 Compounding test

Size L. Depends: E1, S11. Metric: V1, compounding.

**Goal.** Measure whether youk's memory and contracts make later tasks in a project easier, which no one-shot battery can.

**Why.** SWE-Bench-CL and SWE Context Bench score chronological task sequences (forward transfer, forgetting). VibeMemBench found most memory systems fail to beat memory-off, mainly from volume and form. youk's brief is a memory system and has the same risk.

**Build.**
- Sequences of 4 to 6 related tasks per repo in commit order, mined with the same verification.
- Arms per sequence: memory off (bare), youk memory on (brief and contracts accumulating across the sequence), irrelevant-text control (same brief length, unrelated content).
- Metrics: pass rate, tokens and steps per task, repeated corrections on the same topic, forward transfer (later-task gain over memory off).
- Memory injected compressed and gated by task size, per the lean design.

**Verify first.** youk can carry state between runs inside the harness (its project slug and task graph persist across the sequence within one battery root).

**Kill criterion.** If memory on does not beat the irrelevant-text control, the brief's content is not the cause of any effect; cut it back.

**Handoff.** Per-sequence table and the forward-transfer estimate with interval.
