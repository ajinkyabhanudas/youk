# S11 Slim always-on

Size M. Depends: S01, G1, E1. Metric: V3, B (noninferior).

**Goal.** Cut what is loaded every session without losing results. This builds the `lean` arm's content.

**Why.** Context files raised cost 20%+ for ~0-4% gain in the AGENTS.md study. Compliance falls as instruction count rises.
Two "skills" (`compaction`, `session`) are internal dev notes that cost listing tokens and trigger nothing.

**Load.** `~/.claude/CLAUDE.md`, `skills/*/SKILL.md` frontmatter (bulk edit), `docs/claude-md-template.md`,
`bench/arms/lean/`, `bench/footprint-baseline.json`.

**Design rules from the research** (`research-eval-design.md`, findings 5 and 6):
- The lean context holds only rules that are non-inferable from the repo, project-specific, and checkable. No repository overviews, no restating what the model already does.
- Start minimal and add a line only for an observed, repeated failure.
- Brief injection is gated on task size: XS and S get none. Items are short and compressed, never transcripts.
- Judge lean against full on both task tiers from E1, not on small tasks alone.

**Build.**
- Lean context at or under 15 lines, hook-injected; global CLAUDE.md reduced to a pointer.
- Skill descriptions at or under 25 words each; keep the "do not trigger on" clause as one short phrase.
- Move `compaction` and `session` to `docs/internal/` (not skills).
- AGENTS.md at or under 10 lines. Update the CLAUDE.md template.
- Run the battery: lean vs full. Bisect by component if lean loses.

**Tests.** Footprint ratchet lowered; skill frontmatter lint (word limit); template matches lean.

**Out of scope.** Changing gate logic (S12).

**DoD.** Standard DoD. Always-on at or under 3k tokens (brief under 1k).

**Kill criterion.** Any trimmed element that drops pass rate by more than 5 points (interval excludes zero) is restored.

**Handoff.** Before and after footprint table; battery result.

**Status (2026-10-06).** Build done: always-on 1,932 tokens, target 3,000. G2 pass-rate check outstanding (needs E1). The full arm's text is frozen in `bench/arms/full/CLAUDE.md`.
