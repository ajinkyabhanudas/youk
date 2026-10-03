# Pattern promotion — choosing the representative statement (Phase D judgment call)

Read `docs/pattern-learning-architecture-design.md`'s "Phase D, precisely" section
first. `servers/core/src/pattern_promotion.py`'s `find_promotion_candidates(root)`
is purely mechanical: it groups real `status: confirmed` `PatternEntry` rows by
exact `(domain, sub_domain)` equality, keeps only groups spanning >=2 distinct
projects, runs the existing `abstract_claim()` on every entry's statement, and
drops the whole group if any result has `confident: False`. It returns real groups
with every member's abstracted statement attached — it never picks which one
represents the group, because it has no real basis to prefer one project's wording
over another's.

Picking the representative statement is the same category of judgment call as
Phase C's domain/sub_domain naming (`reversal-confirmation.md`) and the per-task
domain-scope step in `skills/nfr-check/SKILL.md` (CIR-165): read the actual real
text, decide, justify in one sentence. Do not build a scoring function over the
candidate statements — that degenerates into the same invented-similarity mistake
the design doc already rejected for the matching key itself.

## When this runs

Same periodic cadence as Phase C's reversal check (see the design doc's own
data-flow diagram) — run it as part of self-heal's AUDIT phase
(`self-heal/SKILL.md` Phase 1), after the reversal check step, once per run across
all projects' confirmed patterns (not scoped to a single project — promotion is
inherently cross-project). Wiring this behind a dedicated MCP tool is deliberately
left to a later phase, same precedent as Phase C's own deferred MCP-tool wiring and
the design doc's "A2A: relevant to design for, not to build" section. Until that
tool exists, this step is run by directly invoking the Python functions for the
repo root; do not block on the MCP wiring to follow this step.

## Required format

For each real group `find_promotion_candidates` returns:

- If `len(set(group["abstracted_statements"])) == 1`: the choice is trivial — every
  member abstracted to the same wording. Use that wording as `chosen_statement`
  with no further reasoning required, and call `promote_group(group,
  chosen_statement)` directly.
- If there is more than one distinct abstracted wording, output exactly this
  before calling `promote_group` — never skip straight to promotion:

```
[PROMOTION CANDIDATE]
domain: {group["domain"]} / sub_domain: {group["sub_domain"]}
projects: {sorted(group["projects"])}
candidates:
  - ({entry.provenance[0]["project"]}) {abstracted_statement}
  - ({entry.provenance[0]["project"]}) {abstracted_statement}
  ...
chosen: {chosen_statement} — {one-sentence reason this wording best represents the general pattern across all listed projects}
```

Only after that block is written does `promote_group(group, chosen_statement)` get
called. An empty `find_promotion_candidates` result needs no block — move on, same
as self-heal's existing "no recurring gaps" exit.
