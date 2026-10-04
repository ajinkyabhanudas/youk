# Pattern-learning architecture: precedence, schema, and guardrails

> Anchor document. Every phase below must re-read this file before starting,
> and name explicitly if its implementation diverges from what's written
> here — same discipline as docs/problem-space-modeling-design.md, which
> this initiative builds directly on top of.

> **STATUS:** Phase C/D's wiring into `self_heal` was reverted: it
> duplicated `_detect_cross_project_patterns` -> `promote_to_global_contracts`,
> which already had 65 real entries against zero here. The "self-heal AUDIT
> phase" named below never existed in the live system. The functions remain
> real and tested with no live caller. `global-patterns.jsonl` is now backed
> by `promote_to_global_contracts` (`global_contracts.py`), not `promote_group`.

## The outcome this exists to serve

From the founder, verbatim, earlier in this session: youk should understand
a developer's problem space well enough to define edge cases and
boundaries *before* a mistake happens, and get better at this over time.
Everything below is justified only by whether it moves that outcome,
measurably -- not by whether it's an interesting thing to build.

## The three systems already in play, and why they're not one thing

1. **Domain Brief** (`servers/core/src/domain_brief.py`,
   `servers/code/src/domain_edge_cases.py`,
   `servers/code/src/domain_edge_case_review.py` -- problem-space-modeling
   Phases 1-3/6). Proactive: surfaces a candidate risk from a project's own
   *written* decisions, before the task is built. Per-project, built fresh
   each run from that project's own files.

2. **Youk's existing reactive pattern-library + skill-forge** (pre-existing,
   `state/verification-pattern-library.jsonl` is one real instance of this
   shape). Reactive: logs a pattern only *after* a real miss already
   happened. High precision by construction -- it only ever records
   something real -- but structurally cannot prevent a first occurrence.
   Confirmed this session: underused in practice, not necessarily broken in
   code (real gaps found this session were never fed into it).

3. **The disposition log** (not yet built -- this document's main subject).
   Tracks what actually happens to each Domain Brief candidate: accepted,
   dismissed, or ignored. This is the measurement layer discussed with the
   founder before this document -- without it, "try the mechanism on a real
   task" produces an anecdote, not evidence.

**Decided precedence and data flow** (the founder asked explicitly whether
these need to talk to each other -- answer: yes, but through one specific
bridge, not a mesh):

```
Domain Brief (1) --surfaces--> candidate shown to developer
                                      |
                                      v
                          disposition logged (3): accepted / dismissed / ignored
                                      |
                    (periodic, not real-time) reversal check:
                    did a dismissed candidate's invariant get violated
                    for real, evidenced by a NEW written decision/post-
                    mortem entry? (Domain Brief's own extractor already
                    re-reads DECISIONS.md-shaped files on every run --
                    a real post-mortem written up as a new decision entry
                    is automatically picked up next time (1) runs; no new
                    parsing machinery needed here)
                                      |
                                      v
                    confirmed reversal -> written into (2)'s EXISTING
                    pattern-library, not a new file -- (2) is the real,
                    already-built place for "a real, confirmed gap"
                                      |
                    (2)'s entries, once confirmed across >=2 PROJECTS
                    (not >=2 occurrences in one project -- that's just
                    (2) working normally within a project) -----> eligible
                    for promotion to a GLOBAL pattern store, after an
                    abstraction pass (reuse verification_contract.py's
                    abstract_claim(), CIR-157 -- strip proprietary
                    specifics before anything crosses a project boundary,
                    same precedent, don't build a second abstraction step)
                                      |
                                      v
                    global store, schema below -- consulted by (1) when
                    building ANY project's Domain Brief, surfaced as a
                    distinct, clearly-labeled category (never presented as
                    if it came from that project's own decisions)
```

No step above is invented infrastructure where a real, already-built
mechanism does the same job: reversal detection reuses Domain Brief's own
re-parse; promotion reuses `abstract_claim()`; the receiving end of a
confirmed pattern reuses the existing pattern-library file shape, extended,
not replaced.

## Schema (the part that has to be locked in reliably)

Real, existing constraint on this decision: ADR-009 in youk's own
`knowledge/projects/youk/decisions.md` already rejected Pydantic for state
validation, specifically because its default coercion silently accepts a
malformed write instead of raising. That decision stands here too --
**no Pydantic**. The resolution, consistent with that ADR and with what the
founder asked for (schema-based, something a tool can lock in reliably,
portable enough to matter for a future cross-boundary consumer):

- **Contract**: a committed JSON Schema file
  (`schemas/pattern-entry.schema.json`) -- portable, versionable,
  language-neutral (readable by a future non-Python consumer, including a
  future A2A-exposed endpoint, without this codebase's own dataclasses).
  This is the thing another system validates against.
- **Enforcement**: a Python `@dataclass` with `__post_init__` validation
  that raises on a malformed value, same shape as every other state model
  in this codebase already uses per ADR-009 -- never silent coercion.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://youk.dev/schemas/pattern-entry.schema.json",
  "title": "PatternEntry",
  "type": "object",
  "required": ["id", "schema_version", "scope", "domain", "sub_domain",
               "statement", "evidence_level", "provenance", "status",
               "created_at"],
  "properties": {
    "id": {"type": "string"},
    "schema_version": {"type": "string", "const": "1.0"},
    "scope": {"type": "string", "enum": ["local", "global"]},
    "domain": {"type": "string"},
    "sub_domain": {"type": "string"},
    "constraint_set": {
      "type": "array", "items": {"type": "string"},
      "description": "The conditions this pattern is actually known to apply under -- e.g. ['python', 'docker-multi-container']. Empty means unconstrained, stated explicitly, never implied by omission."
    },
    "statement": {"type": "string"},
    "evidence_level": {
      "type": "string",
      "enum": ["asserted", "internally_checked", "externally_verified"],
      "description": "Same vocabulary as verification_contract.py's SubClaim -- reused, not reinvented."
    },
    "provenance": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["project", "abstracted"],
        "properties": {
          "project": {"type": "string"},
          "source_file": {"type": "string"},
          "source_id": {"type": "string"},
          "abstracted": {
            "type": "boolean",
            "description": "True once abstract_claim() has stripped proprietary specifics. A global-scope entry with any provenance row abstracted=false is invalid -- enforced, not just documented."
          }
        }
      }
    },
    "confirmed_count": {"type": "integer", "minimum": 0},
    "status": {
      "type": "string",
      "enum": ["candidate", "confirmed", "promoted", "retired"],
      "description": "candidate: surfaced, no disposition yet. confirmed: a real reversal proved it mattered. promoted: confirmed in >=2 distinct projects, abstracted, eligible for global scope. retired: superseded or proven wrong -- kept, never deleted, for the same reason nothing in this codebase deletes a real record."
    },
    "created_at": {"type": "string", "format": "date-time"},
    "updated_at": {"type": "string", "format": "date-time"}
  }
}
```

This single schema shape serves all three systems above: a local Domain
Brief candidate is a `PatternEntry` with `scope: local`, `status:
candidate`; a reactive pattern-library hit is the same shape at
`status: confirmed`; a promoted cross-project finding is `scope: global`,
`status: promoted`. One schema, three lifecycle points -- not three
different ad hoc dict shapes that have to be kept in sync by hand.

### DispositionEvent -- a deliberately separate, lighter schema

Phase B needs to log what happens to a surfaced candidate (accepted /
dismissed / ignored) every time `nfr-check` surfaces one. This is NOT a
`PatternEntry` -- forcing it into that shape would mean inventing fake
`domain`/`sub_domain`/`evidence_level`/`provenance` values for something
that is, at the moment it's logged, just "a thing got shown and a human (or
the session) reacted to it." A `PatternEntry` is reserved for something
that has already cleared a real bar (confirmed by a reversal, or promoted
across projects); a `DispositionEvent` is the raw material that might one
day produce one.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://youk.dev/schemas/disposition-event.schema.json",
  "title": "DispositionEvent",
  "type": "object",
  "required": ["candidate_id", "project", "task", "bounded_context",
               "source_file", "source_id", "disposition", "timestamp"],
  "properties": {
    "candidate_id": {
      "type": "string",
      "description": "Deterministic, derived from (project, bounded_context, source_id, task) -- NOT a random uuid, so the same real candidate surfaced again for a similar task can be correlated without a lookup table."
    },
    "project": {"type": "string"},
    "task": {"type": "string"},
    "bounded_context": {"type": "string"},
    "source_file": {"type": "string"},
    "source_id": {"type": "string"},
    "disposition": {
      "type": "string",
      "enum": ["accepted", "dismissed", "ignored"],
      "description": "accepted: plan changed because of it. dismissed: explicitly judged irrelevant to this task. ignored: surfaced, no explicit call either way -- the default when nothing says otherwise, logged as its own real value, never silently omitted."
    },
    "timestamp": {"type": "string", "format": "date-time"}
  }
}
```

The relationship to `PatternEntry`, decided: a `DispositionEvent` with
`disposition: dismissed` is the thing Phase C's reversal check watches.
When a later real incident (a new decision/post-mortem entry Domain Brief's
own extractor picks up on its next run) proves that dismissal wrong, Phase
C constructs a REAL `PatternEntry` at that point -- `scope: local`,
`status: confirmed`, with `provenance` pointing at both the original
decision and the new incident entry -- and writes it into the existing
reactive pattern-library. The `DispositionEvent` itself is never promoted
or converted in place; it stays a flat, append-only record of what
happened, same discipline as every other append-only log in this codebase
(`events.jsonl`, the pattern-library itself).

Storage: `state/disposition-log.jsonl`, append-only, one real event per
line, never backfilled -- same precedent as every other JSONL file in this
initiative.

## A2A: relevant to design for, not to build

youk is public, MIT, domain-neutral (circaid's own ADR-C001 pins exactly
this). If the global pattern store matters, a different operator's youk
installation might eventually want to query or contribute to a shared
registry across an organizational boundary -- that is a real, legitimate
future shape, and it's what A2A (Agent2Agent protocol) is for.

It is not needed now: one operator, three local projects, no
cross-organization boundary exists yet. Building an A2A surface today would
be the same mistake already caught and corrected twice this session
(embeddings for a 6-row corpus, a fixed domain table) -- real infrastructure
built ahead of real need.

What's actually required now: don't paint this into a corner. The
promote/query functions for the global store must be plain functions with
a clear input/output contract (a `PatternEntry` in, a `PatternEntry` or
`list[PatternEntry]` out) -- never entangled with local file I/O in a way
that would force a rewrite to serve the same contract over a protocol
later. The JSON Schema above is the exact artifact an Agent Card or A2A
schema declaration would need; it already exists in a portable form for
that reason.

## Guardrails (decided now, enforced, not aspirational)

- **No Pydantic, no silent coercion** -- ADR-009, inherited directly, not
  re-litigated here.
- **No deletion** -- a `retired` entry stays on record. Matches this
  codebase's standing discipline (never backfill, never fabricate, and
  here: never erase a real finding because it turned out wrong).
- **No global-scope entry without `abstracted: true` on every provenance
  row** -- enforced in the dataclass's `__post_init__`, not just asserted
  in a docstring, so a malformed write raises instead of silently leaking
  project-specific content across a boundary.
- **No promotion below 2 distinct projects** -- a pattern confirmed once,
  in one project, is `confirmed`, not `promoted`. Promotion requires real
  cross-project recurrence, not a single strong signal dressed up as
  general.
- **No claim of improvement without the disposition log** -- standing from
  the prior conversation, restated here as an enforced rule: reporting
  "this is working" without pointing at real logged dispositions is not
  permitted.

## Phased build (resumable; read this document first, every phase)

- Phase A: the schema file + the dataclass + validation, with real tests
  proving the guardrails actually raise (malformed global entry, promotion
  below 2 projects, Pydantic absent).
- Phase B: the disposition log itself, per the `DispositionEvent` schema
  above -- append-only, real events only, wired to where Domain Brief
  candidates are actually surfaced (`domain_edge_cases.py` / `nfr-check`'s
  CLASSIFY phase). Not a `PatternEntry` -- see the schema section for why.
- Phase C: see "Phase C, precisely" below -- two real gaps had to be
  settled first (where `domain`/`sub_domain` come from, and the existing
  pattern-library's incompatible file shape), same discipline as
  `DispositionEvent` before Phase B.

### Phase C, precisely

**Gap 1 -- `domain`/`sub_domain` have no mechanical source.**
`DispositionEvent` doesn't carry them, and a diff between two Domain Brief
snapshots can detect THAT something changed, never WHAT field of knowledge
it belongs to -- that's a judgment call, same category as the per-task
domain-scope naming in Phase 5 (CIR-165). Decided: Phase C's mechanical
part only ever detects a reversal and surfaces it as plain data (no
`PatternEntry` yet); naming `domain`/`sub_domain` and actually constructing
the `PatternEntry` is a required skill-content reasoning step, not a
Python function guessing at a categorization it has no real basis for.

**Gap 2 -- the existing pattern-library file has the wrong shape.**
`state/verification-pattern-library.jsonl`'s real rows today are
`{claim_shape, missed_sub_claim, how_found, date}` -- not `PatternEntry`.
Writing `PatternEntry` JSON into that file would mix two incompatible
schemas in one JSONL, which defeats the entire point of Phase A (one
schema serving every lifecycle point). Decided: that file stays exactly as
it is, read-only, a historical record -- nothing in this codebase deletes
a real record. A new file, `state/confirmed-patterns.jsonl`, is where every
real `PatternEntry` at `status: confirmed` (from Phase C) or later
`status: promoted` (from Phase D) actually gets written. This new file is
"the reactive pattern-library" in `PatternEntry` terms going forward; the
old file's role is superseded, not merged into it.

**The real mechanical pieces (Phase C scope):**
1. `state/domain-brief-known-sources/{project}.json` -- every `source_id`
   Domain Brief has ever produced for that project, so a later run can
   tell a genuinely NEW entry from one that was always there.
2. `detect_reversals(project, root) -> list[dict]` -- rebuilds the brief
   fresh, diffs against the ledger for new source_ids, cross-references
   `disposition-log.jsonl`'s `dismissed` rows for that project by
   `bounded_context` match (same term-matching style as
   `domain_edge_cases.py`, reused, not reinvented), returns real
   `{dismissed_event, new_invariant}` pairs. Updates the ledger after.
   Returns `[]`, never a forced match, when nothing real changed.
3. A real function `confirm_reversed_pattern(reversal: dict, domain: str,
   sub_domain: str) -> PatternEntry` that the skill-content step calls once
   a human/session has named the judgment-call fields -- constructs the
   real `PatternEntry` (`scope: local`, `status: confirmed`,
   `evidence_level: internally_checked`, `provenance` citing both the
   original dismissed decision and the new reversing one) and appends it
   to `state/confirmed-patterns.jsonl`.
- Phase D: see "Phase D, precisely" below -- two real gaps settled first,
  same discipline as Phases B and C.

### Phase D, precisely

**Gap 1 -- `abstract_claim()`'s glossary is youk-specific.**
`servers/core/src/verification_research.py`'s `GLOSSARY` is hand-curated
for youk's own vocabulary (`claude code`, `mcp`, `paperclip`, ...). Calling
it on a circaid or canopy confirmed entry's statement will not recognize
their proprietary terms via the glossary -- but the function's own
`_IDENTIFIER_PATTERN` fallback already catches any identifier-shaped token
the glossary missed and sets `confident: False` rather than silently
guessing. Decided: Phase D reuses `abstract_claim()` completely unmodified
-- no glossary expansion, no second abstraction path -- and treats
`confident: False` as a hard refusal to promote. A pattern that can't be
abstracted with confidence stays `confirmed`, never reaches `promoted`.
This is the same shape as Phase A's existing "no un-abstracted provenance
row" guardrail, just enforced one step earlier.

**Gap 2 -- "the same pattern across projects" needs an honest key, not
invented similarity.** Two confirmed entries' `statement` text (real,
project-specific prose) will essentially never text-match across
projects even when they're conceptually the same gap -- inventing a
similarity score here would be the same mistake as every other "no
embeddings, no ML" decision already made in this initiative. Decided: the
matching key is exact equality on `(domain, sub_domain)` -- the same two
fields Phase C's skill-content step already requires a human/session to
name with justification for every confirmed entry. Two confirmed entries
from two distinct projects with the same `(domain, sub_domain)` pair are
the candidate group; which project's own abstracted statement best
represents the general pattern, when more than one is available, is
itself a judgment call (same category as naming domain/sub_domain in the
first place) -- not something a function should pick silently.

**The real mechanical pieces (Phase D scope):**
1. `find_promotion_candidates(root) -> list[dict]` -- reads
   `state/confirmed-patterns.jsonl`, groups `status: confirmed` entries by
   `(domain, sub_domain)`, keeps only groups spanning >=2 distinct
   `project` values in their provenance, runs `abstract_claim()` on every
   entry's `statement` in a group, and drops the whole group if any
   result has `confident: False`. Returns real groups with their real
   abstracted statements attached -- `[]` when nothing qualifies.
2. A skill-content step (same home as Phase C's `reversal-confirmation.md`,
   or a sibling reference -- implementer's call) that, for a real group
   `find_promotion_candidates` returns, picks which abstracted statement
   represents the pattern (trivial when there's only one distinct wording;
   a real choice, stated with reasoning, when there's more than one) and
   then calls `promote_group`.
3. `promote_group(group: dict, chosen_statement: str) -> PatternEntry` --
   builds the `provenance` list (every real entry in the group, each row's
   `abstracted` set to `True`, now legitimately true because
   `abstract_claim()` ran and was confident) and calls Phase A's existing
   `promote_pattern()` to get the actual guardrail enforcement (`>=2`
   distinct projects) for free, rather than re-checking it. Appends the
   result to `state/global-patterns.jsonl` (new file, same precedent as
   Phase C's `confirmed-patterns.jsonl` being separate from the old
   pattern-library).
4. `query_global_patterns(root, domain=None, sub_domain=None) ->
   list[PatternEntry]` -- reads `global-patterns.jsonl`, optionally
   filtered. Deliberately NOT wired into `DomainBrief`'s own dataclass
   (that's an already-shipped, tested schema; adding a field to it now is
   unnecessary risk for this phase). A caller gets global patterns as a
   separate, clearly-labeled list -- never silently merged into a
   project's own `bounded_contexts`, which are that project's own real
   decisions and nothing else. Wiring this query into the actual
   `nfr-check` candidate-surfacing flow (so a developer sees a labeled
   "global" hit distinctly from a "local" one) is explicitly deferred to
   a later integration step -- same honesty precedent as Phase C naming
   its own deferred MCP-tool wiring instead of hiding it.
- Phase E: see "Phase E, precisely" below.

### Phase E, precisely

Not a new mechanism -- every function Phase E needs already exists (Phases
A-D). This phase's entire job is proving the full chain actually composes,
using the real deployment shape rather than one isolated unit test per
function.

**The real deployment shape, stated explicitly because it matters for how
the test is built:** one youk installation tracks multiple projects'
Domain Briefs and confirmed patterns in the SAME root's `state/` directory
-- `confirmed_patterns_path(root)` and `global_patterns_path(root)` are
per-ROOT, not per-project; the `project` field on each row is what
distinguishes them. So a real cross-project promotion test uses ONE
shared `tmp_path` root with two real projects' `DECISIONS.md` copied into
it under their own project labels (e.g. `youk` and `circaid`'s real files,
copied, never fabricated prose) -- not two separate roots, which would
never let `find_promotion_candidates` see both.

**The full real chain to prove, in order:**
1. Copy two real projects' actual `DECISIONS.md` files into a shared
   `tmp_path`.
2. For each project: `build_domain_brief`, then `find_domain_edge_case_candidates`
   for a real task touching one of that project's real bounded contexts,
   then `append_disposition_event` with `disposition="dismissed"`.
3. Add a real-shaped reversing decision to BOTH projects' copied files
   (same shape as Phase C's own `_REVERSING_ENTRY` fixture).
4. `detect_reversals` for each project -- confirm each finds its real pair.
5. `confirm_reversed_pattern` for each, naming the SAME `(domain,
   sub_domain)` for both (the test's own deliberate choice, proving the
   cross-project match condition) -- confirm both land in the one shared
   `confirmed-patterns.jsonl`.
6. `find_promotion_candidates` -- confirm it finds the real 2-project group.
   `promote_group` -- confirm a real `PatternEntry` lands in
   `global-patterns.jsonl`. `query_global_patterns` -- confirm it reads
   back.

**The adversarial half, non-optional -- Phases C and D's own real bugs
were both found by testing the failure path, not the happy path:**
7. A second, parallel run of the same chain where one of the two
   reversing decisions contains a real proprietary-shaped identifier (same
   style as the `PaymentGatewayRetryHandlerV3` case that exposed the
   abstraction leak). Confirm `find_promotion_candidates` correctly
   refuses the WHOLE group -- nothing reaches `global-patterns.jsonl` from
   that run.
8. A third check: run the identical chain twice end-to-end and confirm
   idempotency -- the second run produces no duplicate rows anywhere
   (ledger, confirmed-patterns, global-patterns), consistent with every
   individual phase's own deterministic-id guarantee, now proven to hold
   when the whole chain runs twice, not just one function in isolation.

Real progress tracked in `state/pattern-learning-architecture/progress.json`.
