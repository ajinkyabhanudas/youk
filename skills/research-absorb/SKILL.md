---
name: research-absorb
description: >
  Ingests external research (papers, blog posts, framework docs, architectural writeups)
  and routes findings into youk's knowledge layer — updating skill content, concept graph
  entries, or contracts as appropriate. Use this when you've read something new and want
  to capture what it means for youk specifically. Fires on: "absorb this paper",
  "what does this mean for youk", "extract what's useful from this", "update youk from
  this research", "I found a better approach to X". Distinct from /research which scans
  external sources proactively — this skill processes research you've already found.
  Do NOT use for: general Q&A about a paper, summarising without routing, or cases where
  the research contradicts a FIXED_CONSTRAINT (surface the conflict instead).

do-not-trigger-on: |
  General paper summaries with no youk application. Summarising for external audiences.
  Research that contradicts an existing architectural decision without surfacing the conflict.
---

# research-absorb — Research Ingestion + Routing

Point this skill at a paper, post, or doc. It extracts actionable claims, classifies each
by which youk component it applies to, stress-tests the application before proposing it,
and routes each approved finding to the right machine: skill content, concept graph,
contract, or code proposal. Nothing auto-applies — founder review always required for
CODE_EDIT targets.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(paste or URL)* | Full loop: INGEST → CLASSIFY → ROUTE → VERIFY |
| `claims only` | INGEST → CLASSIFY, stop — produce the classified claim list without routing |
| `route: [claim]` | Single claim, skip INGEST — classify and route one specific finding |
| `skill: [name]` | Constrain CLASSIFY to a single skill target — find what applies to that skill |
| `silent` | Run full loop, only surface BLOCKING classification conflicts |

---

## Context Capture (Always First)

Before any phase, extract:

```
SOURCE:    [title, author, URL or "pasted" — never fabricate a citation]
TYPE:      [paper | blog post | framework docs | architectural writeup | other]
DOMAIN:    [what is this primarily about? e.g. RAG, agent coordination, eval design, routing]
YOUK_DIR:  [current project directory — determines which skill context files to load]
FIXED:     [any youk architectural decisions that are already settled and cannot be overridden]
```

FIXED is the most important field. Read `state/session-open.json` for current slug, check
`knowledge/projects/{slug}/decisions.md` for settled decisions. Never route a claim that
contradicts a FIXED decision without surfacing the conflict explicitly.

---

## The Four Phases

Each phase begins with a compact token: `[PHASE: NAME]`

---

### Phase 1 — INGEST

`[PHASE: INGEST]`

Extract claims from the source. A claim is a specific, testable assertion — not a theme.

Rules:
- **Specificity gate:** "LLMs benefit from structured output" is not a claim. "Structured output with JSON schema constraints reduces token usage by 15–30% on instruction-following tasks (source, experiment N)" is a claim.
- **Novelty check:** for each claim, ask: does youk already do this? If yes, mark `EXISTING` — do not re-propose.
- **Evidence tier:** tag each claim with E0–E3 (see evidence ladder below). E0 (assertion) claims are noted but not routed.
- **Cap at 8 claims.** If the source has more, take the 8 most applicable to youk. More is not better — each claim that routes creates work.

**Evidence ladder for claims:**
| Tier | Basis | Route? |
|------|-------|--------|
| E0 | Author assertion, no experiment | Note only — do not route |
| E1 | Single experiment or case study | Route with caveat |
| E2 | Replicated across ≥2 independent experiments | Route |
| E3 | Meta-analysis or well-established benchmark | Route with priority |

**Output format:**
```
[INGEST]
Source: {title} — {URL or "pasted"}
Claims extracted: {N}

Claim 1: {specific, testable assertion in one sentence}
  Evidence: E{tier} — {brief basis}
  youk relevance: {one sentence — why this matters for youk specifically}
  Status: NEW | EXISTING (already in {skill/contract/concept})

Claim 2: ...
```

---

### Phase 2 — CLASSIFY

`[PHASE: CLASSIFY]`

For each NEW claim, determine the target component in youk. Classification is exclusive —
one claim, one target. If a claim applies to multiple targets, split it.

**Classification table:**

| Target | When to route here | Tool |
|--------|-------------------|------|
| `SKILL_EDIT:{skill_name}` | Claim changes how a skill should run its phases | `assess_skill` → `add_proposal(SKILL_EDIT)` |
| `CONCEPT_GRAPH` | Claim introduces a named concept, relationship, or architectural pattern | `write_concepts` (safe auto-apply) |
| `CONTRACT` | Claim establishes a behavioral rule that should hold every session | `save_contract` |
| `CODE_EDIT:{server/file}` | Claim requires a persistent tool capability or server change | `add_proposal(CODE_EDIT, review_required=True)` |
| `ROUTING_WEIGHT` | Claim suggests a skill should fire more/less often on specific task types | `add_proposal(CODE_EDIT)` — route_task scoring change |
| `DEFER` | Claim is valid but no current youk component maps to it — note for future | Log in `knowledge/projects/youk/research-backlog.md` |

**Classification rules:**
- A claim that changes when a skill fires → `SKILL_EDIT` on the skill's description/trigger
- A claim about what a skill should *do* in a phase → `SKILL_EDIT` on that phase section
- A claim that contradicts an existing FIXED decision → **CONFLICT** — surface it, do not classify
- A claim that requires a new MCP tool → `CODE_EDIT` + note it's MCP_CANDIDATE scope

**Output format:**
```
[CLASSIFY]
Claim 1 → SKILL_EDIT:challenge — {one sentence: what changes in which section}
Claim 2 → CONCEPT_GRAPH — {concept name + one-line definition}
Claim 3 → CONTRACT — {the behavioral rule as a contract string}
Claim 4 → DEFER — {why no current component maps to this}
Claim 5 → CONFLICT: contradicts ADR-007 ({decision text}) — surface before routing
```

---

### Phase 3 — ROUTE

`[PHASE: ROUTE]`

For each classified claim, run the appropriate action. Order: CONFLICT checks first, then
safe-auto targets (CONCEPT_GRAPH, CONTRACT), then review-required targets (SKILL_EDIT,
CODE_EDIT).

**CONFLICT handling (mandatory first):**
If any claim is classified CONFLICT: surface it now. State the claim, the conflicting
decision, and what updating youk would cost. Do not proceed to route other claims until
the founder resolves the conflict. Options: (A) drop the claim, (B) update the ADR.

**CONCEPT_GRAPH route:**
```python
# Concepts are safe-auto — no stress-test required (additive, non-destructive)
# Format the concept as: {"label": "...", "definition": "...", "source": "paper title"}
# Call write_concepts() or add to knowledge/domain/{slug}.md manually
```

**CONTRACT route:**
```python
# Contracts are load-bearing — stress-test before save_contract
# Stress-test: would this contract cause a false positive on any existing session?
# If stress-test BLOCKING → revise contract wording. If PASSED → save_contract(text, cwd)
```

**SKILL_EDIT route:**
1. Call `youk-code.assess_skill(skill_name)` — check if proposed addition conflicts with existing content
2. If no conflict: `youk-core.add_proposal(change_type="SKILL_EDIT", target="skills/{name}/SKILL.md", content=<exact text>, target_section=<section>, review_required=False)`
3. Stress-test the proposal in context: would this change cause the skill to fire incorrectly?
4. If stress-test PASSED: `youk-core.apply_proposal(confirmed=True, safe_types=["SKILL_EDIT"])`

**CODE_EDIT route:**
1. `youk-core.add_proposal(change_type="CODE_EDIT", target=<file>, change_description=<what + why>, review_required=True)`
2. Do NOT apply — founder review required. Report: "Queued CODE_EDIT for {file} — requires review in PENDING.md."

**ROUTING_WEIGHT route:**
Same as CODE_EDIT — add_proposal only, never apply.

**DEFER route:**
Append to `~/.claude/youk/knowledge/projects/youk/research-backlog.md`:
```
## {claim summary} — {source}, {date}
{why no current component maps here}
{what would need to exist for this to route}
```

---

### Phase 4 — VERIFY

`[PHASE: VERIFY]`

After routing all claims, run a final coherence check:

1. **No orphaned claims:** every non-DEFER claim produced an action (proposal, contract, concept).
2. **No silent CODE_EDITs:** every CODE_EDIT is in PENDING.md with `review_required=True`.
3. **No CONFLICT bypassed:** if any claim was CONFLICT, confirm the founder resolved it before this phase ran.
4. **Concept graph consistent:** new concepts don't redefine existing ones (check by querying `query_concept_graph` with the new concept label).
5. **Contract not duplicated:** new contracts don't restate existing ones in contracts.md.

Emit:
```
[VERIFY]
Claims routed: {N}
  SKILL_EDIT applied: {list}
  CONTRACT saved: {list}
  CONCEPT_GRAPH written: {list}
  CODE_EDIT queued (review required): {list}
  DEFER logged: {list}
  CONFLICT unresolved: {list — must be empty to close}

Session impact: {one sentence — what youk can do now that it couldn't before}
```

---

## Quality Bars (Non-Negotiable)

- **No E0 claims route.** An author's assertion without experimental backing does not modify youk's behavior. Note it, log it to research-backlog.md, move on.
- **No auto-apply for CODE_EDIT.** Server code changes require founder review — always `review_required=True`.
- **CONFLICT surfaces before routing.** A claim that contradicts a settled decision is a decision point, not a routing target.
- **Stress-test before SKILL_EDIT apply.** A skill edit that causes false-positive triggers is worse than not absorbing the research.
- **One claim, one target.** Splitting is correct; ambiguous dual-target routing is not.
- **Source is always cited.** Every proposal, concept, and contract written by this skill includes the source URL/title in its description. Undocumented provenance cannot be audited.

---

## Example Flows

**Paper on chain-of-thought prompting:**
> User pastes abstract + key findings from a CoT paper showing structured reasoning steps improve multi-hop accuracy.

INGEST: 3 claims extracted (E2, E1, E0).
CLASSIFY: E2 claim → SKILL_EDIT:challenge (structured phases reduce multi-hop errors). E1 claim → CONCEPT_GRAPH (chain-of-thought as named pattern). E0 claim → NOTE ONLY.
ROUTE: assess_skill("challenge") → add_proposal → stress-test PASSED → apply. write_concepts("chain-of-thought"). E0 skipped.
VERIFY: 2 of 3 claims routed. 0 conflicts. 0 CODE_EDITs queued.

**Blog post contradicting current routing approach:**
> Post argues flat skill lists outperform graph-based routing for <20 skills.

INGEST: 1 claim extracted (E1 — single author's production system).
CLASSIFY: → CONFLICT: contradicts ADR-007 (concept graph as first-class routing capability).
ROUTE: Surface conflict. Options: (A) drop — E1 evidence insufficient to override ADR, (B) update ADR with caveat.
Founder decides → (A) drop + log to research-backlog.md with note.

**Framework docs for a new MCP pattern:**
> User pastes MCP specification section on streaming tool responses.

INGEST: 2 claims extracted (E3 — spec is authoritative).
CLASSIFY: Claim 1 → CODE_EDIT:servers/core/src/server.py (streaming response support). Claim 2 → CONCEPT_GRAPH (streaming tool response pattern).
ROUTE: add_proposal(CODE_EDIT, review_required=True). write_concepts().
VERIFY: 1 CODE_EDIT queued. 1 concept written. Founder reviews server.py change before applying.
