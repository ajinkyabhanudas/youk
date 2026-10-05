# S16 Skill pruning (time-gated)

Size S. Depends: S03 plus at least 20 real sessions of skill events. Metric: V3, usage.

**Goal.** Archive skills that data shows are unused, with Ajinkya's approval.

**Why.** 54 skills, ~88k words. Usage is unknown today. Zero audit mentions: `surface-options`, `overengineering-auditor`,
`survey`, `skill-forge`, `task-contract`, `simplify`. Overlap to review: `review`, `check`, `code-review`. This is a hint list,
not a verdict. The ledger decides.

**Load.** Output of `scripts/value_report.py` (skill fire counts), `skills/SKILL-REGISTRY.md`.

**Rule.** A skill is a candidate if it has zero fires in 30 days, is not in a gate chain, and did not contribute in any battery run.
Candidates go to Ajinkya as a list. Approved ones move to `skills/_archive/` (restorable). Nothing is deleted.

**Build.** `scripts/skill_prune_report.py` producing the candidate list; a restore command.

**Tests.** Rule applied to a synthetic ledger; archive then restore round trip.

**Out of scope.** Rewriting skills.

**DoD.** Standard DoD. Footprint ratchet lowered.

**Kill criterion.** None.

**Handoff.** Archived list and the footprint reduction.
