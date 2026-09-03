---
name: doc-suite
rationale_why: "The 4-document product-portfolio phase (PRD, engineering doc, interview-prep, retrospective) only compounds if it runs in the same disciplined order every time. Running it ad hoc, from memory, is how the origin-interview gate and the standalone-PRD bar quietly get skipped under time pressure."
description: >
  Runs the full product-portfolio documentation phase for a project, end to end:
  PRD (write-spec system-prd mode) -> engineering doc -> product-sense/interview-prep
  doc -> retrospective. Writes all 4 files to ~/Desktop/Product-Portfolio-Docs/{project}/.
  Handles both ongoing projects (retrospective mode, grounded in existing code/ADRs/git
  history) and new projects (prospective mode, no build history to walk yet). Triggers
  on: "run the doc suite", "generate the product docs", "do the full PRD phase",
  "/doc-suite", any request to produce the complete 4-document set for a project rather
  than one document at a time. For a single document only, invoke write-spec directly
  with the relevant mode instead of this orchestrator.
---

# doc-suite — Product Portfolio Documentation Orchestrator

Sequences the 4-document phase that write-spec's `system-prd` mode and its siblings
produce, so it runs as one disciplined pass rather than four separately-remembered
invocations. This skill does not contain new document-writing logic of its own — it
is a sequencing and gating layer over write-spec's `system-prd` mode. Read
`write-spec/SKILL.md`'s `system-prd` mode in full before executing any phase below;
this skill assumes that mode's phases, tags, and quality bars and does not repeat them.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full 4-doc phase, mode auto-detected (see MODE DETECTION) |
| `retrospective` | Force retrospective mode even if the project looks early-stage |
| `prospective` | Force prospective mode even if code already exists |
| `resume` | Continue an existing folder — detect which of the 4 docs already exist and pick up from the next one, not from scratch |
| `prd-only` | Run Phase 0 and the PRD only, stop before the engineering doc |
| `project: [name]` | Target a specific project name/slug for the output folder |

---

## Mode detection (before Phase 0)

Check the target project for signs of an existing build: a git history with more than
a handful of commits, ADRs or an equivalent decision log, a working test suite. If
found, default to RETROSPECTIVE. If the project is a fresh idea with no code yet or
only scaffolding, default to PROSPECTIVE. State the detected mode in one line before
proceeding and let the developer override with `retrospective` or `prospective` if the
detection is wrong. Do not silently guess and proceed without stating the guess.

---

## Sequencing (the 4 phases, in fixed order)

### Phase 1 — PRD (`write-spec`, `system-prd` mode)

Invoke write-spec's `system-prd` mode directly, following every one of its phases,
including the mandatory Phase 0 origin interview. This is the highest-risk step in the
whole suite — do not compress or skip it to save time. If the developer has already
stated the origin, alternative, and real first user earlier in the conversation, restate
it back and confirm rather than re-asking, exactly as write-spec's Phase 0 specifies.

Write to `~/Desktop/Product-Portfolio-Docs/{project-slug}/01-PRD.md` (or the developer's
named location). Apply every quality bar from write-spec's `system-prd` mode without
exception, including the standalone-PRD bar: the PRD must fully support its own claims
without pointing to docs 2 through 4 for backup. Verify this explicitly before moving to
Phase 2 — reread the PRD as if the other three files didn't exist, and fix any section
that only earns its confidence because a sibling document backs it up.

Do not proceed to Phase 2 until the PRD passes write-spec's Phase 7 self-check
(origin check, measurability check, confusion check) with no `[SHALLOW]` verdict.

### Phase 2 — Engineering doc

Not a write-spec mode of its own — build this directly, grounded the same way the PRD
was: primary sources only (ADRs, commit history, architecture docs, the actual code),
tagged `[decided-before-build — see {source}]` or `[reconstructed]`, same voice rules
(no em-dashes, no "it wasn't X, it was Y," no theatrical framing, read-aloud test).

Structure: one section per major architecture decision, each stating the decision, the
real alternative considered, why not the alternative (the specific cost, not a vague
"more complex"), and — where the decision has a real before-and-after (a boolean fixed
into an unforgeable type, an assumption caught by an empirical check before shipping) —
tell that story specifically. A before-and-after correction is stronger interview and
engineering-judgment material than a clean first-time decision, and should be sought out
and surfaced, not buried under the cleaner decisions.

Close with a "known engineering gaps" section distinct from the PRD's Track A/B split:
restate the PRD's Track A (closeable by more engineering) items with their engineering
shape rather than business framing. Do not duplicate Track B here — that stays business-
framed in the PRD only.

Write to `02-engineering-doc.md` in the same folder.

### Phase 3 — Product-sense / interview-prep doc

Format: a rehearsal aid, not a summary. Structure as questions a sharp interviewer would
actually ask ("why does this exist," "what's your north star and why not X," "walk me
through a decision you'd reconsider," "what would you build next and why not the
impressive-sounding thing," "what's the biggest risk and is it an engineering risk,"
"what's a mistake you made and what changed because of it"), each with the honest,
specific answer grounded in docs 1 and 2 — not generic interview advice.

Include a section of exact numbers worth having ready (test counts, golden-set size,
measured precision/recall, panel size) with the caveat for each of what it does and
doesn't prove. Close with a one-line tone check: every answer should be sayable out
loud, not read as if from a slide.

Write to `03-product-sense-interview-prep.md`.

### Phase 4 — Retrospective

Mandatory once docs 1 through 3 exist. Two required sections, per write-spec's Doc 4
specification:

**Section A** — mistakes made constructing docs 1 through 3 *in this session*: every
real correction that happened while building them (a wrong inference caught, a section
that had to be rewritten, a framework applied before checking it fit, a ranking that
briefly included the wrong kind of item). For each: what the mistake was, the specific
structural reason it happened (not "I was imprecise" — the actual mechanism), and what
changed as a result. If genuinely nothing was corrected, say so — but audit hard before
concluding that, since a completely clean first pass is rare enough to be suspicious.

**Section B** — hindsight calls about the underlying system's own build, distinct from
anything the ADRs themselves already flag as a reversal trigger. Tag every entry
`[hindsight — not an ADR reversal trigger, a genuine "would have done differently" call]`.
Do not manufacture disagreement with a sound decision to fill this section.

Close with a numbered, direct action list: what changes next time. This is the section
a returning developer reads first.

Write to `04-retrospective.md`.

---

## Gates between phases (do not skip)

- **After Phase 1:** the standalone-PRD check must pass before starting Phase 2. A PRD
  that leans on the engineering doc for support is a defect to fix now, not something
  Phase 2 can retroactively excuse.
- **After Phase 2:** confirm every architecture decision cited in Phase 3's interview
  answers actually traces to something written in Phase 2 — no interview-prep answer
  should introduce a claim about the system that doc 2 doesn't already support.
- **Before Phase 4:** Phase 4 requires having actually lived through the construction of
  docs 1 through 3 in this session to write Section A honestly. If this skill is invoked
  in `resume` mode against docs written in a prior session with no memory of how they
  were built, say so directly and scope Section A to what can be verified by rereading
  the docs for internal inconsistencies, rather than fabricating a construction narrative
  that didn't happen in this session.

---

## Resume mode

When invoked with `resume` on a project folder that already has some of the 4 files:
detect which exist, state that back plainly ("found 01-PRD.md and 02-engineering-doc.md,
missing 03 and 04"), and continue from the next missing phase. Do not regenerate
existing files unless the developer explicitly asks for a redo of a specific one.

---

## What this skill does not do

It does not write code, does not run nfr_check or dev_loop, and is not a substitute for
/build. It produces documentation only. If the conversation drifts into "and now let's
build the correlation engine we found while writing Known Gaps," that's a separate /build
invocation, not part of this skill's scope — say so directly rather than silently
expanding scope mid-phase.
