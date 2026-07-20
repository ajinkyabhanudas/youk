# Skill Registry — y2k-1

**Company:** y2k-1 | **Activation:** say "activate y2k-1" | **Roster size:** 26
*Living document. Updated by /skill-health after each review. Last updated: 2026-07-20.*
*Owner: Ajinkya Dessai. All skills are scoped to the ~/.claude/skills/ directory.*

---

## What This Document Is

The complete map of the skill ecosystem. Every skill that exists, what it does, what
it tends to miss, and how it connects to others. The hiring committee standard for
any new skill: it must do something no existing skill does.

**Machine-readable graph:** `~/.claude/youk/knowledge/skill-graph.yaml` — encodes all
skill dependencies, knowledge reads/writes, trigger conditions, and stack coverage status.
Consumed by `check_doc_graph()` and `generate_stack_overlay()`.

**Stack overlay schema:** `~/.claude/skills/stack-overlay-schema.md` — canonical structure
for all generated `references/stacks/{framework}.md` overlays (6 sections, WAF-grounded,
<600 tokens). New overlays are generated on first encounter, saved for future sessions.

---

## Skill Inventory

| Skill | Role | Invoke When | Health |
|---|---|---|---|
| `/dev-loop` | Senior Engineer | Any implementation task | ACTIVE |
| `/ux-designer` | UX Researcher | Any user-facing design decision | ACTIVE |
| `/code-review` | Quality Reviewer | Any diff before merging | ACTIVE |
| `/security-review` | Security Auditor | Auth, data, new endpoints | ACTIVE |
| `/verify` | QA Tester | After implementation, confirm live behavior | ACTIVE |
| `/nfr-check` | Systems Engineer | Before any non-trivial feature (quick=default, full for L/XL) | ACTIVE |
| `/adr` | Staff Architect | Any significant technical decision | ACTIVE |
| `/stress-test` | Red Team Lead | Before committing to any major design | ACTIVE |
| `/pm-review` | AI Product Manager | Any new feature request or prioritization question | ACTIVE |
| `/write-spec` | Technical PM | After build decision — define WHAT to build precisely | ACTIVE |
| `/orchestrate` | Chief of Staff / COO | New project, feature sprint, or "what's next?" | ACTIVE |
| `/context-sync` | Context Manager | Session start, session end, when context feels stale | ACTIVE |
| `/humanize` | Technical Writer | Commit messages, docs, decision rationale | ACTIVE |
| `/learn` | L&D Coach | Session end (always), explicit concept deep-dives | ACTIVE |
| `/skill-health` | Engineering Manager | Periodic review, post-observed gap; reads audit logs | ACTIVE |
| `/simplify` | Code Quality | After implementation, reduce complexity | ACTIVE |
| `/run` | DevOps | Run/start the project for manual verification | ACTIVE |
| `/review` | GitHub PR Review | GitHub PR review | ACTIVE |
| `/skill-forge` | Skill Architect (proactive) | New stack, or "what skills would an elite need here" — derives + sharpens skills at a rising standard | ACTIVE |
| `/challenge` | Direction Gate | Before any M+ implementation — is this the right problem? | ACTIVE |
| `/adversary-loop` | Independent Adversary | M+ design decisions — context-independent attack until exhaustion | ACTIVE |
| `/done` | Session Close | Session end — code-review + verify + humanize + learn in sequence | ACTIVE |
| `/adversarial-planning` | Adversarial Auditor | Adversarial audit of any planning target: claims → verification → convergence → roadmap | ACTIVE |
| `/self-heal` | Improvement Protocol | /health, /improve, org_score check, recurring gap — makes health work register as capability skill | ACTIVE |
| `/install-experience` | Onboarding Auditor | install.sh changes, pre-release gate, "does install work?" — SCAN → SCRIPT-AUDIT → DOCKER → HANDSHAKE | ACTIVE |
| `/namespace-safety` | Collision Gate | Before any generate_skill or new MCP tool — checks skill names, MCP tool names, config keys for collisions | ACTIVE |
| `/dependency-audit` | Dependency Auditor | New dependency added, "are deps safe?", pre-release — INVENTORY → PINNING → VULNERABILITIES → REMEDIATE | ACTIVE |

---

## Invocation Flows

### New Feature Flow

```
1. /pm-review          — Should we build this? P0/P1/P2? Why NOT build it?
2. /write-spec         — Define WHAT to build precisely (after build decision)
3. /nfr-check          — Quick (4 Qs) for S/M; full for L/XL
4. /adr                — Any architectural decisions to document?
5. /stress-test        — L/XL only: does the design hold up?
6. /dev-loop           — Implement (consumes NFR Decision Block as context)
7. /ux-designer        — If user-facing: design the UI states
8. /code-review        — Quality gate on the implementation
9. /security-review    — If auth/data/new endpoint: security gate
10. /verify            — Confirm live behavior is correct (use Playwright MCP for any UI change; protocol in ~/.claude/skills/verify/playwright-protocol.md)
11. /humanize          — Commit messages and documentation
12. /learn             — Session-end knowledge capture
```

### New Project Flow

```
1. /orchestrate        — Set up rolling 3-step plan, routing to skill teams
2. /pm-review          — Product brief + prioritization
3. /write-spec         — Full PRD for core features
4. /nfr-check full     — Full NFR check for new project
5. /adr                — Document founding architecture decisions
6. /stress-test        — Attack the architecture before building
7. → Feature flow above for each feature
```

### Decision Flow

```
1. /adr                — Document the decision and rejected alternatives
2. /stress-test        — Attack the chosen design
3. /nfr-check connect  — Check if the decision creates new NFR requirements
```

### Session Management Flow

```
Session start:
1. /context-sync start — Load L1 + L2 + L3; report resume point

Session end:
1. /context-sync end   — Flush to L2/L3; prune session context
2. /learn              — Post-session knowledge capture
3. /humanize           — Final commit message
```

### Maintenance / Review Flow

```
Periodic (every 2-3 weeks):
1. /skill-health       — Review skill ecosystem health
2. /code-review        — Review accumulated technical debt
```

---

## What Each Skill Tends to Miss

Honest assessment of known gaps. Updated by /skill-health reviews.

| Skill | Known Gaps |
|---|---|
| `/dev-loop` | NFR decisions (caching especially) made too late; no "should we build this?" gate; no decision documentation; no implicit ADR detection in AUDIT phase |
| `/ux-designer` | Accessibility (WCAG); mobile/responsive; performance budget; **rendering environment now covered by checklist.md Rendering Environment section** |
| `/code-review` | Architectural drift over time; doesn't catch NFR gaps (that's /nfr-check's job) |
| `/security-review` | Not always invoked on internal modules; only catches what it's shown |
| `/verify` | **Now Playwright-enabled** — Protocol: `~/.claude/skills/verify/playwright-protocol.md`. **Test 10 added: dark mode rendering check.** Remaining gap: no automated performance regression. |
| `/nfr-check` | May default to full ceremony when quick block would do; watch for over-triggering. **Category 11 added: Rendering Environment (mandatory for all CSS/UI changes).** |
| `/adr` | Easy to skip on "obvious" decisions that later turn out not to be obvious. **Implicit architectural decisions section added to decision-triggers.md.** |
| `/stress-test` | Agent independence requires explicit instruction; poorly run = agents echoing each other |
| `/pm-review` | Solo developer calibration still evolving; "do nothing" option sometimes skipped |
| `/write-spec` | New — may over-specify for small features; use `quick` mode for S |
| `/orchestrate` | Consistently skipped — no session-start invocation observed. Session planning done informally instead. |
| `/context-sync` | Superseded by session_start/compact_context MCP tools — registry entry kept for historical flow reference. |
| `/humanize` | Requires explicit invocation; not yet auto-triggered; Co-Authored-By misapplied when run manually |
| `/learn` | Running consistently (52% sessions, Jul 2026). Prior gap resolved. |
| `/skill-health` | dev_loop audit registration gap: M+ sessions not logging dev_loop in Skills: line even when implementation runs. |
| `/challenge` | Fire rate 4% (1/23 sessions Jul 2026) despite CLAUDE.md contract. High-autonomy developer pre-empts most design challenges. |
| `/adversary-loop` | New — no gap history yet. Fires for M+ design decisions when /challenge routes to full adversary mode. |
| `/done` | Fires as /done sequence; skills inside it (code-review, verify, humanize, learn) also logged separately, inflating their counts slightly. **New (2026-07-20): does not call self_heal(), so improvement-metrics.json (org_score trend) is not updated by a /done close — only a separate /self_heal or /improve run writes it. A full 8-phase delivery session (Canopy, 2026-07-19) closed correctly with /done and is still invisible in org_score history.** |
| `/self_heal` | Called ~9% of sessions this month (3/~35) despite being the sole writer of improvement-metrics.json. Org_score trend, velocity, and per-project scores go stale whenever a session closes via /done without a separate /self_heal call. |
| `/self-heal` | New — no gap history yet. Critical quality bar: SKILL_EDIT content must be full section text or apply_proposal destroys existing content. Watch for partial-content proposals. |
| `/install-experience` | New — no gap history yet. Fast-path relies on git log to detect unchanged install.sh; if git not available, fast-path silently skips. |
| `/namespace-safety` | New — no gap history yet. Semantic overlap detection is heuristic — may miss overlaps when skill descriptions use different vocabulary for the same concept. |
| `/dependency-audit` | New — no gap history yet. CVE scan is incomplete without pip-audit installed — must flag this explicitly rather than proceeding silently with training-knowledge checks. |

---

## Skill Wiring Diagram

```
  /orchestrate ←─── Founder entry point. Routes all skills per project type.
       │
       ▼
  /pm-review  ─── Should we build this? P0/P1/P2? Why NOT?
       │
       ▼
  /write-spec ─── WHAT exactly are we building? (PRD quality)
       │
       ▼
  /nfr-check  ─── 4 Qs (S/M) or full check (L/XL)
       │
  ┌────┴─────┐
  │          │
/adr    /stress-test  ←── L/XL only
  │
  └────┬─────┘
       ▼
  /dev-loop  ─── Implementation
       │
  ┌────┴────────┬────────────┐
  ▼             ▼            ▼
/ux-designer /code-review /security-review
                  │
                  ▼
              /verify
                  │
  ┌───────────────┼──────────┐
  ▼               ▼          ▼
/humanize      /learn   /context-sync end
(commits)    (knowledge)   (flush + audit log)

Meta (run separately):
  /skill-health  ← reads audit logs, scores org efficiency
  /context-sync start ← beginning of every session
```

---

## New Skill Backlog

Proposed skills that don't yet exist. Evaluated against the hiring bar before creation.

| Proposed Skill | Gap It Addresses | Priority | Status |
|---|---|---|---|
| `/incident-review` | Post-production incident structured retrospective | LOW | Deferred — promote when first project reaches production |
| `/dependency-audit` | Review all dependencies for CVEs, updates, deprecation | LOW | PROMOTED — skill generated 2026-07-20 via stack scan |
| `/cross-project` | Surface patterns from one project applicable to a new project | MEDIUM | LOW-ACTIVE — invoke at project completion or when starting a second project in the same domain |

---

## Change Log

| Date | Change | Reason |
|---|---|---|
| 2026-06-27 | Created registry; added 8 new skills | Initial ecosystem design — AI agentic company session |
| 2026-06-27 | Elevated caching in dev-loop audit checklist (LOW → HIGH) | Caching decision slipped post-implementation because it was rated too low to trigger early |
| 2026-06-27 | Added NFR gate to dev-loop UNDERSTAND phase | Pre-build NFR check prevents post-hoc NFR decisions |
| 2026-06-27 | Added /orchestrate (COO), /write-spec (Technical PM) | Close PM gap vs. Anthropic plugin; orchestrate skill routing |
| 2026-06-27 | Simplified /nfr-check: 4-question default, full only for L/XL | Reduce ceremony, keep what catches 80% of incidents |
| 2026-06-27 | Added audit log to /context-sync FLUSH; extended /skill-health with org efficiency score | CEO-level visibility into org health trends |
| 2026-06-27 | Rewrote /humanize voice profile: hard rules for no em dashes, no rhetorical buildup | Extracted from Ajinkya's actual writing patterns |
| 2026-06-27 | Added Playwright MCP protocol to /verify; wired into New Feature Flow | Live browser testing revealed bugs invisible to unit tests — validation mismatches, tab label drift from stale server |
| 2026-06-27 | /skill-health review — Org score 5.8/10. Added: NFR category 11 (Rendering Environment), ux-designer checklist Rendering Environment section, /verify Test 10 (dark mode rendering check), /adr implicit decisions section, FOUNDER-GUIDE session-close required framing | Rendering environment gap slipped past UX review and reached the user; session-close cluster consistently skipped across multiple sessions |
| 2026-07-03 | Stack Coverage System added to code-review + nfr-check SKILL.md. generate_stack_overlay() tool added. skill-graph.yaml + stack-overlay-schema.md created. | Generative overlay architecture — skills detect stack gap on first encounter, propose generating overlay, save for future sessions. WAF-grounded schema ensures critical questions > checklists. |
| 2026-07-14 | Added /skill-forge (proactive stack→skill convergence loop) + analyze_stack_for_skills() tool + signal/noise framework (humanize). | Closes youk's improvement loop forward: forge anticipates skills from stack analysis at a rising standard until convergence; self_heal stays reactive. Signal/noise framework (SUBTRACT+REVEAL) generalizes REVEAL from learn/challenge/stress-test into one reusable source. |
| 2026-07-17 | Added /challenge, /adversary-loop, /done to inventory. Updated known gaps table. Org score: 7.2/10 (+1.4 vs. prior review). Top gap: dev_loop not registering in audit for M+ sessions. | skill-health review Jul 2026 |
| 2026-07-20 | Added 4 skills from stack scan: /self-heal (closes audit registration gap for health work), /install-experience (first-run install audit), /namespace-safety (collision gate before write), /dependency-audit (Python dep pinning + CVE). Roster: 22 → 26. | Track A stack scan via /improve |

---

## Hiring Committee Standard

Any new skill must pass these gates before being added:

1. **Scope test**: "Does this do something that NO OTHER SKILL on the current roster already does?"
2. **Hiring bar test**: "If this were a team member, would we hire them for this specific role?"
3. **Reference test**: "Does it have at least 2 reference files that make it robust on any task?"
4. **Handoff test**: "Does its output format connect cleanly to the next skill in the chain?"
5. **Self-limiting test**: "Does it know when NOT to invoke itself, and does it say so?"
