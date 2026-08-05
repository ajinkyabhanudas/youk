# ADR: youk's convergence angle basis is self-revising, not frozen

Decision locked 2026-08-05 (session #69). Foundational — changes what youk IS.
Related: [[skill-trust-artifact]], [[reasoning-integrity]], [[tool-enforced-gates]].

## The question that forced this

Are youk's 7 convergence angles (structural, operational, experiential, adversarial,
temporal, outcome, semantic) MECE and complete — or can a task need an 8th?

- If MECE/complete → youk never misses → the "open angle" is always empty → youk is a
  closed system that cannot learn. Dead honesty field.
- If not complete → an 8th can exist → but then every "converged" verdict is suspect,
  because youk converged over the angles it KNOWS, blind to the ones it doesn't. This
  relocates satisfaction-bias one level up: "zero objections from all angles I thought
  to check."

Both horns are fatal. The angle-set was written by a human and is the ONE wall youk
never challenges while attacking everything else. That is the blind spot.

## Decision

youk cannot be complete. It can be **self-correcting**. The 7 angles are the current
best BASIS, not a MECE partition. youk's integrity comes not from the basis being
perfect but from youk detecting when the basis failed and growing it. Completeness is
asymptotic — approached, never had. An "open angle" is not negligence; it is the
frontier where the current basis ran out, captured so a later youk closes it.

## Mechanism (fully autonomous adoption + after-the-fact accountability)

Current state in code (verified session #69):
- `_SEVEN_CONVERGENCE` is a hardcoded frozen set (challenge_gate.py:16, session.py:2197).
- `unknown_unknown` is a first-class param that records an angle "unresolvable without
  real external collision" (server.py:1180) and persists in convergence_state
  (session.py:2201). health.py already EMITS real ones (e.g. "adversarial: requires
  real competitor analysis — cannot be self-assessed").
- Recurrence→proposal machinery exists: "same gap_type 2+ times → pattern_trigger"
  (server.py:1161). detect_skill_gaps → assess → generate → add_proposal loop exists.

THE GAP: unknown_unknowns accumulate but never feed back into the basis. youk can
NOTICE an 8th angle and has no way to ADOPT it. The loop is ~90% built, disconnected
at one seam.

The close:
```
loop converges over current basis
  ├─ surfaces unknown_unknown ──► trust artifact "open:" line (user SEES the limit now)
  └─ same unknown_unknown recurs 2+ ──► add_proposal("candidate angle {X}")
        └─ youk challenges the CANDIDATE (distinct angle, or facet of an existing one?)
             └─ survives ──► AUTONOMOUSLY added to a versioned basis (v7→v8)
                  └─ session_end DOCUMENTS: what angle, why, which recurring uu drove it
                       └─ user can REVERT (drop it) or IMPROVE (refine) at that surfacing
```

Adoption is **autonomous** (youk doesn't stall for approval) but **never silent**:
every basis mutation is surfaced at session end with what/why, and is **reversible**.
Same principle as this session's uninstall feature — autonomous change + a clean
revert path. Each basis version is snapshotted so revert is exact.

## Why not the alternatives

- **Human-gated pre-approval:** stalls youk's evolution waiting on the user; weaker than
  autonomous+retrospective-veto, which evolves at machine speed AND stays safe.
- **Detect-and-surface-only (manual encode):** the loop never closes itself — defeats
  "youk improves itself where needed." A flag is not self-correction.
- **Frozen basis (status quo):** the incoherence above. Asserts completeness it cannot
  prove, while providing a field to admit incompleteness it never acts on.

## Build scope (L — cross-system, next session, full routing + adversary-loop)

- challenge_gate.py / session.py: `_SEVEN_CONVERGENCE` frozen set → versioned mutable
  basis with provenance per angle (why it exists, when added, which uu drove it).
- Recurrence detector: unknown_unknown seen 2+ across convergence_state → add_proposal.
- Candidate-angle challenge: run the angle itself through youk's challenge/adversary
  loop — is it genuinely distinct from the existing 7, or a facet? Only distinct survives.
- Autonomous apply + version snapshot (revert floor).
- session_end: document each basis mutation (angle, rationale, driving uu) + expose
  revert/improve affordance.
- Trust artifact "open:" line reads live unknown_unknowns (the user-facing half).

## The resolution to the original dilemma

An open angle is NOT "an angle missed" (negligence) and youk is NOT "complete/MECE"
(impossible). An open angle is the frontier, captured, that a later youk closes by
growing. The angle-set stops being the one unchallenged wall — it gets challenged like
everything else. Integrity lives in the revision mechanism, not the basis.
