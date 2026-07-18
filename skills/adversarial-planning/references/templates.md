# references/templates.md — T1–T8 Templates

Evolved from the adversarial-planning pack (01-ADVERSARIAL-PROTOCOL.md) per deviation log B.1.
Each template encodes lessons from the phase where it applies.

---

## T1 — Claim Row

```
CLAIM-{NN}: "{verbatim or close-paraphrase}"
  source:        {file, line — or "README line ~N" if line numbers are version-skewed}
  type:          outcome | capability | design-principle | measurement | install-UX
  verifiability: empirical-only | code-verifiable | design-verifiable
  evidence:      [TAG] {evidence text, or "needs trace"}
  verdict:       HOLDS | PARTIAL | UNVERIFIED-AS-STATED | CONTESTED
  one-line why:  {one sentence justifying the verdict — required for all non-HOLDS}
  survived:      {objections that passed through the frame attack; or "[pending A.5]"}
```

**Notes:**
- Line numbers may be version-skewed in public repos vs. local. Use "line ~N" for approximate citations;
  note the content that was confirmed, not just the line number.
- [ASSUMED] evidence → verdict is UNVERIFIED-AS-STATED, not HOLDS, until upgraded to [TRACED].
- R10: if the claim's quantity appears in ≥2 sources, reconcile inline before assigning verdict.

---

## T2 — Gap Row

```
GAP-{N}: {one-line title}
  promise damaged:   {which promise statement (from A.1) this gap undermines — quote or paraphrase}
  defect/absence:    {what is missing or wrong — specific, tagged with evidence}
  evidence:          [TAG] {source, line where possible}
  promise-damage:    {1-5}  (5 = this IS the promise; 1 = minor wording gap)
  user-frequency:    {1-5}  (5 = every session; 1 = rare edge case)
  rank score:        {promise-damage × user-frequency}
  disposition:       {if accepted structural limit: "ACCEPTED AS STRUCTURAL LIMIT — [reason]"}
```

**Disposition field:** Add when a gap is intentionally accepted rather than addressed by a CAP.
State plainly: "No CAP can close this within the current architecture because [reason]. Accepted."
Do not leave gaps unaddressed without a disposition — the grader will look for it.

---

## T3 — Attack Log Entry

Used in `STATE/attack-logs/{item}-{slug}.md`:

```
# STATE/attack-logs/{item}-{slug}.md
Item: {CLAIM-NN | GAP-N | CAP-N}
Protocol: 7-frame + frame-generation
Generated: {date}

## Round 1

F1 [USER-VALUE]:
  Steelman: {strongest case this frame should find an objection}
  Finding: {CLEAR with positive claim | objection with weight}

F2 [ENGINEERING-RIGOR]: ...
F3 [EVIDENCE]: ...
F4 [GOODHART]: ...
F5 [TRUST/SELF-MOD]: ...
F6 [ADOPTION-ECONOMICS]: ...
F7 [SCALE/FAILURE]: ...

Round 1 verdict: {N BLOCKING, N HIGH, N LOW — or "zero objections, proceed to frame-gen"}

## Frame-Generation Round (runs after zero objections from F1-F7)
Generated frame: {name | "none generated"}
If generated: scope, items in, items out, finding.

## Round 2 (if needed)
...

## Convergence
Exit condition met: {yes/no}
Objections resolved: {N}
Surviving notes: {any LOW notes carried forward}
Final verdict: {PASSES | PASSES WITH REVISION | BLOCKED}
```

---

## T4 — Verdict Page Structure

```
# REPORT/verdict.md

## Promise-fixed verdict (PRIMARY)
{2-3 paragraphs. Against the stated promise (A.1), does the target deliver?
Honest assessment. State what is verifiable vs. unverified vs. falsified.
Include metric reconciliation (R10) for any figure cited.}

## Claims-fixed verdict
{N HOLDS / N PARTIAL / N UNVERIFIED-AS-STATED / N CONTESTED — total must match claims count.
Key findings per category. No padding.}

## Category-relative verdict
{Against the design space (A.7), where does the target stand?
Genuine differentiators + genuine gaps vs. comparables.
[SOURCED] tags where web search confirmed; [ASSUMED] where not.}

## Top 3 gaps (one line each)
1. {gap title} (score N): {one sentence}
2. ...
3. ...

## Convergence certificate
{paste from T5}
```

---

## T5 — Convergence Certificate

```
[CONVERGENCE CERTIFICATE]
Items processed:     {N claims (Phase A.2)} + {M gaps (A.6)} + {K CAP items (A.8)} = {total}
Rounds consumed:     Full 7-frame on {n} items; inline 3-angle on {m} items
Objections raised:   {N} material objections across full-round items; {N} resolved before verdict
Frames generated:    {N — list names and scopes; or "0 — F1–F7 sufficient"}
Items CONTESTED:     {N — list them; or "0 — all items converged within round cap"}
Open deviations:     {N — see STATE/deviation-log.md}
Open questions:      {N — see STATE/questions.md}
Honest ceiling:      "{specific statement of what the loop can and cannot claim}"
```

---

## T6 — Null-Baseline Entry

```
## Null-Baseline Analysis (Phase A.4)

{Source description}: Without/With comparison assessed against minimum tier that delivers each benefit.

[TRACED] = code-verifiable; [READ] = documentation-only; tier labels as applicable

| Claimed benefit | Minimum tier | Evidence |
|-----------------|-------------|----------|
| {benefit} | {tier} | [TAG] {evidence} |
...

Key finding: {the honest statement of what the minimum viable tier delivers vs. the full stack}
```

---

## T7 — Deviation Log Entry

```
DEV-{N} @ {step}:
  pack said:     "{what the protocol specified}"
  reality:       {what was actually possible or encountered}
  I did:         {what was done instead}
  proposed fix:  {how the protocol should be updated to handle this case}
  fix type:      (a) new instruction | (b) template change | (c) floor/budget change | (d) accepted looseness
```

No entry may be silently dropped. Every deviation is logged and assigned a fix type.

---

## T8 — Roadmap Item (CAP)

```
CAP-{N}: {title}
  closes:               {gaps this actually closes — reference by GAP-N}
  does NOT close:       {adjacent gaps sometimes assumed closed — mandatory field}
  mechanism:            {specific enough to implement — file paths, interfaces, behavior}
  design-space cell:    {which axis/position in the A.7 design space this occupies}
  rejected neighbors:   {≥2 alternatives with rejection reason — not just "excluded"}
  deletes:              {what this removes, makes redundant, or replaces}
  adjacent-possible:    {existing infrastructure this builds on}
  acceptance evidence:  {within-target verification — for solo/single-developer products,
                        use within-developer design (same developer as own control across time).
                        Cross-cohort divergence requires ≥2 users — do not state it for
                        solo-developer products.}
  depends on:           {other CAPs required first — or "None"}
  survived:             {objections that passed through the full 7-frame attack on this CAP}
  note:                 {any correction applied during the attack that changed the mechanism
                        or threshold from what was initially proposed}
```

**Required fields:** ALL fields listed above. `does NOT close` is mandatory — gaps adjacent
to the CAP that the CAP does not address must be named. Omitting it means the grader
cannot evaluate whether the roadmap overpromises.

---

## T9 — Gate Post (required manifest checklist echo)

Every gate message must end with this manifest checklist after refreshing RELAY/.
Replace each `[...]` with `present` or `ABSENT`. A gate message without this checklist
is an incomplete gate. The refresh must happen immediately before posting — not
speculatively. `ABSENT` on any required field = the gate is incomplete.

```
RELAY manifest:
  MANIFEST.md        [present/ABSENT]
  live-evidence.md   [present/ABSENT]
  REPORT/            [present/ABSENT]
  deviation-log      [present/ABSENT]
  attack-logs        [present/ABSENT]
  skill+package      [present/ABSENT]
```

**MANIFEST.md** — one-line description of each file in RELAY/ with byte size and date.
**live-evidence.md** — any live tool return values captured during the run (session_start
outputs, metric values, git SHA) that the discriminator cannot reproduce from committed files.
