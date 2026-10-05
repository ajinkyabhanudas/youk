# S01 Footprint baseline and budget

Size S. Depends: none. Metric: V3.

**Goal.** Measure what youk puts in front of the model every session, and make growth fail CI.

**Why.** The ~11k-token always-on figure in the anchor is a chars/4 guess. Skill descriptions alone are
estimated at 8.4k. No budget exists, so the footprint only grows.

**Load.** `~/.claude/CLAUDE.md` (read only), `AGENTS.md`, `skills/*/SKILL.md` frontmatter,
`plugin/scripts/session_start.py`, one existing script test for style.

**Verify first.** Only the frontmatter `description` of each skill reaches the prompt (true in this
session's skill listing). If the host also injects skill bodies, add them.

**Build.**
- `scripts/footprint.py`: tokens per source (CLAUDE.md, AGENTS.md, skill descriptions, session brief,
  hook payloads). Use chars/4 and print "approx, +/-15%". If `anthropic` token counting is available offline, prefer it.
- Commit `bench/footprint-baseline.json` with current numbers.
- `tests/test_footprint_budget.py`: current total must not exceed baseline (ratchet). Lower the baseline whenever a card reduces it.
- `make footprint`.

**Out of scope.** Reducing anything. That is S11.

**DoD.** Standard DoD plus: baseline file committed, ratchet test fails when a skill description grows.

**Kill criterion.** None (diagnostic). Review when S11 lands.

**Handoff.** Paste the baseline table into the anchor's evidence section, replacing the estimates.
