---
name: adversarial-planning
description: >
  Adversarial audit skill. Takes any planning target — a product, a plan, a migration,
  an architecture, a capability roadmap, a set of claims — and produces a battle-tested
  analysis: claims inventory, empirical verification, null-baseline, adversarial convergence
  per item, gap register, design-space enumeration, roadmap with rejected alternatives, and
  a verdict with convergence certificate. Exit condition is zero new objections, not round count.
  State is externalized so the analysis survives context compaction and tab-close.
  Triggers on: "audit whether this delivers its promises", "analyze this product/plan adversarially",
  "derive a roadmap from first principles", "stress-test this architecture", "reason until nothing
  better exists", "red-team this plan", "what gaps does this have?", "challenge this before we ship",
  explicit requests for adversarial or claims-based analysis of any non-trivial target.
  Distinct from challenge (single direction, single task) and adversary-loop (direction attack only).
  adversarial-planning handles multi-item, multi-phase, stateful audits of products or plans.
---

# adversarial-planning — Adversarial Analysis and Roadmap Derivation

The most expensive failure in planning is not picking the wrong solution — it is not
knowing what you are actually claiming, not verifying the claims, and not enumerating
what better solutions exist. This skill addresses all three.

It runs a structured adversarial protocol on any planning target. State is externalized
to files so weak long-horizon instruction following does not corrupt the analysis. Frames
are fixed and role-forced so self-sycophancy cannot produce shallow verdicts. Evidence is
tagged so claims requiring EXECUTED or TRACED evidence cannot be satisfied by assertion.

**Fail-soft ordering:** The highest-leverage steps (state setup, goals/claims decomposition,
evidence tagging) come first. A partial execution through Phase A.3 still yields a
materially defensible claims inventory with evidence quality visible. Refinement and
roadmap derivation come later and are layered on top.

---

## Invocation Grammar

| Invocation | Behavior |
|------------|----------|
| *(no directive)* | Full protocol — all phases, state files, convergence certificate |
| `quick: [target]` | Claims inventory + top-3 gaps only. No roadmap. For time-bounded audits. |
| `roadmap: [gap register]` | Roadmap derivation only — given a completed gap register, derive CAP items and attack them |
| `claims: [source text]` | Claims extraction and verification only — no gap register or roadmap |
| `resume` | Read STATE/progress.md and continue from the last completed step |
| `gap: [specific gap]` | Adversarial attack on one gap only — full 7-frame protocol |

---

## Target Profiles

The phases are stated for any planning target. Worked profiles:

| Profile | What counts as a "claim" | What counts as the "promise" | Null-baseline |
|---------|--------------------------|------------------------------|---------------|
| **Repo audit** | README claims, changelog claims, metric assertions | Core README promise | Minimum tier that delivers claimed benefits |
| **Architecture audit** | Design doc claims, ADR decision rationales | Core design goal | What the system without the proposed change delivers |
| **Plan audit** | Task list assumptions, outcome claims | Project goal | Doing nothing / minimum intervention |
| **Product audit** | Marketing claims, feature descriptions | Primary user value prop | Competing product or manual workaround |
| **Migration audit** | Migration claims, compatibility assertions | "Nothing breaks" | Running current system unchanged |

---

## State Files (create in STATE/ at Phase 0)

| File | Contents |
|------|----------|
| `STATE/progress.md` | Phase ledger — one row per step, status, git SHA at start |
| `STATE/repo-map.md` (or `STATE/target-map.md`) | 2-level directory tree, LOC counts, key surface (or equivalent for non-repo targets) |
| `STATE/deviation-log.md` | Every place this protocol under-specified or was deviated from, with proposed fix |
| `STATE/attack-logs/{item}-{slug}.md` | One file per item that received full 7-frame protocol |
| `STATE/questions.md` | Open questions requiring human input, surfaced at gate stops |
| `RELAY/` | Gate handoff directory — gate packages go in, discriminator memos come back. Never summarize; discriminator reads source files directly. |

---

## Evidence Tags

Apply to every piece of evidence cited. Verdict requires ≥ TRACED for all load-bearing claims.

| Tag | Meaning |
|-----|---------|
| `[EXECUTED]` | Command run, output observed directly |
| `[TRACED]` | Read the source file/code; confirmed the claim holds at the line level |
| `[READ]` | Read the document; claim appears there but code not traced |
| `[ASSUMED]` | Training knowledge or inference — no source file confirmed |

**R10 — Numeric Reconciliation (mandatory):** Any quantity appearing in ≥2 sources
(committed file, live tool return, doc, metric) must be explicitly reconciled with both
values cited before use. State the denominator and scope for each. Near-equal metrics
from different denominators are exactly the hiding place this rule exists for.

---

## Protocol Budget (mandatory scope — DEV-3 fix)

| Item type | Required protocol | Written attack log? |
|-----------|------------------|---------------------|
| Roadmap items (CAP-N) | Full 7-frame + frame-generation | Yes — STATE/attack-logs/ |
| Top-5 gaps by rank score | Full 7-frame + frame-generation | Yes |
| Claims load-bearing for verdict page | Full 7-frame + frame-generation | Yes |
| All other claims (rank score < threshold) | Inline 3-angle clearing (minimum) | No |
| Claims already HOLDS with no contested verdict | Inline clearing sufficient | No |

Full 7-frame protocol = all seven frames run, frame-generation round, exit on zero new objections.
Inline 3-angle clearing = F1 (user value), F2 (engineering rigor), F3 (evidence) minimum; log inline.

---

## Phase 0 — Setup

`[PHASE 0: SETUP]`

**0.1 — State initialization**
Create `STATE/progress.md` as a phase ledger. Record:
- Git SHA (if repo target): `git rev-parse HEAD`
- Date and execution context (live machine / clone / remote)
- Any uncommitted changes or live-vs-committed divergences (R10 applies here)
- Note deviation if analyzing in-place on a live machine — live tool returns may diverge from committed files

If analyzing in-place: flag every place where live state (session state files, audit log entries, runtime metrics) might diverge from committed state. Log in `STATE/deviation-log.md`.

**0.2 — Target map**
Build `STATE/target-map.md` (or repo-map for repo targets):
- 2-level directory tree with file counts and rough LOC estimates
- Key surface: interfaces, tools, skills, APIs, config files
- Dependencies and external integrations

**0.3 — Workspace isolation**
If the target is a live repo working tree, create the audit workspace OUTSIDE the repo (`~/Desktop/{target}-audit/`). Never write `STATE/`, `REPORT/`, or skill artifacts into the repo working tree — CAP implementations go into the repo on a dedicated branch only.

macOS hazard: on case-insensitive filesystems, `mv STATE/` matches `state/` (lowercase). If the repo has a `state/` directory, name the audit directory `STATE-audit/` or confirm the path resolves to the intended directory before executing any move.

Create `RELAY/` now (not at gate time). Empty from Phase 0 = protocol complete.

**0.4 — Deviation log**
Create `STATE/deviation-log.md`. Pre-populate with any immediate deviations from this protocol (e.g., web search unavailable, analyzing in-place instead of clean clone, workspace path differs from default).

Mark Phase 0 DONE in progress.md.

---

## Phase A.1 — Objective / Promise Decomposition

`[PHASE A.1: OBJECTIVES]`

State the target's core promise in one sentence — the standard against which all claims and gaps are measured. Read the primary source (README first section or equivalent) and extract verbatim. Format: `PROMISE / SOURCE / FALSIFIABLE: yes|no`.

Mark Phase A.1 DONE in progress.md.

---

## Phase A.2 — Claims Inventory

`[PHASE A.2: CLAIMS INVENTORY]`

Extract ≥25 falsifiable claims from the target. Use T1 format (see `references/templates.md`): source, type, verifiability, evidence tag, verdict (assign after A.5), one-line why, survived.

Mark Phase A.2 DONE in progress.md when ≥25 claims extracted.

---

## Phase A.3 — Empirical Verification

`[PHASE A.3: VERIFICATION]`

For each claim: attempt to upgrade evidence tag from [ASSUMED]/[READ] to [TRACED]/[EXECUTED].
Prioritize claims that are load-bearing for the verdict (outcome claims, measurement claims).

Sub-steps:
- **A.3a**: Sample key artifacts (≥5 for repo audits). Note: distinguish test layers (MCP-level vs hook-level vs integration tests are different enforcement surfaces).
- **A.3b**: Trace code paths for measurement claims. Verify formulas, weights, thresholds.
- **A.3c**: Run any executable checks available (CI output, test suite, CLI tools).
- **A.3d**: Apply R10 to any metric that appears in ≥2 sources — reconcile denominators before proceeding.

Mark Phase A.3 DONE in progress.md. Record any claims that remain [ASSUMED] with an explanation of why TRACED is unavailable.

---

## Phase A.4 — Null-Baseline

`[PHASE A.4: NULL-BASELINE]`

Apply the null-baseline test: what does the target deliver WITHOUT the proposed feature/change/system?

Format:
```
NULL-BASELINE:
  Without:  [what the user gets without the target]
  With:     [what the target adds, per tier if applicable]
  Delta:    [the actual marginal value, with evidence tags]
  Key finding: [the honest assessment of the delta — can be smaller than the promise implies]
```

For tiered systems: enumerate what each tier delivers. The gap between claimed benefits and actual tier requirements is a finding.

Mark Phase A.4 DONE in progress.md.

---

## Phase A.5 — Adversarial Convergence

`[PHASE A.5: ADVERSARIAL CONVERGENCE]`

Apply the 7-frame adversarial protocol to claims. See `references/frames.md` for full frame templates.

**Protocol scope** (see Protocol Budget table above):
- Full 7-frame + frame-generation: roadmap items, top-5 gaps, verdict-load-bearing claims
- Inline 3-angle (F1, F2, F3 minimum): all other claims

**Exit condition:** A full frame pass produces zero new objections from ALL frames run. Not round count. Self-check before any verdict: (1) did the last round produce zero new objections? (2) is there any frame or angle not yet run? Both must be true.

**Frame-generation round:** After F1–F7 exhaust, ask if a target-specific frame is necessary. If generated: apply to all relevant items; document scope.

Inline clearing format: `F1 [USER-VALUE] {finding or CLEAR} / F2 [ENGINEERING-RIGOR] / F3 [EVIDENCE] / Verdict / Why`. Full templates in `references/templates.md` (T3).

Write full attack logs to `STATE/attack-logs/{item}-{slug}.md` for mandatory-full-protocol items.

Mark Phase A.5 DONE in progress.md. Update claim verdicts.

---

## Phase A.6 — Gap Register

`[PHASE A.6: GAP REGISTER]`

Derive gaps from the adversarial convergence. A gap = distance between the promise (A.1) and verified reality (A.5).

For each gap:
```
GAP-{N}: {one-line title}
  promise damaged:   {which promise statement this gap undermines}
  defect/absence:    {what is missing or wrong — specific, evidence-tagged}
  evidence:          [tag] {source}
  promise-damage:    {1-5 — how severely this damages the core promise}
  user-frequency:    {1-5 — how often a user would encounter this gap}
  rank score:        {promise-damage × user-frequency}
```

Rank gaps by rank score. Top-5 receive full 7-frame attack in A.5 (if not already done).

Mark Phase A.6 DONE in progress.md.

---

## Phase A.7 — Design-Space Enumeration

`[PHASE A.7: DESIGN SPACE]`

Enumerate the design space along ≥3 axes relevant to the target's domain.

**Mandatory landscape search:** When web access is available, run ≤10 searches to ground comparable systems with current URLs. [ASSUMED] tags are permitted only when web is confirmed unavailable at execution time. If analysis was done with [ASSUMED] comparables and web is later available, run searches before the gate closes.

For each axis: position the target on the axis, identify at least 2 alternatives, state why each alternative was rejected or not adopted.

Apply R10 to any metric used to compare systems: both figures and their denominators/scopes must be cited.

Mark Phase A.7 DONE in progress.md.

---

## Phase A.8 — Roadmap Derivation

`[PHASE A.8: ROADMAP]`

Derive capability improvements (CAP-N) that close top gaps.

For each CAP item, use T8 format:
```
CAP-{N}: {title}
  closes:               {which gaps — reference only gaps it actually addresses}
  does NOT close:       {gaps sometimes assumed to be closed but aren't — mandatory field}
  mechanism:            {how it works — specific enough to implement}
  design-space cell:    {which axis/position this occupies}
  rejected neighbors:   {≥2 alternatives considered and why rejected}
  deletes:              {what this removes or makes redundant}
  adjacent-possible:    {what exists that this builds on}
  acceptance evidence:  {within-target verification — for solo/single-developer targets,
                        use within-developer design: same developer as own control across time.
                        Cross-cohort divergence is not runnable without multiple users.}
  depends on:           {other CAPs required first, or "None"}
  survived:             {objections that passed through adversarial attack on this CAP}
```

**Each CAP item must survive full 7-frame + frame-generation attack** (written to STATE/attack-logs/).
No CAP item goes to the roadmap without passing the convergence protocol.

Mark Phase A.8 DONE in progress.md.

---

## Phase A.9 — Convergence Certificate

`[PHASE A.9: CERTIFICATE]`

Emit before verdict:
```
[CONVERGENCE CERTIFICATE]
Items processed:    {N claims} + {M gaps} + {K CAP items} = {total} items
Rounds consumed:    Full 7-frame on {n} items; inline 3-angle on {m} items
Objections raised:  {N} material objections across full-round items; {N} resolved before verdict
Frames generated:   {N beyond F1-F7; named and scoped}
Items CONTESTED:    {N — if >0, list them; they cannot appear in verdict as resolved}
Honest ceiling:     "{No frame we could construct produces a surviving objection against the
                    converged verdicts... [or: the following tensions remain unresolved]}"
```

CONTESTED items must appear in the verdict as UNRESOLVED, not as HOLDS or PARTIAL.

Mark Phase A.9 DONE in progress.md.

---

## Phase A.10 — Verdict

`[PHASE A.10: VERDICT]`

Three-axis verdict structure:

**Promise-fixed (primary):** Against the stated promise (A.1), does the target deliver? Honest assessment with evidence. State what is verifiable, what is unverified, what is falsified.

**Claims-fixed:** Summary of claim verdicts. Count: N HOLDS / N PARTIAL / N UNVERIFIED-AS-STATED / N CONTESTED. Key findings per category.

**Category-relative:** Against the design-space enumeration (A.7), where does the target stand vs. comparables? What are the genuine differentiators? What are the genuine gaps?

Format:
```
Top 3 gaps (one line each):
1. {gap title} (rank score {N}): {one sentence}
2. ...
3. ...
```

Mark Phase A.10 DONE in progress.md. Phase A complete.

---

## The Seven Frames

Full templates and role-forcing instructions in `references/frames.md`.

Frames: F1 USER-VALUE · F2 ENGINEERING-RIGOR · F3 EVIDENCE · F4 GOODHART · F5 TRUST/SELF-MOD · F6 ADOPTION-ECONOMICS · F7 SCALE/FAILURE

**Frame-generation trigger:** After F1–F7 exhaust, ask: "Is there a frame not in F1–F7 that this target's specific structure makes necessary?" If yes: name it (F8, F9...), apply to all relevant items, document scope explicitly. Narrow frames are valid — document which items are in and out of scope.

---

## Gate Stops

**GATE 1 (end of Phase A.10):** Present the verdict, convergence certificate, and roadmap. Await human approval before proceeding to skill forge or implementation.
MANDATORY FINAL STEP before posting the gate: refresh RELAY/ per the Gate Packaging Manifest, then end the gate message with the manifest checklist echo — see T9 format. A gate message without this checklist is an incomplete gate.

**GATE 2 (end of Phase B, if forging a skill):** Present the SKILL.md inline, reference file list, B.1 disposition table (deviation → fix), and B.2 shortfall table. Do not proceed to benchmarking until approved.
MANDATORY FINAL STEP before posting the gate: refresh RELAY/ per the Gate Packaging Manifest, then end the gate message with the manifest checklist echo — see T9 format. A gate message without this checklist is an incomplete gate.

At each gate: surface open questions from `STATE/questions.md`. Do not answer gate questions yourself — wait for human input.

---

## External Verification

**Self-converged ≠ externally-verified.** The convergence certificate records that the internal loop ran to dry — zero new objections across all frames run. It does not record that an independent reader, with no knowledge of the analyst's reasoning, found the output credible. These are different signals. Self-convergence is necessary but not sufficient. The Gate 1 material error (41%/70% metric conflation) survived internal convergence and was caught only by an external discriminator. The skill ships this section so the verifier half of the loop is not invented mid-run.

### Gate Packaging Manifest

At each gate stop, package the following for the discriminator:

**GATE 1 package:**
```
REPORT/claims-matrix.md       — all claims with verdicts and evidence tags
REPORT/gap-register.md        — ranked gaps with promise-damage scores
REPORT/roadmap.md             — CAP items with full T8 fields
REPORT/appendix-evidence.md   — design-space axes and landscape comparables
REPORT/verdict.md             — three-axis verdict + convergence certificate
STATE/deviation-log.md        — all deviations with fix types
STATE/questions.md            — open questions requiring discriminator input
STATE/attack-logs/            — full attack logs for mandatory-full-protocol items
```

**GATE 2 package (skill forge):**
```
{skill}/SKILL.md              — full skill file inline
{skill}/references/           — all reference files with one-line summaries
STATE/deviation-log.md        — B.1 disposition table (deviation → fix, all entries)
B.2 shortfall table           — competing skills vs. this skill (inline in gate post)
```

Place packages in `RELAY/` before posting the gate. The discriminator reads from `RELAY/`
and returns their response there. Do not summarize or paraphrase package contents — the
discriminator reads the source files, not a summary.

### Discriminator Grading-Rubric Template

Provide this template to the discriminator with each gate. The discriminator fills it in:

```
GATE {N} GRADING MEMO

STATUS: APPROVED | APPROVED WITH CORRECTIONS | REJECTED

## A. Citation audit results
{Spot-check ≥3 specific line citations from the package against the source.
Note: VERIFIED | VERSION-SKEWED | INCORRECT for each.
Flag any quantity that appears in ≥2 sources without R10 reconciliation.}

## B. Grades
- Verification quality: HIGH | MEDIUM | LOW
  (Were claims TRACED to source, or accepted at [READ]/[ASSUMED]?)
- Convergence rigor: HIGH | MEDIUM | LOW
  (Did the protocol scope match the mandatory-full-protocol table? Were all
  attack logs written? Did the certificate match the actual work done?)
- Novelty: HIGH | MEDIUM | LOW
  (Did the analysis surface findings the author couldn't self-generate?)
- State discipline: HIGH | MEDIUM | LOW
  (Were all deviations logged? Does progress.md match actual work done?)

## C. Required corrections (complete all before gate advances)
{List each correction as C{N}: specific change required, file, field.}

## D. Answers to open questions
{Answer each question from STATE/questions.md.}

## E. Pack patches
{Any new rules, mandatory additions, or protocol amendments that this run revealed.
Each patch becomes a P{N} entry in the deviation log.}

Proceed: apply E, execute C, post GATE {N}.1 delta, then await approval to advance.
```

### Self-Converged ≠ Externally-Verified: The Structural Doctrine

The convergence certificate is an internal signal. It records:
- That the analyst ran all mandatory frames
- That the last round produced zero new objections
- That no unrun frames were skipped

It does not record:
- That an independent reader found the analysis credible
- That the evidence citations are accurate (a discriminator spot-checks these)
- That the numeric quantities were correctly attributed to the right sources
- That the conclusions follow from the evidence rather than from the analyst's priors

**What external grading catches that internal convergence cannot:**
- Metric conflation (same number, different denominators — the analyst doesn't notice because they trust their own sourcing)
- Overclaims from single data points ("most developers see 6-8" from one data point)
- Missing mandatory fields the analyst normalized away (does NOT close, acceptance evidence design)
- Protocol scope violations the analyst rationalized (inline clearing where full protocol was required)

**Operating rule:** Submit every Gate output to a discriminator before advancing. The discriminator does not need to be human — a context-independent model with only the package files (no session history, no analyst reasoning) is sufficient and structurally stronger than a human who has been watching the analysis unfold. The independence guarantee is what matters.

---

## Convergence Rules

See `references/convergence.md` for full mechanics. Key rules:

**Exit condition:** Zero new objections from all frames in the last round, AND no unrun frames remaining. Not round count. Self-check: (1) last round clean? (2) any angle unrun? Both must be true.

**Round caps (emergency brakes only):** Per-item: 10 rounds. On cap hit: surface unresolved tension, require human input. Never exit silently. Phase A cap: prioritize top-5 gaps and verdict-load-bearing claims if budget runs out.

**Global optimum:** Exiting because run frames produced no objections, while leaving frames unrun, is local optimum — not global.

---

## Anti-Sycophancy Mechanisms (structural)

- **Role-forced frames:** CLEAR requires a positive claim — not "seems fine," not deferral. Steelman gate: before CLEAR, state the strongest case this frame should have found an objection and argue why it doesn't hold. If the steelman holds, convert to HIGH.
- **State externalization:** Progress ledger is ground truth on resume. The ledger overrides memory.
- **Evidence ladder:** [ASSUMED] → UNVERIFIED-AS-STATED. Verdicts require ≥ TRACED.
- **Convergence certificate:** Cannot be written honestly until both exit conditions are met. If it cannot be written with confidence, the loop has not completed.
- **External verification:** Self-convergence is necessary, not sufficient. Submit every gate output to a discriminator (see External Verification section). The discriminator catches what internal convergence cannot.

---

## Quality Bars

- **State files are the ground truth.** Progress.md overrides memory.
- **[ASSUMED] cannot be HOLDS.** UNVERIFIED-AS-STATED until TRACED.
- **CONTESTED items appear as UNRESOLVED in the verdict.** Not PARTIAL.
- **CLEAR requires a positive claim.** "Seems fine" is not CLEAR.
- **Every CAP must survive full 7-frame attack.** No roadmap item without attack log.
- **R10 is mandatory.** Any metric in ≥2 sources: both values, both denominators, reconciled.
- **`does NOT close` is mandatory on CAP items.** The discriminator will look for it.
- **Acceptance evidence is within-target for solo-developer products.** Cross-cohort requires ≥2 users.
- **P5 — CAP premise re-verification (E2-C3, 2026-07-18):** Before implementing any CAP, re-verify the `defect/absence` claim against the frozen audit-SHA state of the target. The T8 `defect/absence` field REQUIRES an evidence tag ([EXECUTED] preferred, [TRACED] minimum). An unverified `defect/absence` that turns out false means CAP scope is wrong — the implementation becomes a drift sentinel rather than a feature add. This must be caught before commit, not by the discriminator at the gate. Premise re-verification step: at each CAP start, grep/read the target at the audit SHA for the specific artifact the defect claims is absent. If present, reclassify the CAP as SENTINEL (drift guard) before proceeding, and log the reclassification in the deviation log.

---

## Reference Files

| File | When to read |
|------|-------------|
| `references/frames.md` | Phase A.5 — full frame templates with role-forcing instructions |
| `references/convergence.md` | Phase A.5 and A.9 — loop mechanics, certificate format, round caps |
| `references/templates.md` | All phases — T1 (claims), T2 (gaps), T3 (CAP), T4 (verdict), T5 (certificate), T6 (null-baseline), T7 (deviation log), T8 (roadmap item) |
| `references/evidence.md` | Phase A.3 and throughout — tagging ladder, verification-first doctrine, null-baseline as reusable move, R10 |
