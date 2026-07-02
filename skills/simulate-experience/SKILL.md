---
name: simulate-experience
description: >
  Developer experience audit skill. Simulates youk from the perspective of real
  developer personas — junior dev first install, senior dev mid-project, dev joining
  an existing-knowledge project, dev returning after a long gap. Identifies friction
  points, gaps, and missing context. Output is always a ranked list of actionable
  improvement proposals, not a narrative report. Designed to feed the self-evolution
  loop: each finding becomes an add_proposal() call, not just a recommendation.
  Triggers on: "simulate the dev experience", "test the onboarding", "what would a
  junior dev see", "walk through the experience", "red team the onboarding", any
  request to evaluate youk from a user's perspective.
---

# simulate-experience — Developer Experience Audit Skill

Walk youk's experience from the outside in. The goal is not to describe the
experience — it is to find the specific moment where a developer would lose
confidence, get confused, or receive less value than they should. Every finding
must map to a concrete improvement proposal that can be queued via add_proposal().

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | All four personas, full audit, ranked proposals |
| `persona: junior` | Junior dev only (first install, first week) |
| `persona: senior` | Senior dev mid-project (heavy user, 3+ months) |
| `persona: joining` | New dev joining a project with existing youk context |
| `persona: returning` | Dev returning after 30+ day gap |
| `persona: canopy` | Simulate against a specific project (pass project_dir) |
| `quick` | Top 3 friction points per persona only |

---

## Context Capture (Always First)

```
PROJECT_DIR:     [path to project being simulated against, or "(generic)" if none]
PROJECT_TYPE:    [detected stack, or "(unknown)"]
SESSION_COUNTER: [how many sessions exist in audit for this slug]
CONTRACTS:       [count of loaded contracts]
PRIOR_RESUME:    [last resume_point, or "(none — cold start)"]
PERSONAS:        [which personas to simulate — default all four]
```

Read the actual session_start output for the project if available. Do not simulate
from memory — call session_start and observe what it returns.

---

## The Four Personas

### Persona A — Junior Dev (First Install, Week 1)

**Profile**: Using Claude Code for the first time. Has never seen youk. Installed it
because a senior teammate said to. Doesn't know what MCP servers are.

**Simulation steps**:
1. What is the first message they see when Claude Code opens? (session card)
2. They type: "help me add a button to the form." What ceremony fires? Does it feel proportionate?
3. They ask: "what is /done?" — does the session card explain it?
4. They finish work and close the tab without typing anything. What is lost?
5. They open Claude Code the next day. Does it remember anything?

**Friction signals to look for**:
- Session card uses jargon they don't know (L1, slug, close-cluster, ceremony)
- First message is longer than they'll read
- No explanation of what just happened (youk loaded context, but how would they know?)
- They'd need to type /done and don't know it — default tab-close loses everything
- They say "always use TypeScript" mid-session — does save_contract fire immediately? If not, that agreement is gone the next time Claude auto-compacts or when the tab closes

**Output format**:
```
[PERSONA A: JUNIOR DEV]
Session #1 experience: {what they see, verbatim from session_start output}
First task experience: {what ceremony fires for "add a button to the form"}
Friction point {n}:
  Moment: {when exactly in the experience this happens}
  Observed: {what the developer sees or doesn't see}
  Impact: HIGH | MEDIUM | LOW
  Fix: {specific, one-sentence change that removes this friction}
  Proposal type: SKILL_EDIT | CODE_EDIT | CONFIG_EDIT | CLAUDE_MD_EDIT
```

---

### Persona B — Senior Dev Mid-Project (Power User)

**Profile**: 3 months in, 40+ sessions with youk on this project. Uses /build and
/done regularly. Has established contracts, decisions, resume points. Values speed.

**Simulation steps**:
1. Open session — how long does session_start take? What does the plan show?
2. Start a large refactor (/build) — does routing give M ceremony? Is nfr_check useful?
3. Ship at end of day (/done → session_end) — does the close-cluster actually fire?
4. Next morning: does resume_point reflect what was left off?
5. self_heal runs: does org_score reflect actual session quality?

**Friction signals to look for**:
- Session plan shows the same stale item every session (not dynamic)
- nfr_check silent fail if API key absent
- resume_point only captures last audit summary, not actual code state
- Token overhead invisible until /health is called manually

**Output format**: same as Persona A but `[PERSONA B: SENIOR DEV]`

---

### Persona C — New Dev Joining Existing Project

**Profile**: Different developer, fresh install of youk. The senior dev has been using
youk on canopy for 3 months. This dev is joining mid-project. Has never used youk but
has been given install instructions.

**Simulation steps**:
1. They install youk on their machine. Run `make install`.
2. Open Claude Code in the canopy directory.
3. What do they see? Does the accumulated knowledge from the senior dev load?
4. Do they feel any different from just using Claude without youk?
5. They work for a week. Does their session_end feed into the shared knowledge?

**Critical gap to check**: Is knowledge stored per-user or per-project? If per-user
(which it is — `~/.claude/youk/knowledge/`), this developer gets nothing from the
senior dev's history. There is no shared knowledge store.

**This is the team collaboration gap.** Surface it explicitly.

**Output format**: same format, `[PERSONA C: JOINING DEV]`

---

### Persona D — Dev Returning After Long Gap

**Profile**: Used youk heavily, then was off for 8 weeks. Returns to the project.
Codebase has 60+ new commits from the team. Stack may have changed.

**Simulation steps**:
1. Open Claude Code in the project directory.
2. Does session_start surface the staleness signal? ("Returning after 56 days — 63 commits")
3. Is the resume_point accurate or dangerously stale?
4. Are old contracts still valid? (No way to know — youk loads them unconditionally)
5. Is the project type still correct? (package.json may have added new deps)

**Friction signals to look for**:
- Staleness signal only appears if last-seen was written correctly (check if it was)
- Old contracts may be wrong — no contract validation mechanism
- No "things changed while you were away" summary
- Session plan shows 8-week-old resume point as if it's fresh

**Output format**: same format, `[PERSONA D: RETURNING DEV]`

---

## Team Collaboration Gap

youk knowledge is per-user (`~/.claude/youk/knowledge/`). A developer joining a project
with existing youk history on another team member's machine starts from zero — no contracts,
no decisions, no resume points transfer automatically.

**Current state:** Each developer maintains an independent youk instance. Projects accumulate
knowledge independently per user. Persona C always surfaces this.

**What would be needed to share knowledge across a team:**
1. Commit `knowledge/projects/{slug}/` to the project repo (gitignore exceptions needed)
2. Conflict resolution when two devs write different contracts.md entries
3. install.sh change to symlink per-project knowledge/ into the repo rather than ~/.claude/youk/

**When simulating Persona C:** explicitly call out this gap as STRUCTURAL (not a bug, not
fixable with a simple code change). Do not elide it or soften it — team adoption decisions
depend on understanding this limitation honestly.

---

## Synthesis Phase

After all persona simulations:

```
[SYNTHESIS]
Total friction points: {N}
By severity:
  HIGH ({n}): {brief list}
  MEDIUM ({n}): {brief list}
  LOW ({n}): {brief list}

Structural gaps (require architecture changes, not just tweaks):
  - {gap}: {what would be needed to address it}

Compound frictions (where one gap makes another worse):
  - {friction A} × {friction B} = {compound effect}
```

---

## Proposal Generation Phase (Required — Not Optional)

For every HIGH and MEDIUM friction point, generate a concrete add_proposal() call.

Format:
```python
add_proposal(
    title="...",  # max 60 chars
    rationale="...",  # one sentence: which persona, which moment, what breaks
    action="CODE_EDIT | SKILL_EDIT | CONFIG_EDIT | CLAUDE_MD_EDIT",
    target="...",  # file path relative to youk root
    content="...",  # the actual change (code diff, SKILL.md section, config key)
    target_section="..."  # function name or heading to replace
)
```

**Rule**: if you can't write the `content` field concretely, the finding is not specific
enough. Do not queue vague proposals like "improve the onboarding." Queue specific ones
like "add welcome message to _generate_session_plan() when session_counter == 1 and
contracts exist from a different install."

LOW friction points: document but do not queue proposals — too much noise.

---

## Self-Evolution Hook

After generating proposals, check:
1. Did any finding recur across multiple personas? (compound signal — higher priority)
2. Did any finding match a known SkillGap: entry from recent audit logs?
3. For compound or recurring findings: bump to HIGH if not already

The purpose of this skill is not a one-time audit. It is a recurring signal source for
the self_heal loop. Run it before each major release or after any significant feature
addition to youk itself.

---

## Quality Bars

- **Specificity**: "The session card is too long" is not a finding. "On Persona A's first
  session, the session card shows 7 items including jargon terms (L1, slug, ceremony) that
  a junior dev has no context for, causing them to skip reading it entirely" is a finding.
- **Persona fidelity**: Each persona must be evaluated from THEIR knowledge level, not
  yours. A junior dev doesn't know what MCP is. A senior dev does. Different finding.
- **Proposals must be queueable**: Every proposal must include a `content` field with
  enough detail that apply_proposal could execute it without further input.
- **Team gap honesty**: Persona C always surfaces the shared-knowledge-store gap. This
  is a structural limitation, not a bug. Surface it accurately rather than eliding it.
- **Contract capture check (required for every persona)**: At some point during each
  persona's simulation, they must verbalize a working agreement ("always X", "never Y",
  "from now on Z"). Verify: (1) save_contract fires immediately, not at /done,
  (2) the contract appears in contracts.md after the call, (3) the next session_start
  loads it. If any step fails, that is a HIGH friction finding — verbalized agreements
  that don't survive compaction silently destroy institutional memory.

## Personas
## Persona E: The Acid Test — youk developing youk

**Profile:** Simulates the youk founder using youk to build youk itself. Session ~30, active development session on the youk codebase.

**What to test:**
- Does session_start produce a brief that eliminates re-establishment cost, or does the developer still re-derive context?
- Did route_task size the last 3 tasks correctly? Were capability skills invoked each time?
- Is the /learn output (if it ran) producing pattern extractions that would prevent future mistakes?
- How many founder corrections occurred this session vs. session 1? Is the trend down?
- Did self_heal detect any of the patterns the founder caught manually?

**The acid test question:** If the founder removed youk today and rebuilt from git history + contracts.md + decisions.md alone (no session_start, no route_task), how much slower would development be? If the answer is "barely slower", youk is not compounding.

**Quality bars:**
- session_start brief must eliminate re-establishment without re-reading files
- At least 1 capability skill must have fired in the last 3 sessions
- /learn must have run in the last /done session
- Founder corrections per session must be trending DOWN over the last 5 sessions
- self_heal must have caught ≥1 thing the founder didn't have to surface manually

**Red flags (STRUCTURAL gap, not UX friction):**
- Founder manually diagnosing gaps self_heal was supposed to catch
- /learn rate = 0% across multiple sessions
- route_task returning skills that were never invoked
- org_score STALLED despite active development

**Output format:** Same as other personas — ACTUAL vs. PROMISED, GAP, verdict (COMPOUNDING / PARTIAL / FAILING), top 3 friction points, one-line fix each.
