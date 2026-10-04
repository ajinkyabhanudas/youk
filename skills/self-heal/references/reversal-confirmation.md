# Reversal confirmation — naming domain/sub_domain (Phase C judgment call)

Read `docs/pattern-learning-architecture-design.md`'s "Phase C, precisely" section
first. `youk-core.detect_domain_reversals` (`servers/core/src/reversal_check.py`'s `detect_reversals`) is
purely mechanical: it rebuilds a project's Domain Brief, diffs it against the
known-sources ledger, and cross-references real dismissed `DispositionEvent` rows
by bounded_context keyword overlap. It returns plain `{dismissed_event,
new_invariant}` data — never a `PatternEntry`, and never a `domain`/`sub_domain`
guess, because it has no real basis to invent one. A diff between two Domain Brief
snapshots can detect THAT something changed; it cannot tell WHAT field of
knowledge the change belongs to.

Naming `domain`/`sub_domain` is the same category of judgment call as the
per-task domain-scope step in `skills/nfr-check/SKILL.md` (CIR-165): read the
actual real text, decide, justify in one sentence. Do not consult or build a
fixed topic→domain lookup table — that degenerates into the exact mistake CIR-165
already caught and corrected once.

## When this runs

`detect_reversals` is periodic, not real-time (see the design doc's own data-flow
diagram) — there is no live request this plugs into, unlike Phase B's
real-time `nfr-check` CLASSIFY wiring. Run it as part of self-heal's AUDIT phase
(`self-heal/SKILL.md` Phase 1), once per project with a real Domain Brief, before
concluding the audit found "no recurring gaps."

The two steps are MCP tools in youk-core, like every other self-heal call:
`youk-core.detect_domain_reversals(project)` returns the pairs, and
`youk-core.confirm_domain_reversal(reversal, domain, sub_domain, project)`
records one. An agent host without Python access to the repo can run both.

## Required format

For each real pair `detect_domain_reversals` returns, output exactly this before calling
`confirm_domain_reversal` — never skip straight to confirmation:

```
[REVERSAL CONFIRMED]
dismissed: {dismissed_event.bounded_context} ({dismissed_event.source_id})
reversed by: {new_invariant.source_id}
domain: {domain} — {one-sentence reason this is the right field of knowledge for this pair}
sub_domain: {sub_domain} — {one-sentence reason this narrows it correctly}
```

Only after that block is written does `confirm_domain_reversal(reversal, domain,
sub_domain, project)` get called. An empty `detect_domain_reversals` result needs no block — move
on, same as self-heal's existing "no recurring gaps" exit.
