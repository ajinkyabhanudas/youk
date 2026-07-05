# youk Self-Heal Proposals

*Pending founder review. Hard rule: no-auto-apply-proposals.*
*Approved proposals are removed from this file and committed to the relevant config/skill file.*

---

<!-- Proposals are appended here by youk-core.self_heal() and session_end() -->

## PENDING-20260705155022 — 2026-07-05
**Target:** servers/core/src/health.py
**Change:** self_heal: detect projects with 5+ sessions and 0 contracts
**Reason:** self_heal had no check for the silent failure where contracts were verbalized but never persisted (save_contract never called). Projects with 5+ sessions but zero entries in contracts.md indicate this failure. The contract_capture_failure check exists but fires on missing contracts.md — not on a present but empty contracts.md.
**Before:** 
**After:** In _check_contract_health(): after checking contracts.md exists, also check if it has zero non-header lines (empty file). If session_count >= 5 and contracts file exists but has no contract entries (only the ## Contracts header), emit finding: "Project has {n} sessions but contracts.md is empty — agreements verbalized in sessions were never persisted. Trigger: mention a working agreement and verify save_contract() fired immediately."
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** _check_contract_health
**Content:**
```
In _check_contract_health(): after checking contracts.md exists, also check if it has zero non-header lines (empty file). If session_count >= 5 and contracts file exists but has no contract entries (only the ## Contracts header), emit finding: "Project has {n} sessions but contracts.md is empty — agreements verbalized in sessions were never persisted. Trigger: mention a working agreement and verify save_contract() fired immediately."
```

## PENDING-20260705155026 — 2026-07-05
**Target:** servers/core/src/session.py
**Change:** session: _detect_project_type — handle Docker-based Python (no requirements.txt at root)
**Reason:** _detect_project_type returned unknown for the youk repo itself — a Docker-based Python project where requirements.txt lives in servers/*/requirements.txt not at root. The _detect_stack_context() function added this session does detect it correctly, but _detect_project_type is still used in session_plan generation and may show "unknown" for the youk codebase.
**Before:** 
**After:** In _detect_project_type(): after checking root requirements.txt, also glob for servers/*/requirements.txt and servers/*/pyproject.toml. If found and project_dir contains a Makefile + docker-compose or Dockerfile → classify as python/docker rather than unknown. This makes youk classify itself correctly.
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** _detect_project_type
**Content:**
```
In _detect_project_type(): after checking root requirements.txt, also glob for servers/*/requirements.txt and servers/*/pyproject.toml. If found and project_dir contains a Makefile + docker-compose or Dockerfile → classify as python/docker rather than unknown. This makes youk classify itself correctly.
```

## PENDING-20260705-compact-intent — 2026-07-05
**Target:** servers/core/src/compaction.py
**Change:** compact_context: add intent parameter to prioritize by importance, not recency
**Reason:** compact_context() currently preserves what's most recent. High-value context (NFR decisions, architectural choices from early in session) gets squeezed out by recent tool call output. The Tier priority (CONTRACT > DECISION > EXPLORATION > CLARIFICATION) is documented in CLAUDE.md but not enforced in code.
**Before:** build_brief(project_dir: str) → dict
**After:** build_brief(project_dir: str, intent: str = "") → dict. When intent is provided: contracts always pinned verbatim; NFR Decision Blocks matching the intent keyword pinned verbatim; exploration/tool-call output compressed to 1 sentence per block; clarification exchanges dropped. The intent parameter propagates from compact_context MCP tool.
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** build_brief
**Content:**
```
Extend build_brief(project_dir, intent="") to accept an optional intent string.
When intent is provided, apply Tier priority in output ordering:
1. Contracts (verbatim, always first — CONTRACT tier)
2. NFR Decision Blocks that contain intent keywords (verbatim — DECISION tier)
3. Resume point and session plan (1-2 sentences — DECISION tier)
4. Recent tool call output (compress to 1 sentence each — EXPLORATION tier)
5. Clarification exchanges (drop entirely — CLARIFICATION tier)
The intent string is passed from the compact_context MCP tool signature:
compact_context(cwd: str, intent: str = "") → add intent param to server.py tool.
Update CLAUDE.md to pass intent when calling compact_context after NFR decisions:
compact_context(cwd, intent="payment webhook nfr") preserves the NFR block verbatim.
```

## PENDING-20260705-skill-handoff — 2026-07-05
**Target:** servers/core/src/session.py
**Change:** session: pending-handoff mechanism — skill output flows into next skill input
**Reason:** Skills run independently today. nfr-check output doesn't flow into dev-loop context. code-review findings don't become the starting point for security-review. This is the difference between "a sequence of good checklists" and "a system where each discipline makes the next one better." skill-graph.yaml already encodes precedes/follows relationships — the mechanism to use them is missing.
**Before:** route_to_skill loads base skill + overlays, no prior skill context
**After:** Add pending-handoff to session.json. After nfr-check completes, Claude writes NFR Decision Block to session.json["pending_handoff"]["nfr-check"]. route_to_skill() reads pending_handoff for the next skill and prepends it to skill_content. skill-graph.yaml "precedes" edges define which handoffs are meaningful. After dev-loop reads the nfr-check handoff, it clears it from session.json.
**Status:** PENDING
**ChangeType:** CODE_EDIT
**TargetSection:** route_to_skill and session.json schema
**Content:**
```
1. Add to session.json schema: "pending_handoff": {} (key = source skill, value = output block)
2. In session.py: add write_pending_handoff(skill_name, output_block) and read_pending_handoff(skill_name) functions
3. In servers/code/src/skills.py route_to_skill(): after loading skill_content, check session.json for pending_handoff entries where source skill "precedes" the requested skill (per skill-graph.yaml). Prepend the handoff block to skill_content.
4. In CLAUDE.md: after nfr-check completes, write NFR Decision Block to pending_handoff via write_pending_handoff("nfr-check", nfr_decision_block)
5. After security-review reads code-review handoff, clear it.
Handoff structure: {"source": "nfr-check", "written_at": "ISO8601", "content": "NFR Decision Block verbatim"}
```
