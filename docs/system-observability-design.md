# System observability: the stage map + grounding log

> Anchor document. Every phase below must re-read this file before starting.

## The real problem this exists to solve

Across three subsystems built this session (the verification pipeline,
problem-space-modeling, pattern-learning-architecture), there are now five
real event files (`events.jsonl`, `disposition-log.jsonl`,
`confirmed-patterns.jsonl`, `global-patterns.jsonl`, plus the verification
pipeline's own claim files) and no single place that shows every stage
together, or which ones have actually fired versus only exist in code.

The founder's real, sharper goal: identify where youk relies on LLM
judgment versus real deterministic rules, log every real judgment call so
it can be checked later for drift or bias, and see the whole system's flow
stage by stage without re-deriving it from memory or old conversation.

## Real gap found while scoping this: the biggest judgment call is unlogged

`skills/nfr-check/SKILL.md`'s "Domain scope" step (CIR-165) names 2-4
knowledge domains per task -- the single heaviest judgment call in the
whole system -- and writes nothing durable. It happens in-session and
leaves no trace. Fixed as part of this initiative, not deferred: a real
`state/domain-scope-log.jsonl` entry per real invocation.

## Part 1: the Stage Registry

A committed file, `docs/system-map.yaml`, listing every real stage across
all three subsystems. Not hand-maintained prose -- a flat list, one entry
per stage, each with:

```yaml
- name: domain_scope_naming
  grounding: llm_judgment   # deterministic | llm_judgment | hybrid
  subsystem: problem-space-modeling
  triggers_on: "nfr-check CLASSIFY phase, M+ task"
  reads: []
  writes: [state/domain-scope-log.jsonl]
  real_log: state/domain-scope-log.jsonl
- name: detect_reversals
  grounding: deterministic
  subsystem: pattern-learning-architecture
  triggers_on: "self-heal AUDIT phase"
  reads: [state/confirmed-patterns.jsonl, state/disposition-log.jsonl, DECISIONS.md]
  writes: [state/domain-brief-known-sources/]
  real_log: null   # mechanical, no separate judgment log needed
```

`grounding` is the field that answers the founder's actual question:
`deterministic` stages are pure code (same input, same output, every
time); `llm_judgment` stages are a real human/session decision with no
mechanical check; `hybrid` stages (Phase C/D's domain/sub_domain naming
feeding a mechanical promotion guardrail) are both.

## Part 2: a real status-check function, not memory

`scripts/system_status.py` (or similar): reads the registry, then reads
the REAL file each entry points to, and reports per stage -- has it ever
fired, when last, how many times. For `llm_judgment`/`hybrid` stages,
additionally surfaces the real logged decisions themselves (e.g. every
real domain-scope naming, so a human can scan for repeated/suspicious
patterns -- the actual drift-and-bias check the founder asked for).

Never invents a status for a stage with no real log -- "never fired" and
"no log exists for this stage" are reported as distinct states, not
collapsed into one.

## Part 3: the live dashboard, extended not replaced

The existing Verification Ledger artifact
(https://claude.ai/artifact/PPREQs6YRFfvK1PvmafyoU) already does exactly
this for one subsystem. Generalize it to read `system-map.yaml` plus every
real log file across all three subsystems, colored by real status (never
fired / fired once / stale / active) and by `grounding`
(deterministic/judgment/hybrid), so a judgment-heavy stage is visually
distinct from a mechanical one at a glance.

## Going forward

Every new ticket's DONE-MEANS from this point includes one line: add this
stage's real entry to `docs/system-map.yaml`. Upkeep happens as a byproduct
of normal work, not a separate maintenance pass that goes stale.

## Phased build

- Phase 1: `state/domain-scope-log.jsonl` + the real skill-content wiring
  to write it (closes the biggest unlogged judgment call first).
- Phase 2: `docs/system-map.yaml`, populated with every real stage across
  all three subsystems, classified by `grounding`.
- Phase 3: `scripts/system_status.py`, the real status-check function.
- Phase 4: dashboard generalization (extends the existing artifact).

Real progress tracked in `state/system-observability/progress.json`.
