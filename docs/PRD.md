# youk — Product Requirements Document

**Status:** Active development — v0.1.0
**Owner:** Ajinkya Bhanudas
**Last updated:** 2026-07-01

---

## Vision

Every Claude Code session should be smarter than the last. youk makes this happen by persisting context across sessions, routing tasks to the right ceremony, and evolving its own skills from observed patterns — without requiring the developer to do anything differently.

The north star: a developer who has used youk for 20 sessions gets measurably better output from Claude than one who hasn't — not because they prompted better, but because youk already knows their working agreements, architecture decisions, and skill gaps.

---

## Users

**Primary:** Solo developer or 2-5 person engineering team using Claude Code daily for non-trivial software work. Experienced engineers who find generic AI assistance increasingly limiting as a project grows.

**Not targeted:** Developers doing one-off scripts or exploratory prototypes. youk's compounding value only emerges across multiple sessions on the same project.

---

## Problems being solved

| Problem | Without youk | With youk |
|---|---|---|
| Context loss | Re-explain project every session | Picks up where you left off — automatically |
| Generic routing | Same ceremony for a typo and an architecture change | XS→XL sizing; skill ceremony matched to task risk |
| Lost working agreements | "always use small commits" lives in chat, then vanishes | Written to contracts.md, loaded verbatim next session |
| Recurring gaps | Same mistake corrected repeatedly | Audit logs feed skill evolution; gaps become proposals |
| Blind to industry | Can't discover "Anthropic published a better pattern" | youk-research scans external sources weekly |
| Cold-start cost | First session on a new project burns tokens on setup | Heuristic bootstrap initializes context at zero API cost |

---

## Non-functional requirements

These are non-negotiable constraints. Any feature that violates them is out of scope.

### NFR-1: Token overhead ceiling
**youk overhead per session ≤ 20% of the session's task token budget.**

Rationale: if running youk costs more tokens than the work it enables, developers will stop using it. This is the north star metric — measured via `track_tokens` → audit log → health.py `_score_org`.

Implications:
- Hot path (session_start, route_task, compact_context, track_tokens) must be zero-API — file-based only
- CLAUDE.md budget: max 1,800 tokens; any addition must remove something of equal size
- Research tools (youk-research, assess_skill, generate_skill) run off the hot path only
- Haiku-first for all research: `claude-haiku-4-5-20251001` for scanning, Sonnet only for proposal generation

### NFR-2: Zero footprint in project repos
youk writes nothing to the developer's project repo. All knowledge, audit logs, and context files live under `~/.claude/`. This is enforced by the `knowledge-extraction-not-logging` hard rule.

### NFR-3: Propose, never auto-apply
Any self-generated improvement (skill edits, config changes, file creates) is queued in `PENDING.md` and requires explicit founder approval via `apply_proposal(confirmed=True)`. Enforced at tool level.

### NFR-4: Hot path latency
session_start, route_task, compact_context — each must complete in under 500ms under normal conditions (no Docker cold-start). These are called on every session and must not block the developer.

### NFR-5: CLAUDE.md budget
Max 1,800 tokens in CLAUDE.md. Measured: `wc -c ~/.claude/CLAUDE.md` ÷ 4. Enforced by convention; doctor.sh warns if exceeded.

---

## Functional requirements

### FR-1: Session continuity
**Requirement:** A session on project P must always include: last resume point, active contracts, pending proposal count, and a forward-looking session plan — without the developer asking.

**Acceptance criteria:**
- `session_start()` returns non-empty `resume_point` for any project with ≥1 prior session
- `contracts` list includes verbatim working agreements from prior sessions
- `session_plan` contains 3-5 actionable items, not generic advice
- Response time: < 500ms

### FR-2: Task routing
**Requirement:** Every M+ task must be routed to the correct skill set before implementation begins.

**Acceptance criteria:**
- `route_task()` returns correct size (XS→XL) for representative test cases
- M+ tasks return non-empty `skills` list and a `plan_hook` if implementation hasn't started
- Net-score routing: typo-override-signal cancels implement-signal → routes XS not M

### FR-3: Context compaction
**Requirement:** `compact_context()` must preserve CONTRACT-tier content verbatim across compaction cycles. EXPLORATION-tier is compressed. CLARIFICATION-tier is dropped.

**Acceptance criteria:**
- A contract written in session 1 appears verbatim in session 10's brief
- Compacted brief is ≤ 2,000 tokens
- No API call required

### FR-4: Skill routing and evolution
**Requirement:** Skills grow from signals. A gap observed in session N becomes a proposal by session N+3.

**Acceptance criteria:**
- `session_end(skill_gaps={"skill": ["gap"]})` writes a SkillGap: audit line
- `self_heal()` after 3+ occurrences returns the skill in `skill_gap_signals`
- `assess_skill()` called on that skill returns `proposed_additions` that map directly to `add_proposal()` calls

### FR-5: Cold-start bootstrap
**Requirement:** A developer's first session on a brand-new project (no README, no CLAUDE.md, no git history) must still receive actionable context — not "No prior context found."

**Acceptance criteria:**
- When `context_level == "L1"` and `project_type == "unknown"`: run enhanced heuristic scan
- Detected signals (Makefile, Dockerfile, test dirs, CI files, language markers) written to `context.md`
- `session_plan` item reads "First session — detected [signals] — establish contracts before coding"
- Zero API calls for bootstrap

### FR-6: Research intelligence
**Requirement:** youk must surface external best practices without developer prompting, at most weekly.

**Acceptance criteria:**
- `youk-research` skill runs via schedule, scans 4+ sources (Anthropic blog, Karpathy GitHub, OpenAI cookbook, relevant HN)
- Each pattern extracted generates one `add_proposal()` call
- Proposals appear in PENDING.md with `source_url` and `relevance_to_youk`
- Token cost per research run: ≤ 15k tokens (Haiku-first)
- Runs off the hot path — never triggered by session_start or route_task

### FR-7: Token observability
**Requirement:** Every session must produce a Tokens: line in the audit log so health.py can track overhead vs. budget.

**Acceptance criteria:**
- `track_tokens()` called at: route_task, each skill invocation, session end
- `session_end()` writes `Tokens: actual/budget (pct%)` to audit log
- `self_heal()` penalises sessions consistently >2× budget in org_score

### FR-8: Guard rails
**Requirement:** Hard rules must block at tool level, not prompt level.

**Acceptance criteria:**
- `apply_proposal(confirmed=False)` returns preview, not error
- `apply_proposal(confirmed=True)` without founder explicit confirmation: blocked (not silently applied)
- `check_command("rm -rf /")` returns `{blocked: true}`
- Credential file in commit path: blocked by `check_commit_quality()`

---

## Success metrics

| Metric | Baseline | Target (session 20) |
|---|---|---|
| Org score (health.py) | 5.8/10 | ≥ 7.5/10 |
| Close-cluster completion rate | 0% | ≥ 60% |
| youk overhead / task tokens | unmeasured | ≤ 20% |
| Skill gap recurrence rate | unmeasured | ≤ 1 recurrence before proposal queued |
| External proposals adopted per month | 0 | ≥ 2 |
| Cold-start context quality | L1 (empty) | L1-bootstrap (heuristic signals) |

---

## Token efficiency design rules

These complement NFR-1 and apply to every implementation decision:

1. **Hot path is zero-API.** session_start, route_task, compact_context, track_tokens: file-based only. No Anthropic API calls on these paths.
2. **Research is off-path.** youk-research, assess_skill, generate_skill: explicit invocation or scheduled cron only.
3. **CLAUDE.md budget: 1,800 tokens.** Measure with `wc -c | ÷4`. Any PR that increases CLAUDE.md must reduce it elsewhere.
4. **Haiku-first.** All web research and initial skill assessment uses claude-haiku-4-5-20251001. Escalate to claude-sonnet-4-6 only for proposal generation and final skill drafts.
5. **Deferred tool schemas.** MCP tool schemas are loaded on demand (via ToolSearch), not on every turn. youk's tool list stays small.
6. **Stable content first.** compact_context() puts contracts (most stable) first, then decisions, then session state. This maximises prompt cache hit rates.

---

## Roadmap

### v0.1.0 — Current (Foundation)
- youk-core + youk-code live
- Session continuity, task routing, skill lifecycle, guard rails
- track_tokens + audit health scoring
- install.sh + doctor.sh for idempotent setup
- 18 skills versioned in repo

### v0.2.0 — Research Intelligence
- `youk-research` skill — external best-practices scanning
- Weekly scheduled cron via harness schedule skill
- `self_heal(research_mode=True)` — gap-driven external search
- Cold-start bootstrap (heuristic context init)
- Innovation scoring in health.py

### v0.3.0 — Token Efficiency
- CLAUDE.md trim to ≤ 1,800 tokens (done in v0.1.0 sprint)
- Overhead tracking: `vs_budget_pct` prominently in session card
- Token ceiling enforcement: warning when session overhead > 20%
- Haiku-first research pipeline

### v1.0.0 — Production Ready
- youk-pm variant (product management, specs, ADRs)
- youk-research as dedicated Docker container with persistent web cache
- Multi-project context: `/cross-project` promoted to full skill
- Install → first meaningful session in < 5 minutes for new users

---

## Architecture constraints

All design decisions must respect:

1. **Two Docker containers only (for now).** youk-core (read-write) and youk-code (read-only). New capabilities go into one of these or wait for v1.0.
2. **Volume-mounted knowledge.** Skills and knowledge files are read at runtime via Docker volume. No rebuild required for skill updates.
3. **MCP protocol.** All capabilities exposed as MCP tools. Nothing proprietary.
4. **Idempotent install.** `bash scripts/install.sh` run twice leaves the system in the same state.
5. **CI must pass.** Any PR must pass ruff + YAML validation + Docker build + MCP handshake.
