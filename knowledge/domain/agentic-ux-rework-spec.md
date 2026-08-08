# Agentic-UX rework — the cognitive-load / symbiosis redesign (durable anchor)

Written mid-session (2026-08-08) before a /compact. This is the load-bearing reasoning so it
survives compaction. Next session: run the TWIN DERIVATION (below) and check for convergence.

## The problem (user's words, distilled)
youk's north star ("compound the developer") got operationalized as GATE CEREMONY (route → nfr →
challenge → adr → review). That ceremony is now cognitive load the developer CANNOT metabolize.
The thing meant to TEACH has become the thing that PREVENTS learning. Failure signature (exact):
the reasoning is GOOD, but info load + speed are so high the developer STOPS READING → shifts to
trust-and-skim → only interjects when a skim catches a miss → then MUCH LATER, comprehension debt
comes due and they're back cross-examining an old feature's implementation. That lag between
"built" and "actually understood" IS the acceptance failure. Human-machine integration not
reaching acceptance.

## Compounding — the user's REFRAME (critical, do not lose)
"Compounding the developer" is NOT: (a) youk narrating in the next prompt what it would otherwise
do, nor (b) youk doing everything autonomously so the human ATROPHIES (dependency = the vision's
named failure mode). It IS a SYMBIOSIS: youk takes on more autonomous, cross-project execution so
the human focuses on creative/discovery work — WHILE the human retains the ability to understand
what was done, absorbing decision reasoning PEDAGOGICALLY, at a pace + load they can process. BOTH
must be true: youk does more AND the human's understanding keeps up. Today only the first is true.

## The diagnostic fork — RESOLVED by the user
Why does the developer stop reading? Answer given: "I can't tell do-vs-teach apart." NOT too-much,
NOT redundant — the reasoning is ONE UNDIFFERENTIATED STREAM doing two incompatible jobs:
- EXECUTION reasoning = youk justifying choices to ITSELF so it does the work right (blast-radius,
  gate output, why-this-file). You need it to have HAPPENED, mostly don't need to READ it.
- COMPREHENSION reasoning = the ~10% that changes the HUMAN's mental model (a real trade-off, a
  foreclosure to veto, a pattern to internalize). This is what teaches.
Fused into one channel at one depth → to find the 10% for you, you read the 90% of youk thinking
out loud → can't skim safely, can't read fully → stop, trust, pay comprehension debt later.
This is the SAME disease as the rest of this session: entanglement (state/schema, capability/wiring).
Fix rhymes: SEPARATE the two, give each its own contract.

## The architectural model (converged from CLT + expertise-reversal + trust-calibration + agentic-UX)
TWO CHANNELS, not one firehose:
- CHANNEL 1 — EXECUTION (do): youk does the work with full internal reasoning + gates, but that
  reasoning is NOT the primary surface. Runs, auditable, expandable, DEFAULT QUIET.
- CHANNEL 2 — COMPREHENSION (teach): a SEPARATE, paced, EXPERT-CALIBRATED account whose only job
  is keeping the human current. Answers "what changed in your system's mental model + what would
  you want to have caught?" — NOT "what I did." Ruthlessly filtered (only load-bearing decisions,
  foreclosures, patterns), expert-calibrated (assumes basics — expertise-reversal fix), PACED (can
  accrue + surface at a natural boundary — a comprehension DIGEST at task/session end), and
  trust-building (shows youk's track record per decision-class so trust CALIBRATES).

## The CONTROL MODEL — settled by the user ("loud on demand, quiet default")
The core invention: THE SYSTEM MUST NEVER DECIDE THE HUMAN'S COGNITIVE DEPTH FOR THEM. Original sin
was youk picking "max depth always" with no dial.
- DEFAULT: quiet. youk executes; reasoning collapses to one line.
- ALWAYS-VISIBLE: a per-step CONFIDENCE/RISK SIGNAL (like the wiring pulse — glanceable). e.g.
  "0.9 confident, low blast-radius" vs "novel, irreversible, 0.5". This is a METACOGNITIVE CUE —
  tells the human how much to trust THIS step; they spend attention proportionally. This is what
  makes trust CALIBRATE instead of collapsing to all-or-nothing.
- EXPAND-ON-DEMAND: full execution reasoning, when the signal makes them want it.
- Channel 2 digest accrues independently of what was expanded live.

## Agentic UX — the reframe that makes this the PRODUCT, not a nicety
Simple UI/UX: "is this screen usable?" Agentic UX: "what is the right RELATIONSHIP between a human
and an autonomous agent that acts, learns, compounds over time?" youk's differentiator was NEVER
the gates — it's the RELATIONSHIP: does more over time (a), keeps you understanding (b), earns
trust per decision-class (c), compounds YOUR judgment not just its context (d). That whole claim is
an AGENTIC-UX claim. So the two-channel + confidence-signal model may BE the product; gates are
plumbing, the relationship is the thing. "Fix cognitive load" and "prove why youk is powerful" are
the SAME problem.
Angles agentic UX adds that plain UX misses:
1. Trust calibration over a RELATIONSHIP ARC (session 1 loud → session 40 earned-quiet), not a session.
2. Agency negotiation — human sets the autonomy boundary; youk respects + expands it as trust grows.
3. Legibility of an autonomous actor — auditable + interruptible WITHOUT demanding constant attention.
4. Compounding as a MEASURABLE relationship property: does needed-oversight DECREASE while
   understanding stays current? That is the v1 north-star metric (ties to ADR-010 metric C:
   developer_autonomy_rate, health.py:391 — already instrumented, needs elevating).

## THE METHOD FOR NEXT SESSION (user's instruction, verbatim intent)
Spec it TWO INDEPENDENT WAYS, kept APART, then check for AGREEMENT (adversarial-independence — two
isolated derivations converging is far stronger than one):
- DERIVATION A — RESEARCH-GROUNDED: pull the literature (web search was spend-limited this turn).
  Cognitive Load Theory (Sweller: intrinsic/extraneous/germane), Expertise Reversal Effect,
  Trust in Automation / Levels of Automation (Lee & See; Parasuraman & Sheridan), Progressive
  Disclosure (Nielsen), recent Agentic UX / Human-AI Interaction guidelines (Amershi et al. 18
  guidelines; 2024-2026 agentic-UX writing). Derive the redesign from what's established.
- DERIVATION B — FIRST PRINCIPLES: derive from youk's own facts + this session's frames, no
  external appeal. Start from "entanglement of do vs teach" and build the two-channel model cold.
- Keep them from contaminating each other. Then: where do A and B AGREE? Agreement = high-confidence
  design. Where they DIVERGE = the genuinely uncertain parts that need the user.

## Confirmed decisions (don't re-litigate)
- Diagnostic: do-vs-teach entanglement (channel problem), confirmed by user.
- Control: loud-on-demand, quiet-default, per-step confidence signal, human owns the depth dial.
- Frame: this is agentic UX and may be THE product, not a feature.
- Method: twin derivation (research + first-principles), check convergence.

## Open (for after the twin derivation)
- How aggressively Channel 1 quiets vs. real-time interruptibility (leaning: risk-escalated, but the
  signal-on-demand model may make this moot — human pulls when signal flags).
- Where the confidence/risk signal's numbers COME FROM (what makes youk "0.9 confident" — needs a
  real basis, not a vibe; else it's theater like the early wiring pulse false-green).
- Whether Channel 2 is a skill, a hook, an output-contract change, or a new subsystem.
- v1 tie-in: this redesign likely REDEFINES ADR-010 metric C (oversight-decrease + understanding-
  current) — richer than raw autonomy_rate.
