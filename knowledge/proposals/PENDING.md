# youk Proposals — PENDING

Proposals queued for review. Each entry is a specific, actionable change to youk.
See knowledge/proposals/ACCEPTED.md and knowledge/proposals/CLOSED.md for history.

---

## PENDING-CCR-20261123-001 — 2026-11-23
**Target:** servers/core/src/compaction.py
**Change:** Add a proactive early-compaction threshold so build_brief() flags "compact soon" at ~70-75% token budget, before the agent hits the context ceiling.
**Reason:** CompactionBench (Nov 2026 preprint) shows reactive compaction — triggered at the token limit — forces summarization under pressure when context is already saturated. APEC's off-critical-path approach prepares the brief with headroom remaining, cutting latency and improving summary quality. Source: https://www.preprints.org/manuscript/202611.0780
**Before:** 
**After:** 
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** build_brief

---

## PENDING-CCR-20261123-002 — 2026-11-23
**Target:** servers/core/src/compaction.py
**Change:** Add a `verbosity` parameter ("concise" | "detailed") to MCP tool responses so agents can request terse output when context budget is constrained.
**Reason:** Anthropic's tool-writing guide (2026) documents that a response-format enum cuts token use by ~2/3 for concise mode with equivalent information. This extends compact_context's existing tier-tagging with a runtime verbosity lever. Source: https://www.anthropic.com/engineering/writing-tools-for-agents
**Before:** 
**After:** 
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** build_brief / compact_context tool schema

---

## PENDING-CCR-20261123-003 — 2026-11-23
**Target:** skills/orchestrate/SKILL.md
**Change:** Add an explicit sub-agent summary ceiling instruction: any sub-skill invocation result must be distilled to ≤1,500 tokens before returning to the lead session; full detail archived to a named file.
**Reason:** Anthropic's multi-agent research system (2026) found token usage explains 80% of performance variance. Sub-agents returning 1,000–2,000 token summaries to the lead agent, with detail isolated in the sub-agent's context, was the highest-leverage intervention. The orchestrate skill currently has no summary ceiling. Source: https://www.anthropic.com/engineering/multi-agent-research-system
**Before:** 
**After:** 
**Status:** PENDING
**ChangeType:** SKILL_EDIT
**TargetSection:** Phase 2 — DELEGATE (or equivalent sub-skill invocation phase)

---
