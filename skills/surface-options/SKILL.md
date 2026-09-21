---
name: surface-options
rationale_why: "challenge and adr both engage only after a direction already exists — challenge attacks an interpretation once one is picked, adr documents a choice once it's made. Neither one catches the moment before either exists: an ambiguous, open-ended, or judgment-call request where a real fork is being collapsed silently, with no visibility into what else was on the table."
description: >
  Fires on an ambiguous/open-ended/judgment-call request that has a real, unstated
  fork in it — surfaces 2-4 costed options plus a mandatory recommendation instead
  of picking one silently. Produces: a short options list (what each option is, its
  real cost/tradeoff, what's lost by not choosing it) and exactly one named
  recommendation with a stated reason. Triggers on: a request with a genuine open
  design/scope/approach choice not yet resolved this session ("should we...",
  "how should this work", "what's the best way to..."), or explicitly "surface the
  options" / "what are my options here". Do NOT trigger when: the direction is
  already explicitly confirmed by the user this session (that fork is closed, not
  open), the task is XS/S with no real branching path, or the "choice" only has one
  sane answer (no real fork — that's not ambiguity, it's a rhetorical question).
  Do-not-trigger-on (disambiguation from `challenge`): a request already committed
  to a specific interpretation, where the open question is whether that
  interpretation is *right* — that is challenge's surface ("is this the right
  problem?"), not this skill's ("which of these real paths do we take?"). If both
  could plausibly fire on the same request, challenge runs first — it can dissolve
  the fork entirely (wrong problem framing) before this skill would waste a
  recommendation on a fork that shouldn't exist. Never fire both on the same
  request in the same turn.
---

# surface-options — Decision Surface

Silently picking a direction on an open fork is a decision the user never got to see.
This skill exists to make that fork visible before it's collapsed — not to slow
everything down, only the requests that actually have one.

Interruption budget: at most once per real fork. Once a fork has been surfaced and the
user has picked (or the assistant has proceeded on a stated default), that fork is
closed for the rest of the session — do not re-surface it, do not re-litigate it, and
do not surface a second, unrelated fork in the same turn unless the user asks for more
than one decision at once.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full: DETECT → SURFACE → RECOMMEND |
| `quick` | DETECT + SURFACE only, skip the full cost breakdown per option (name + one-line tradeoff each), still ends with a mandatory recommendation |
| `silent` | Run DETECT internally; if no real fork exists, proceed with no output. If a real fork exists, this mode does NOT suppress it — an undisclosed fork is exactly what this skill exists to prevent, unlike `challenge`'s `silent` mode which can hold LOW findings back |

---

## Context Capture (Always First)

```
TASK:              [the request, verbatim or paraphrased]
CANDIDATE_FORK:    [the specific open choice this skill thinks exists]
ALREADY_DECIDED:   [any fork the user already closed this session — do not reopen]
REVERSIBILITY:     [easy / hard / very hard — independent of STAKES, see Phase 3]
STAKES:            [low / medium / high — cost of picking wrong and having to redo]
```

`ALREADY_DECIDED` is not conversation-only: before DETECT, check `contracts.md` (the same
file `challenge`/session_end already write explicit agreements to) for a closed fork
matching this one. A fork closed earlier in a session that later hits a compaction
boundary, or is picked back up in a new session, must not silently reopen just because
the conversation context that closed it is gone — that is precisely the "contracts survive
via files, not conversation" failure this codebase has already been burned by once. If a
real fork's resolution is worth protecting from re-litigation across a session boundary,
write it to `contracts.md` in Phase 3, not left to live only in this turn's context.

If `CANDIDATE_FORK` turns out not to be real once DETECT runs (see Phase 1's veto), stop
here and proceed with the task directly — do not force a surfaced list where none is
warranted.

---

## Phase 1 — DETECT

`[PHASE: DETECT]`

1. State the candidate fork in one sentence: what are the genuinely different paths this
   request could go, phrased as an actual question ("in-memory cache vs. Redis", "fix the
   symptom here vs. the root cause upstream").
2. Veto check — a fork is NOT real if any of these hold: only one option is actually sane
   given stated constraints; the user already picked this fork earlier in the session;
   the "options" are cosmetic variations of the same approach, not substantively different
   costs/outcomes. If the veto check fires, stop — this is not a surface-options case,
   proceed with the task directly.
3. If real: name each option candidate (2-4, never more — more than 4 means the fork
   isn't scoped tightly enough, split it).

> Compact phase summary: "Fork: {one sentence}. {N} real options identified, or VETOED: {reason}."

---

## Phase 2 — SURFACE

`[PHASE: SURFACE]`

For each of the 2-4 real options, state:
- **What it is** — one sentence, concrete, not "the flexible approach."
- **Cost** — real cost in the units that matter here (time, tokens, irreversibility,
  maintenance burden) — never "cheap" or "expensive" unqualified.
- **What's lost by not choosing it** — the real thing forfeited if this option is
  skipped. If nothing meaningful is lost, that's evidence this isn't a real option
  (revisit Phase 1's veto).

In `quick` mode: name + one-line tradeoff per option, skip the full three-part breakdown.

> Compact phase summary: "{N} options surfaced: {short names}."

---

## Phase 3 — RECOMMEND

`[PHASE: RECOMMEND]`

1. Name exactly one recommended option. A neutral list with no pick is not this skill's
   output — surfacing options without a recommendation just moves the silent-decision
   problem onto the user with extra steps.
2. State the reason in one sentence, tied to `STAKES` and the real costs from Phase 2 —
   not "it's generally better."
3. **Proceed-vs-wait uses REVERSIBILITY, not STAKES alone.** A fork can be low-effort but
   very-hard-to-reverse (delete vs. archive; a public-facing rename; anything that ships
   externally) — STAKES alone would call that "low" and auto-proceed, which is wrong. Wait
   for explicit confirmation whenever `REVERSIBILITY` is hard or very hard, regardless of
   how low-effort the fork looked. Only proceed on the recommendation without waiting when
   BOTH stakes are low/medium AND reversibility is easy.
4. If this fork is worth protecting from silent re-litigation later (a real, recurring
   decision point, not a one-off), write the closed fork to `contracts.md` — the same
   mechanism `ALREADY_DECIDED` reads from. A fork resolved only in this turn's output and
   never written down is not actually closed past this session.

> Compact phase summary: "Recommend: {option}. Reason: {one line}. {Proceeding / Waiting for confirmation — reversibility: {easy/hard/very hard}}."

---

## Quality Bars (Non-Negotiable)

- **Every surfaced list ends with exactly one recommendation.** A list with no pick, or
  with "it depends," fails this skill's entire purpose.
- **The veto check is not optional.** Running SURFACE on a fork that fails Phase 1's
  veto manufactures ambiguity that was not real — this is as much a failure as silently
  picking a real fork.
- **At most 4 options, at most once per real fork.** A 5th option means the fork isn't
  scoped; a second surface of the same fork means the interruption budget was violated.
- **"What's lost by not choosing it" must be real, not filler.** If an option has
  nothing genuinely lost by skipping it, it should not have been listed as an option.
- **Never re-litigate a fork the user already closed this session — or a prior one.** Check
  `ALREADY_DECIDED` against `contracts.md`, not only conversation context, before DETECT
  runs — a fork closed before a compaction or in an earlier session must stay closed.
- **Reversibility gates auto-proceed, stakes alone never does.** A low-stakes-looking fork
  that is hard or very-hard to reverse always waits for explicit confirmation, even when
  Phase 2's cost breakdown made it look cheap.

### Hiring Validation

1. **Veto discipline:** given "should I name this function `getUser` or `get_user`" in a
   Python-only codebase with an established convention, this skill vetoes — one option is
   not sane given the stated constraint, this is not a real fork.
2. **Mandatory recommendation:** given a genuine fork (in-process cache vs. Redis for a
   single-process app with no restart requirement), this skill never ends with "both are
   valid, your call" — it names one and says why.
3. **Interruption budget respected across a session boundary:** given the user said "let's
   use Postgres" in a prior session, and that agreement was written to `contracts.md`, a
   later task in a new session touching the database does not re-surface
   Postgres-vs-alternative as an open fork — this must hold even though the conversation
   that closed it is gone.
4. **Reversibility overrides a low-stakes read:** given a fork like "delete these unused
   files vs. archive them" — low effort either way — this skill does not auto-proceed on
   "delete" just because STAKES looked low; it waits, because reversal is hard once deleted.
5. **Disambiguation from challenge holds:** given a request that could plausibly trigger
   both skills ("should we restructure this module?"), this skill does not fire alongside
   challenge in the same turn — challenge runs first to confirm the problem framing itself
   is right before this skill would surface paths for solving it.
6. **Scope discipline:** given a fork with 6 candidate options, this skill collapses or
   splits them to 4 or fewer rather than listing all 6.
7. **Real cost, not filler:** every "what's lost" line names a specific, concrete forfeit
   — never a generic "less flexibility" with nothing behind it.

---

## Example Flows

**A genuine open fork:**
> "We need to store session state — what's the best way to do this?"

DETECT: fork = "in-process dict vs. Redis vs. SQLite for session state." Veto check:
none apply — genuinely different cost/durability tradeoffs. 3 real options.
SURFACE: in-process dict (zero infra, cost: state lost on restart) / Redis (survives
restart, cost: new infra dependency + ops burden) / SQLite (survives restart, cost:
none — already a project dependency, slight latency vs. in-process).
RECOMMEND: SQLite — survives restart like Redis, zero new infra cost unlike Redis,
already a dependency. Proceeding (medium stakes, easy to reverse — swapping the storage
backend later touches one module).

**A manufactured non-fork (veto fires):**
> "Should I use a for loop or manually unroll it 50 times to sum this list?"

DETECT: candidate fork stated, but Phase 1 veto fires — only one option is sane, this
isn't a real tradeoff. `[PHASE: DETECT] VETOED: not a real fork, proceeding directly.`
No SURFACE, no RECOMMEND — just do the task.

**Already-decided fork, correctly not reopened across a session boundary:**
> `contracts.md` has "Postgres for storage" from a session 9 days ago. Now: "add a table for X."

DETECT: ALREADY_DECIDED check against contracts.md finds "Postgres for storage" — this
candidate fork is closed, and it survived the gap between sessions because it was written
to a file, not left in conversation context that no longer exists. Proceed directly.

**Reversibility overrides a low-effort read:**
> "Should I delete these three unused files or move them to an archive folder?"

DETECT: fork = "delete vs. archive," genuinely different outcomes. SURFACE: delete (cost:
zero disk use, lost: unrecoverable if wrong) / archive (cost: some clutter, lost: nothing —
fully reversible). RECOMMEND: archive — the disk-space savings from deleting are trivial
compared to the cost of being wrong. Reversibility: very hard for delete, easy for archive
— WAITING for confirmation even though this looked like a low-stakes, low-effort choice.

**`quick` mode:**
> "quick: should this endpoint be sync or async?"

DETECT: real fork (blocking I/O inside vs. not). SURFACE (quick): sync (simple, blocks
under load) / async (more complex, scales under concurrent load). RECOMMEND: depends on
real traffic pattern — name the one that fits the stated/observed load, one line.
