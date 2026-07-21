# youk Philosophy

The principles behind every design decision.

---

## 1. Ambient over activated

JARVIS doesn't need to be turned on. youk is the same. No "activate youk" phrase. No routing announcements. It's just how Claude works — the structure is there, proportionate to the task, invisible when it shouldn't be visible.

## 2. Extract, don't log

The worst AI memory system is an ever-growing transcript. youk never logs what was said. It extracts what was learned — structured insights with analogy, break points, and routing implications. An entry that doesn't improve future routing or prevent future misinterpretation has no place in `knowledge/`.

## 3. Propose, never auto-apply — except for skill text

youk can observe patterns, generate health reports, and propose improvements to its own skills, guard rails, and routing logic. Code changes and config changes never apply without founder approval — the hard rule `no-auto-apply-proposals` is not optional for those. The system that rewrites itself without oversight is not an assistant — it's a liability.

The exception is skill text (SKILL.md files). When a skill fails mid-session and the gap has a concrete fix, Claude may patch the SKILL.md immediately — within the same session, before continuing. This is deliberate: a skill that silently fails is worse than one that self-corrects. The patch is to instruction text, not to code that runs — the risk profile is different. If the patch is wrong, the next `assess_skill()` will surface it.

## 4. Guard rails are versioned contracts

A guard rail that lives in a prompt is a suggestion. A guard rail that lives in `config/guardrails.yaml`, enforced at the tool level, and changed only via a git commit is a contract. Hard rules block. Soft rules nudge. Both are explicit, readable, and auditable.

Current hard rules (see `config/guardrails.yaml` for the authoritative list):
- `no-auto-apply-proposals` — skill/code changes require explicit `apply_proposal(confirmed=True)`
- `no-credential-commits` — `.env`, `*secret*`, `*api_key*` files are blocked from commits
- `knowledge-extraction-not-logging` — raw transcripts never written; only structured insights
- `no-destructive-without-confirm` — `rm -rf`, `reset --hard`, `--no-verify` require per-operation confirmation
- `lint-before-commit` — `ruff check servers/` + `pytest tests/` must pass; `--no-verify` is itself blocked

## 5. Ceremony proportional to risk

XS task: respond directly. XL task: full architecture ceremony. The failure mode to avoid is applying the same process to a typo fix and a new authentication system. `route_task()` sizes first so structure is never a tax on small work.

## 6. Variants are forms of intelligence

youk-code is good at engineering. youk-pm would be good at product thinking. They share a core but have different expertise. Adding a variant is not adding complexity — it's increasing the range of intelligent forms available. The platform scales by specialization, not by cramming everything into one server.

## 7. The repo is the truth

Skills, guard rails, routing logic, and knowledge all live in the repo. Changes flow: insight → structured entry → approved proposal → git commit → deployed. Nothing important exists only in memory or in a running container. The repo is what makes youk reproducible on any machine in one command.

## 8. Build the foundation right, then build fast

Phase 1 is not a prototype. It's the permanent foundation. The MCP server pattern, the knowledge types, the guard rail structure, the Docker volume strategy — these don't get refactored in Phase 2. Phase 2 adds memory extraction and health reporting. Phase 3 adds variants. Each phase is additive. Nothing structural changes.

## 9. Adapt within the session, not between them

The failure mode of batch self-improvement is lag: observe a gap today, fix it in two sessions. An adaptive system fixes within the session where the gap is observed. When a skill fails, `assess_skill` runs immediately. When a route is wrong, the correction is saved as a contract now, not at session end. The audit log accumulates what couldn't be fixed in-session — structural changes that need human review. Everything else closes the loop before the conversation ends.

## 10. Compound the developer, not just the context

A memory system that makes Claude smarter without making the developer smarter is solving the wrong problem. The failure mode is dependency: the developer needs youk to perform well, rather than performing better because of youk.

`/learn` exists to prevent this. At every `/done`, it extracts the session's teachable patterns — bridging what was done to what the developer already knows, naming the concepts they encountered, flagging what was genuinely new. The output is not a file Claude reads next time. It is a structured explanation the developer can internalize.

The test: after 20 sessions, does the developer catch NFR gaps before nfr_check does? Do they structure decisions before /adr prompts them? Do they write code that gets fewer review flags? If yes, youk is compounding the developer. If not, youk is compounding the context — which is useful, but not the north star.
