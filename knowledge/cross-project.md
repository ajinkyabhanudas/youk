# Cross-project learnings

Patterns observed across canopy, youk, and adjacent projects.
Referenced by session_start (session_plan generation) and self_heal.

---

## Planning before execution is first-class

**Pattern:** Every session needs a plan. Every M+ task needs route_task called first.
Skipping either causes ceremony mismatch and context drift.

**Why this matters (canopy evidence):**
Sessions without an upfront plan consistently produced:
- Sub-task expansion: a "quick fix" became a 4-hour refactor because scope was
  never stated at the start
- Primary objective burial: by exchange 15, the original goal was buried under
  sub-task context
- 15-minute re-establishment tax per session — time spent reconstructing "where
  were we?" that structured session_start eliminates

**How youk encodes this:**
- session_start returns session_plan: 3-5 items generated from context (resume point,
  pending proposals, missed close-cluster, project-type nudge, first active contract)
- CLAUDE.md surfaces the plan in the first response as a proposal, not a question
- /plan workflow command rebuilds the plan mid-session if scope changes
- route_task gates every M+ task with ceremony proportional to risk

**The rule:** The system proposes the plan from structured knowledge. The engineer
redirects in one line if wrong. Never ask "what do you want to do today?"

---

## Context contracts survive via files, not conversation

**Pattern:** Behavioral agreements stated mid-conversation (commit format, test cadence,
review requirements) must be written to contracts.md immediately — not trusted to
survive Claude's auto-compaction.

**Why this matters:**
Auto-compaction treats all content equally by recency. A 300-word explanation
receives the same preservation weight as "small commits, explain each one" — even
though the behavioral instruction is load-bearing and the explanation is recoverable.
When the explanation survives and the instruction gets softened to "user wanted specific
commits," behavior drifts silently.

**How youk encodes this:**
- session_end(explicit_contracts=[...]) writes contracts verbatim to contracts.md
- session_start loads contracts first, always, before anything else
- compact_context() pins contracts verbatim at the top of every brief
- Tier hierarchy: CONTRACT (verbatim) > DECISION (summarised) > EXPLORATION (compressed)
  > CLARIFICATION (dropped)

---

## Error states are first-class UX, not afterthoughts

**Pattern (from canopy):** Error states must be designed before the happy path,
not after. When error handling is retrofitted, it is inconsistent and often breaks
the loading/success states it surrounds.

**How youk encodes this:**
- verify/SKILL.md: every error state in the implementation must have a test
- nfr-check Q2 (idempotency) surfaces early whether the operation is safe to retry
- dev-loop ESCALATION BLOCK at iteration 3: if not converged, stop and diagnose

---

## Dual-layer validation, not single-layer

**Pattern (from canopy):** Application-layer validation (regex, type checks) and
infrastructure-layer validation (DB constraints, statement_timeout) must both exist.
Relying on only one layer creates bypass risks and silent failures.

**How youk encodes this:**
- nfr-check Category 3 (State Management) surfaces this for DB-touching tasks
- python_postgresql project type triggers "run nfr_check before touching schema"
  nudge in session_plan

---

## When to reference this file

- session_start: _generate_session_plan reads project_type and close_cluster_missed,
  applies relevant nudges from this file
- self_heal: _generate_findings should check audit history for patterns that match
  known anti-patterns above and generate targeted proposals
- new skills: before writing a new SKILL.md, check here for patterns that should
  be baked into the skill's quality bars
