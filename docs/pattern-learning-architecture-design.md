# Pattern-learning architecture: precedence, schema, and guardrails

> Anchor document. Every phase below must re-read this file before starting,
> and name explicitly if its implementation diverges from what's written
> here — same discipline as docs/problem-space-modeling-design.md, which
> this initiative builds directly on top of.

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
- Phase C: the periodic reversal check -- re-run Domain Brief's own
  extractor, diff new entries against open `candidate`/`dismissed` rows,
  promote a real match to `confirmed` in the existing reactive
  pattern-library.
- Phase D: the global store + the promotion function (>=2 projects,
  abstraction-enforced) + the query function Domain Brief consults when
  building any project's brief.
- Phase E: end-to-end real test -- not a synthetic demo, the same
  discipline as every phase before this.

Real progress tracked in `state/pattern-learning-architecture/progress.json`.
