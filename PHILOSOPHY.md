# youk Philosophy

The principles behind every design decision.

---

## 1. Ambient over activated

JARVIS doesn't need to be turned on. youk is the same. No "activate youk" phrase. No routing announcements. It's just how Claude works — the structure is there, proportionate to the task, invisible when it shouldn't be visible.

## 2. Extract, don't log

The worst AI memory system is an ever-growing transcript. youk never logs what was said. It extracts what was learned — structured insights with analogy, break points, and routing implications. An entry that doesn't improve future routing or prevent future misinterpretation has no place in `knowledge/`.

## 3. Propose, never auto-apply

youk can observe patterns, generate health reports, and propose improvements to its own skills, guard rails, and routing logic. It never applies those improvements without founder approval. The hard rule `no-auto-apply-proposals` is not optional. The system that upgrades itself without oversight is not an assistant — it's a liability.

## 4. Guard rails are versioned contracts

A guard rail that lives in a prompt is a suggestion. A guard rail that lives in `config/guardrails.yaml`, enforced at the tool level, and changed only via a git commit is a contract. Hard rules block. Soft rules nudge. Both are explicit, readable, and auditable.

## 5. Ceremony proportional to risk

XS task: respond directly. XL task: full architecture ceremony. The failure mode to avoid is applying the same process to a typo fix and a new authentication system. `route_task()` sizes first so structure is never a tax on small work.

## 6. Variants are forms of intelligence

youk-code is good at engineering. youk-pm would be good at product thinking. They share a core but have different expertise. Adding a variant is not adding complexity — it's increasing the range of intelligent forms available. The platform scales by specialization, not by cramming everything into one server.

## 7. The repo is the truth

Skills, guard rails, routing logic, and knowledge all live in the repo. Changes flow: insight → structured entry → approved proposal → git commit → deployed. Nothing important exists only in memory or in a running container. The repo is what makes youk reproducible on any machine in one command.

## 8. Build the foundation right, then build fast

Phase 1 is not a prototype. It's the permanent foundation. The MCP server pattern, the knowledge types, the guard rail structure, the Docker volume strategy — these don't get refactored in Phase 2. Phase 2 adds memory extraction and health reporting. Phase 3 adds variants. Each phase is additive. Nothing structural changes.
