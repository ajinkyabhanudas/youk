# S08 Replay battery

Size M. Depends: none. Metric: B.

**Goal.** A fixed, replayable set of real tasks with hidden tests, mined from Ajinkya's own git history.
This is the programmatic simulation: repeatable, many runs, no live-work dependency.

**Why.** Live A/B on one developer is slow and noisy. The battery gives n in days.

**Load.** Nothing from youk core. Needs repo paths for youk, stencil, canopy (config file `bench/repos.yaml`).

**Verify first.** Each repo has a runnable test command and a clean checkout at arbitrary commits.

**Build.** `scripts/sim/mine_tasks.py`:
- Candidate commits: touch both source and tests, at most 4 files and 200 diff lines, tests pass at the commit and fail at its parent (verified by running).
- `bench/tasks/*.yaml`: repo, parent sha, prompt (from the commit message with file names stripped), test command, hidden test files.
- Agent sees the parent checkout with the commit's tests removed. Success means those tests pass after the agent's change.
- Target 20 tasks across at least 3 repos; record language and size per task.

**Tests.** Miner on a fixture repo selects, rejects and verifies as specified.

**Out of scope.** Running agents (S10).

**DoD.** Standard DoD. Task list reviewed by Ajinkya for fairness (no task whose prompt gives the answer away).

**Kill criterion.** If fewer than 12 usable tasks exist, add another repo before S10.

**Handoff.** Task count by repo; known biases (bug-fix heavy, Python heavy).
