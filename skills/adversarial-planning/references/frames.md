# references/frames.md — Seven Frames + Frame Generation

The seven frames are the adversarial protocol's attack surface. Each frame is role-forced:
the attacker's only job is to find objections. CLEAR requires a positive claim.

---

## Running a Frame

For each frame:

1. **Steelman first:** State the strongest case that this frame SHOULD find an objection.
   If you cannot construct a steelman, the frame is likely inapplicable — document why.

2. **Attack:** Either confirm the objection (specific: names what fails, when, who is
   affected, under what condition) or argue why the steelman case doesn't hold.

3. **CLEAR requires a positive claim.** Format:
   > "CLEAR — this frame does not block because [specific reason the target is robust
   > against this lens]. [name the specific scenario that would have triggered an objection,
   > and why it doesn't apply here]."

   These are NOT CLEAR:
   - "Seems fine"
   - "The team can decide"
   - "Probably works"
   - "No obvious issues"
   - Silence

4. **Objection weight:**
   - BLOCKING: if this is correct, the direction/claim is wrong and must not proceed
   - HIGH: proceed with revision; address before shipment
   - LOW: noted, does not block; carried forward as context

---

## F1 — USER-VALUE

**Role:** You are evaluating whether this actually helps the user.

**Questions to run:**
- If the mechanism works perfectly, does the benefit to the user actually materialize?
- Is the benefit real or is it a proxy metric that doesn't correspond to a felt change?
- Would a user who doesn't know the mechanism exists experience the claimed benefit?
- Is the user who benefits the same user paying the cost (ceremony, install, overhead)?
- What does the user have to believe for this to deliver value? Are those beliefs reasonable?

**Common F1 findings:**
- Benefit is real in theory but requires the user to change behavior in ways that
  aren't incentivized
- The metric improves but the experience doesn't
- The benefit accrues after N sessions but the cost is incurred immediately on each session
- The user who benefits is not the user who decides whether to use the system

---

## F2 — ENGINEERING-RIGOR

**Role:** You are evaluating whether the implementation is technically sound.

**Questions to run:**
- Is the claimed behavior actually implemented, or just described?
- Is the code path that produces the claimed output actually reachable?
- Are there edge cases in the implementation that undermine the general claim?
- Does the proposed threshold/formula/algorithm produce the claimed result?
- Are there dependencies (libraries, services, runtime state) that the claim assumes exist?
- What breaks if a dependency is unavailable?

**Common F2 findings:**
- Tool exists and returns the right value when called, but calling is voluntary
  (enforcement is prompt-level, not tool-enforced)
- Formula is correct but threshold is wrong (exceeds measured baseline, e.g. --cov-fail-under 88 vs measured 86)
- Feature is implemented in one path but not another (e.g. Docker vs non-Docker)
- Claim requires a precondition that isn't documented or enforced

---

## F3 — EVIDENCE

**Role:** You are evaluating whether claims are backed by evidence, not assertion.

**Evidence ladder (mandatory ordering):**
1. [EXECUTED] — command run, output observed
2. [TRACED] — read the source; claim holds at line level
3. [READ] — appears in document; code not traced
4. [ASSUMED] — training knowledge or inference; no source confirmed

**Verdict requires ≥ TRACED for load-bearing claims.**

**Questions to run:**
- What is the highest evidence tag this claim can honestly carry?
- Does the evidence actually support the claim, or does it support a weaker version?
- Is there a source that contradicts this claim?
- R10: if this quantity appears in ≥2 sources, are both values cited with denominators?

**Common F3 findings:**
- Claim is [READ] but the code tells a different story [TRACED]
- Two sources cite the same metric with different denominators — one is not the other
- "Automatically" appears in docs but the code requires manual approval
- Badge value is accurate as of last measurement but is not CI-enforced

---

## F4 — GOODHART

**Role:** You are evaluating whether measuring X corrupts X.

Goodhart's Law: when a measure becomes a target, it ceases to be a good measure.

**Questions to run:**
- If a developer optimizes for this metric, what behavior does that incentivize beyond
  the metric's intent?
- Is there a cheap way to score well on this metric without achieving the underlying goal?
- Does the metric stay meaningful as the system matures, or does it become gameable over time?
- Is the metric self-reported? If so, what prevents optimistic reporting?

**Common F4 findings:**
- Ceremony metric (did the gate fire?) rewarded at the same weight as outcome metric
  (was the decision right?)
- Hook that warns about missing gates incentivizes defensive gate invocations on trivial
  tasks to silence the warning, inflating the metric without improving outcomes
- Depth rubric tells users what vocabulary to use to claim DEEP, making honest SURFACE
  catches look like shallow DEEP catches
- Self-reported metric (WORKED/FAILED) can be gamed by always reporting WORKED

---

## F5 — TRUST / SELF-MODIFICATION

**Role:** You are evaluating whether this breaks the trust model or creates uncontrolled self-modification.

**Questions to run:**
- Who can modify what, without review?
- What is the rollback path for each modification type?
- Is the rollback visible? (Rollback exists ≠ rollback visible)
- Does auto-apply of any artifact remove the developer's ability to audit what changed?
- Is the modification scoped to safe artifacts (skill text) or does it touch code/config?
- What happens when an auto-applied patch is wrong?

**Common F5 findings:**
- SKILL_EDIT auto-applies without showing the developer what changed (git is the
  rollback but the diff is not surfaced at patch time — rollback exists, visibility doesn't)
- CODE_EDIT bypass: safe_types parameter allows escalation if misused
- Auto-applied patches accumulate without a periodic review surface

---

## F6 — ADOPTION-ECONOMICS

**Role:** You are evaluating whether the cost/benefit is favorable for a new adopter.

**Questions to run:**
- What does adoption require? (install, config, dependencies, behavioral change)
- What is the first session where the adopter experiences the claimed benefit?
- What is the ceremony cost per session? (additional time, friction, tool calls)
- What does the adopter lose if they stop using the system? (lock-in)
- How does this compare to the zero-cost alternative (no system, manual workaround,
  or a simpler competing system)?

**Common F6 findings:**
- Benefit is deferred N sessions but cost is immediate
- Install requires Docker + 2 MCP servers while the competing product requires zero install
- Ceremony warning fires on XS tasks (false positive), annoying the developer on the
  sessions where it's least relevant
- Lock-in: knowledge is in custom format that doesn't survive tool switch

---

## F7 — SCALE / FAILURE

**Role:** You are evaluating what breaks at scale or under adversarial conditions.

**Questions to run:**
- What happens at 10×, 100×, 1000× the assumed scale? (sessions, data, users, tasks)
- What fails under adversarial use? (developer gaming the metric, bad faith inputs)
- What fails when external dependencies are unavailable?
- What is the worst-case latency or degradation mode? Is it bounded?
- What accumulates over time and eventually becomes a problem?

**Common F7 findings:**
- File-based retrieval becomes a keyword-collision bottleneck at large knowledge bases
- Audit log grows unbounded without a rotation or archival mechanism
- route-task-ran.json is overwritten (not a scale issue) but session boundary detection
  relies on timestamp comparison with edge cases at fast session starts
- Self-reported dataset has no external anchor; at 200 sessions, even a rising trend
  is unconfirmable without a cohort

---

## Frame-Generation Round

After F1–F7 exhaust with zero new objections:

1. Ask: "Is there a frame not in F1–F7 that the specific structure of this target makes necessary?"
   Consider: definitional ambiguity in the promise, measurement/denominator equivocation,
   trust model peculiarities, adoption-tier confusion.

2. If a frame is generated: name it (F8, F9...). State:
   - What the frame attacks (definitional domain, trust domain, measurement domain, etc.)
   - Which items it is relevant to (narrow scope is valid — document which items are in/out)
   - Apply it to all relevant items; document non-application to irrelevant items

3. A generated frame that produces a material objection must be applied to ALL already-converged
   items that are in its scope — even if they previously passed. Document re-application results.

**Example generated frame (F8 from this pack's Phase A run):**
> F8 — DEFINITIONAL EQUIVOCATION: When the promise uses a term that has two distinct
> meanings in the target's context, and the evidence supports one meaning but the promise
> implies the other. Applied to: claims using "compounding" (developer compounding vs.
> context compounding are distinct claims with different evidence requirements). Inapplicable
> to: claims that do not use "compounding" as a load-bearing word.
