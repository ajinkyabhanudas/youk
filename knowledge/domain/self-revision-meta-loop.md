# ADR: youk is self-revising — one bidirectional meta-loop over enrolled judgment-sets

Decision locked 2026-08-05 (session #69). Foundational — this is youk's north star
("compound the developer's ability") turned inward: youk compounds ITSELF.
Generalizes and supersedes [[angle-basis-self-revision]] (now the first enrolled case).
Related: [[skill-trust-artifact]], [[reasoning-integrity]], [[tool-enforced-gates]].

## Principle

Make youk learn like a human: from watching (observing sessions), from doing (running
skills), and unlearn the bad when corrected — getting better without bloating. Every
enumerated set in youk that claims to be complete is an unchallenged wall. The 7-angle
basis was the first found. It is one instance of a pattern: human-written enumerations
asserting "these are all the cases," each able to be wrong, none with a path to
notice-and-revise itself.

The fix is NOT "make everything self-revising" (that IS the bloat). It is ONE
meta-capability — a bidirectional self-revision loop — built once, applied only to sets
that legitimately encode a revisable JUDGMENT.

## The crux: revisable vs frozen (explicit opt-in, default frozen)

A set is enrolled in the loop ONLY by explicit registration with a revision policy.
Default = frozen. Nothing self-revises unless deliberately marked.

## Enrollment is THREE distinct decisions — do not conflate them

Conflating "what CAN revise", "does the user WANT revision", and "which sets are ON" is
the trap. They live at different layers and different moments:

1. ELIGIBILITY (design-time safety boundary, NEVER a user prompt): judgment-set vs
   safety-wall. The user is never asked to classify _ALLOWED_WRITE_ROOTS as revisable —
   that decision protects them and is made by design. Safety/fact sets are hard-blocked
   from enrollment regardless of any user answer.

2. POSTURE (first-run, ONE human-framed question): "Do you want youk to improve itself
   over time — growing and pruning its own reasoning as it watches you work — or stay
   fixed and change only when you edit it?" Asked in the EXISTING first-run onboarding
   path (session.py:1201 is_new_install, :1212 onboarding item). Framed in human terms —
   never exposes internal set names like _SEVEN_CONVERGENCE. Default if declined: fixed
   (no self-revision) — conservative.

   WHY first-run is right for posture but WRONG for specifics: at install the user has
   zero youk experience and cannot judge "should youk revise its angles" — they don't know
   what an angle is. A deep abstract question at the moment of least context yields a
   rubber-stamp, not consent. So first-run asks only the POSTURE, not the specifics.

3. SPECIFIC ENROLLMENT (contextual, matures with use): which eligible sets are actively
   on. Surfaced the FIRST TIME a set has a real revision to propose — "youk noticed its
   {angle set} may be missing a case ({concrete example}); allow it to revise this kind of
   thing going forward?" Decided WITH a concrete example, when the user has context — not
   front-loaded as an abstract list. If posture=fixed, this never fires.

- REVISABLE (judgments youk can be wrong about): _SEVEN_CONVERGENCE, _FOUR_LENSES,
  NFR question set, code-review risk tiers, stress-test attack vectors,
  _SOLUTION_LANGUAGE_SIGNALS, _OPAQUE_WORDS, _CORRECTION_PHRASES, _CROSS_PROJECT_THEMES,
  capability-skill roster. These are youk's OPINIONS — incompletable, correctable.
- FROZEN (mechanical facts + safety walls — NEVER enrollable, hard-blocked not just
  absent): _CODE_EXTS/_DOC_EXTS/_CONFIG_EXTS, _SKIP_DIRS, _STOP_WORDS,
  _ALLOWED_WRITE_ROOTS, secret-safety rules, contract-verbatim rule. `.py` being a code
  extension is not an opinion that can be wrong; _ALLOWED_WRITE_ROOTS self-revising is a
  breach, not learning. A human learns new things but never unlearns that fire burns.

The enrollment test: does this set encode a JUDGMENT youk could be wrong about, or a
FACT / SAFETY CONSTRAINT that must stay fixed? Only the first is enrollable.

## The bidirectional loop (per enrolled set)

```
LEARN (grow):   recurring unknown/gap 2+  → propose ADD element
                  → challenge candidate (genuinely distinct, or a facet of an existing one?)
                  → survives → adopt
UNLEARN (prune): element never fires / rule repeatedly corrected / always a facet
                  → propose REMOVE element
                  → challenge (is removal safe — does anything depend on it?)
                  → survives → prune         ← THIS is the anti-bloat mechanism
both: autonomous apply + versioned snapshot (revert floor)
      → session_end DOCUMENTS every mutation (set, element, add/prune, why, driver)
      → user REVERTS or REFINES at that surfacing
```

Unlearn is what keeps youk from growing monotonically into ceremony. A system that only
accumulates rules becomes rigid and slow — the exact failure youk exists to prevent.
Human learning forgets what stopped being true.

## Autonomous + accountable (same principle as the uninstall feature)

Adoption/pruning is AUTONOMOUS (youk doesn't stall for approval) but NEVER silent: every
mutation surfaced at session_end with what/why/driver, versioned, reversible. Autonomous
action + after-the-fact human veto + working undo. youk evolves at machine speed and can
never quietly change its core.

## Machinery status (verified session #69)

Already present, disconnected at seams:
- unknown_unknown recorded + persisted (session.py:2201, server.py:1180); health.py emits
  real ones.
- recurrence→proposal: "same gap_type 2+ → pattern_trigger" (server.py:1161);
  detect_skill_gaps → assess → generate → add_proposal loop.
- UNLEARN primitive already exists for knowledge: knowledge_index.py:326 demotes unused
  knowledge to cold/archive. Proven pattern, not yet generalized to judgment-sets.

THE GAP: enrolled sets are frozen literals (challenge_gate.py:16 etc.); no registry, no
feedback from unknown_unknowns/corrections into the sets, no prune path for judgment-sets.

## Build scope (L/XL — next session, full adversary-loop + gates)

1. `revisable-sets registry` — explicit enrollment + per-set policy (grow / prune / both),
   default frozen, safety/fact sets hard-blocked from enrollment.
2. Convert enrolled frozen literals → versioned mutable sets with per-element provenance.
3. LEARN detector: recurring unknown_unknown/gap → add_proposal(candidate element).
4. UNLEARN detector: never-fires / repeatedly-corrected / always-a-facet → propose prune.
   Reuse the knowledge_index demote pattern.
5. Candidate challenge: run add/prune through youk's challenge/adversary loop.
6. Autonomous apply + version snapshot per set (revert floor).
7. session_end: document each mutation + expose revert/refine.
8. Trust artifact "open:" line reads live unknown_unknowns (user-facing half).

First enrolled instance: _SEVEN_CONVERGENCE (grow+prune). Prove the loop on one set
before enrolling more. Do not enroll everything at once — that is the bloat this ADR
forbids.

## Why not the alternatives

- Auto-classify revisable-vs-frozen: a misclassification enrolls a safety wall — the exact
  catastrophe. Opt-in registry makes that impossible by construction.
- Make all sets revisable: infinite machinery, the bloat itself. Only judgment-sets qualify.
- Frozen status quo: youk asserts completeness it cannot prove across ~30 enumerated sets,
  provides fields to admit incompleteness (unknown_unknown), and never acts on them.

## Resolution of the original dilemma (MECE or missing?)

Neither. No enrolled set is claimed MECE, and none is left silently incomplete. Each is a
current best basis that revises itself — grows at its frontier, prunes its dead weight —
gated by youk's own challenge discipline, with a human veto after the fact. Integrity
lives in the revision mechanism, not in any set being perfect. youk stops treating its own
enumerations as the walls it never challenges.
```
