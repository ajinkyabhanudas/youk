# youk Self-Heal Proposals

*Pending founder review. Hard rule: no-auto-apply-proposals.*
*Approved proposals are removed from this file and committed to the relevant config/skill file.*

---

<!-- Proposals are appended here by youk-core.self_heal() and session_end() -->

## PENDING-20260702044435 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** session_start: warn when commits exist but no resume_point
**Reason:** Persona A + D: tab-close is the default session end. When next session opens and there are commits since last-seen but no resume_point, the dev has no idea their context was lost. Surfacing this in session_plan converts a silent failure into an actionable signal.
**Before:** 
**After:** Add to _generate_session_plan(): after the staleness/resume block, check if new_commits > 0 and not resume_point (or resume_point is the default cold-start text). If so, append: f"⚠ Last session ended without /done — {new_commits} commit(s) exist but no context was saved. Run /done at end of this se
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
Add to _generate_session_plan(): after the staleness/resume block, check if new_commits > 0 and not resume_point (or resume_point is the default cold-start text). If so, append: f"⚠ Last session ended without /done — {new_commits} commit(s) exist but no context was saved. Run /done at end of this session to start compounding."
```

## PENDING-20260702044441 — 2026-07-02
**Target:** servers/core/src/health.py
**Change:** self_heal: flag empty loop when PENDING.md and audit SkillGaps both zero
**Reason:** Persona B: self_heal returns org_score findings but never flags that the self-evolution loop itself is starved. When PENDING.md has 0 proposals AND audit has 0 SkillGap entries for 30 days, that IS a finding — the compounding loop isn't running. Should surface as HIGH finding so the developer knows to investigate.
**Before:** 
**After:** Add to _generate_findings(): read PENDING.md and count proposals. Read audit for SkillGap: lines. If both are 0 and total sessions >= 3, append: "Self-evolution loop is starved: 0 proposals in PENDING.md, 0 SkillGap entries in audit across {total} sessions. Run /done with skill_gaps to start feeding
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_findings
**Content:**
```
Add to _generate_findings(): read PENDING.md and count proposals. Read audit for SkillGap: lines. If both are 0 and total sessions >= 3, append: "Self-evolution loop is starved: 0 proposals in PENDING.md, 0 SkillGap entries in audit across {total} sessions. Run /done with skill_gaps to start feeding the loop, or run simulate-experience to seed proposals manually."
```

## PENDING-20260702044448 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** session_start: plain-English /done explanation on first session
**Reason:** Persona A: cold-start session plan says "Use /build to start work; /done at the end saves context for next time" — but a junior dev who asks "what is /done?" gets the CLAUDE.md description with code-review/verify/humanize/session_end jargon. First session should define it in one plain sentence.
**Before:** 
**After:** In the cold-start branch of _generate_session_plan(), change the plan item to: f"First session on {slug} — detected {signals_str}. /build starts work. /done saves context so next session picks up where you left off (no /done = session forgotten). Type /done when you're finished."
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
In the cold-start branch of _generate_session_plan(), change the plan item to: f"First session on {slug} — detected {signals_str}. /build starts work. /done saves context so next session picks up where you left off (no /done = session forgotten). Type /done when you're finished."
```

## PENDING-20260702044456 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** session_start: surface API key missing as session_plan warning
**Reason:** Persona A + B: nfr_check and route_to_skill both fail when ANTHROPIC_API_KEY is absent from Docker. The error is returned inline in the tool response but not surfaced proactively. Checking for the key at session_start and adding a plan item means developers see the warning before hitting the error mid-task.
**Before:** 
**After:** Add near end of start_session(), before building SessionState: check Path("/claude/.anthropic/api_key").exists() or os.environ.get("ANTHROPIC_API_KEY"). If neither: add to session_plan: "⚠ ANTHROPIC_API_KEY not found in Docker — nfr_check and skill execution will fail. Run: export ANTHROPIC_API_KEY=
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** start_session
**Content:**
```
Add near end of start_session(), before building SessionState: check Path("/claude/.anthropic/api_key").exists() or os.environ.get("ANTHROPIC_API_KEY"). If neither: add to session_plan: "⚠ ANTHROPIC_API_KEY not found in Docker — nfr_check and skill execution will fail. Run: export ANTHROPIC_API_KEY=sk-ant-... && make install"
```

## PENDING-20260702044508 — 2026-07-02
**Target:** simulate-experience
**Change:** Team knowledge gap: document shared-knowledge-store limitation in README
**Reason:** Persona C: A new dev joining an existing youk project gets zero benefit from prior sessions — knowledge is per-user (~/.claude/youk/), not per-project. This is structural and expected, but not documented. Developers joining a team should know that youk starts fresh for them and what the path to shared knowledge looks like (future: git-committed knowledge/projects/ per-repo).
**Before:** 
**After:** ## Team Collaboration Gap

youk knowledge is per-user (`~/.claude/youk/knowledge/`). A developer joining a project with existing youk history on another team member's machine starts from zero — no contracts, no decisions, no resume points transfer automatically.

**Current state:** Each developer ma
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT
**TargetSection:** Team Collaboration Gap
**Content:**
```
## Team Collaboration Gap

youk knowledge is per-user (`~/.claude/youk/knowledge/`). A developer joining a project with existing youk history on another team member's machine starts from zero — no contracts, no decisions, no resume points transfer automatically.

**Current state:** Each developer maintains an independent youk instance. Projects accumulate knowledge independently per user.

**Path to shared knowledge (not yet built):** Committing `knowledge/projects/{slug}/` to the project repo would let teammates share context. This requires: (1) gitignore exceptions for knowledge/projects/, (2) conflict resolution for contracts.md when two devs add different contracts, (3) install.sh changes to symlink knowledge/ into the project repo rather than ~/.claude/youk/.

**Surface this explicitly** in Persona C output so product decisions about team knowledge sharing are made with the full picture.
```

## PENDING-20260702061710 — 2026-07-02
**Target:** CLAUDE.md
**Change:** Contract save: confirm to user immediately after save_contract
**Reason:** Persona A: junior dev says "always use TypeScript", save_contract fires silently — they have no idea if the agreement was captured or dropped. Without confirmation, contract capture is invisible and unverifiable.
**Before:** 
**After:** After calling save_contract(), if result.saved is true, append one sentence inline: "Saved — 'always use TypeScript' will load at the start of every future session." If result.saved is false (already exists), say: "Already in contracts — this agreement is already saved." This must appear in the resp
**Status:** APPLIED — 2026-07-02
**ChangeType:** CLAUDE_MD_EDIT
**TargetSection:** Contract phrase triggers
**Content:**
```
After calling save_contract(), if result.saved is true, append one sentence inline: "Saved — 'always use TypeScript' will load at the start of every future session." If result.saved is false (already exists), say: "Already in contracts — this agreement is already saved." This must appear in the response where the contract was verbalized, not as a separate turn.
```

## PENDING-20260702061714 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** close_cluster_missed: plain English, not jargon
**Reason:** Persona A: "Last session ended without context-sync + learn" is MCP-layer jargon a junior dev skips. They miss the actionable signal that their prior work wasn't persisted.
**Before:** 
**After:** Replace the close_cluster_missed plan item text from "Last session ended without context-sync + learn — call session_end with explicit_contracts before new work piles up" to "Last session wasn't saved — run /done at the end of this session so your work compounds into the next one."
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
Replace the close_cluster_missed plan item text from "Last session ended without context-sync + learn — call session_end with explicit_contracts before new work piles up" to "Last session wasn't saved — run /done at the end of this session so your work compounds into the next one."
```

## PENDING-20260702061719 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Stale contract warning when returning after 30+ days
**Reason:** Persona D: contracts from 8 weeks ago load unconditionally — team may have switched patterns entirely. Returning dev starts session with actively wrong behavioral constraints, no warning.
**Before:** 
**After:** In _generate_session_plan(), after the staleness block where days_since_last >= 7 is detected, check if contracts exist and days_since_last >= 30. If so, prepend to session_plan: f"Returning after {days_since_last} days — your {len(contracts)} contracts were written before you left. Verify they're s
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
In _generate_session_plan(), after the staleness block where days_since_last >= 7 is detected, check if contracts exist and days_since_last >= 30. If so, prepend to session_plan: f"Returning after {days_since_last} days — your {len(contracts)} contracts were written before you left. Verify they're still valid before relying on them (run: cat ~/.claude/youk/knowledge/projects/{slug}/contracts.md)."
```

## PENDING-20260702061723 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Include last 3 commit subjects in staleness plan item
**Reason:** Persona D: "Returning after 56 days — 63 commits" is surfaced but not actionable. Dev still has to run git log manually to understand what changed while away.
**Before:** 
**After:** In _generate_session_plan(), when days_since_last >= 7, call _read_git_log(project_dir, n=3) and append the commit subjects to the staleness plan item. Format: "Returning after {N} days — {commits} commit(s) since last session. Recent: {commit1_subject} / {commit2_subject} / {commit3_subject}"
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
In _generate_session_plan(), when days_since_last >= 7, call _read_git_log(project_dir, n=3) and append the commit subjects to the staleness plan item. Format: "Returning after {N} days — {commits} commit(s) since last session. Recent: {commit1_subject} / {commit2_subject} / {commit3_subject}"
```

## PENDING-20260702061727 — 2026-07-02
**Target:** servers/core/src/compaction.py
**Change:** Detect contradictory contracts on save_contract call
**Reason:** Persona D: returning dev saves "from now on use hook-based components" but old contract "always use class components" is still in contracts.md. youk loads both silently, giving Claude contradictory instructions.
**Before:** 
**After:** In write_contracts(), after deduplication, check each new contract against existing ones for keyword overlap (split both into words, check intersection excluding stop words like 'always', 'never', 'use', 'the'). If overlap found, include a 'conflicts' list in the return value: {"added": 1, "conflict
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** write_contracts
**Content:**
```
In write_contracts(), after deduplication, check each new contract against existing ones for keyword overlap (split both into words, check intersection excluding stop words like 'always', 'never', 'use', 'the'). If overlap found, include a 'conflicts' list in the return value: {"added": 1, "conflicts": ["existing contract that may contradict: always use class components"]}. Caller (save_contract tool in server.py) surfaces conflicts in the tool response so Claude can flag them.
```

## PENDING-20260702061732 — 2026-07-02
**Target:** scripts/install.sh
**Change:** install.sh: explain value before prompting for API key
**Reason:** Persona C: joining dev hits "Enter your ANTHROPIC_API_KEY" prompt before understanding what youk uses it for. No context = likely to skip it, silently losing nfr_check and skill execution.
**Before:** 
**After:** Before the read -rs ANTHROPIC_API_KEY prompt, add: echo "  youk uses this for quality checks (nfr_check) and skill execution." / echo "  Without it, basic session tracking still works — you can add it later by re-running this script." This prints above the prompt line so the dev understands the choi
**Status:** APPLIED — 2026-07-02
**ChangeType:** CONFIG_EDIT
**TargetSection:** API key prompt
**Content:**
```
Before the read -rs ANTHROPIC_API_KEY prompt, add: echo "  youk uses this for quality checks (nfr_check) and skill execution." / echo "  Without it, basic session tracking still works — you can add it later by re-running this script." This prints above the prompt line so the dev understands the choice they're making.
```

## PENDING-PROMO-SESSION-20260702063509 — 2026-07-02
**Target:** skills/session/SKILL.md
**Change:** Promote recurring gap pattern: session (3 occurrences across 0 project(s))
**Reason:** SkillGap 'session' appeared 3 times in audit logs. Sample gaps: _detect_project_type returned unknown for the youk repo itself — Docker-based Python projects not detected without requirements.txt at expected paths; no unit tests existed — bugs in _count_pending_proposals and _detect_project_type were invisible for multiple sessions; _count_pending_proposals included APPLIED entries — pending count was wrong on every session_start for sessions with prior applied proposals. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** 
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-PROMO-COMPACTION-20260702063509 — 2026-07-02
**Target:** skills/compaction/SKILL.md
**Change:** Promote recurring gap pattern: compaction (3 occurrences across 0 project(s))
**Reason:** SkillGap 'compaction' appeared 3 times in audit logs. Sample gaps: contracts verbalized mid-session existed only in conversation context until session_end — auto-compaction erased them silently, session_end had 0% fire rate; build_brief mkdir was outside try/except — checkpoint write failure could propagate as an exception instead of degrading silently; compact_context verbatim-paste framing implied it protected contracts from auto-compaction — it only improves odds via recency, actual durability required writing to file. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** 
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-20260702100230 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Fix project_type detection — scan for Makefile and Python files
**Reason:** Persona B (senior) and D (returning): project_type returns "unknown" for every session in a Python/Docker project with Makefile, requirements.txt, and pytest — make_targets and ci_providers are also empty, eroding trust in youk's routing intelligence.
**Before:** 
**After:** In _scan_project_tooling() and project_type detection, extend the Makefile search to check both project_dir and project_dir/.. (one level up), and scan for Python markers (requirements.txt, pyproject.toml, setup.py, *.py files in src/) in addition to package.json. When Dockerfile is present with FRO
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _scan_project_tooling
**Content:**
```
In _scan_project_tooling() and project_type detection, extend the Makefile search to check both project_dir and project_dir/.. (one level up), and scan for Python markers (requirements.txt, pyproject.toml, setup.py, *.py files in src/) in addition to package.json. When Dockerfile is present with FROM python:, set project_type to "python". When Makefile found, parse it for targets by running: targets = [line.split(':')[0] for line in makefile.splitlines() if ':' in line and not line.startswith('\t') and not line.startswith('#')]
```

## PENDING-20260702100243 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Plain-English session plan for sessions 1-3 (junior onboarding)
**Reason:** Persona A (junior): Session plan shows "context-sync + learn", "explicit_contracts", "self-heal proposals" — none are English to a new user, causing them to skip the card entirely. The plan must speak to where they are.
**Before:** 
**After:** In _generate_session_plan(), when session_counter <= 3, replace internal jargon items with plain-English equivalents:
- "session_end with explicit_contracts" → "Type /done when you're finished so I remember this session next time"
- "Review N pending self-heal proposal(s)" → omit entirely for sessio
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan
**Content:**
```
In _generate_session_plan(), when session_counter <= 3, replace internal jargon items with plain-English equivalents:
- "session_end with explicit_contracts" → "Type /done when you're finished so I remember this session next time"
- "Review N pending self-heal proposal(s)" → omit entirely for session_counter <= 3
- "close_cluster_missed" → "Last session wasn't saved. Type /done before closing so I remember what you were working on."
- "contract" references → "saved rule" or "agreement"
Add as first item when session_counter == 1: "Welcome — I'm youk. I track your work session to session. Type /done when you finish to save your progress."
```

## PENDING-20260702100251 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Stale resume_point staleness indicator when days >= 14 and commits > 10
**Reason:** Persona D (returning): After 8 weeks away with 60+ new commits, resume_point shows the old task with full confidence and no staleness marker — the dev picks up wrong context silently.
**Before:** 
**After:** In start_session(), when computing session_plan and days_since_last >= 14 and new_commits > 10, prepend to the resume_point string before adding to session_plan:
f"[{days_since_last}d stale — {new_commits} commits since — verify before resuming] {resume_point}"
This makes staleness explicit in the p
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** start_session staleness block
**Content:**
```
In start_session(), when computing session_plan and days_since_last >= 14 and new_commits > 10, prepend to the resume_point string before adding to session_plan:
f"[{days_since_last}d stale — {new_commits} commits since — verify before resuming] {resume_point}"
This makes staleness explicit in the plan item itself rather than requiring the dev to notice a separate staleness warning.
```

## PENDING-20260702100258 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Show /done → org_score feedback loop in session plan when close missed
**Reason:** Persona B (senior): org_score is capped at 5.8/10 due to 0% close rate, but the developer has no visible feedback connecting /done behavior to their score — the improvement loop is invisible.
**Before:** 
**After:** In _generate_session_plan(), when close_cluster_missed is True, change the plan item from the generic "Last session wasn't saved..." to include the score feedback:
"Last session wasn't saved (impacts org score — currently {score}/10). Type /done before closing to raise it."
Where score comes from th
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** _generate_session_plan close_cluster_missed
**Content:**
```
In _generate_session_plan(), when close_cluster_missed is True, change the plan item from the generic "Last session wasn't saved..." to include the score feedback:
"Last session wasn't saved (impacts org score — currently {score}/10). Type /done before closing to raise it."
Where score comes from the dashboard_summary or improvement-metrics.json. If score unavailable, omit the score reference but keep the /done CTA.
```

## PENDING-20260702100306 — 2026-07-02
**Target:** config/routes.yaml
**Change:** Wire nfr_check into M+ plan_hook in routes.yaml
**Reason:** Persona B (senior): nfr_check exists but never appears in any of 28 audit sessions — it's not wired into the routing layer for M+ tasks, so quality gates never fire for large changes.
**Before:** 
**After:** In the M and L task size plan_hook sections, add nfr_check as a required step. The plan_hook for M+ should include:
"1. nfr_check (run before implementation to surface non-functional requirements)
2. [existing plan steps]
3. code-review (run after implementation)"
If plan_hook is a string field, app
**Status:** APPLIED — 2026-07-02
**ChangeType:** CONFIG_EDIT
**TargetSection:** M+ plan_hook
**Content:**
```
In the M and L task size plan_hook sections, add nfr_check as a required step. The plan_hook for M+ should include:
"1. nfr_check (run before implementation to surface non-functional requirements)
2. [existing plan steps]
3. code-review (run after implementation)"
If plan_hook is a string field, append: " → start with nfr_check to surface non-functional requirements before implementation."
```

## PENDING-20260702100313 — 2026-07-02
**Target:** scripts/install.sh
**Change:** Add per-developer knowledge disclaimer to install.sh
**Reason:** Persona C (joining dev): install.sh gives no indication that youk knowledge is per-machine — a developer joining a team project expects to inherit their teammate's context and is silently disappointed.
**Before:** 
**After:** After the success message at the end of install.sh, add:
echo ""
echo "  Note: youk stores knowledge on this machine only (~/.claude/youk/)."
echo "  Teammates using youk on the same project have separate histories."
echo "  To share context, copy ~/.claude/youk/knowledge/projects/<slug>/ to their m
**Status:** APPLIED — 2026-07-02
**ChangeType:** CONFIG_EDIT
**TargetSection:** success block
**Content:**
```
After the success message at the end of install.sh, add:
echo ""
echo "  Note: youk stores knowledge on this machine only (~/.claude/youk/)."
echo "  Teammates using youk on the same project have separate histories."
echo "  To share context, copy ~/.claude/youk/knowledge/projects/<slug>/ to their machine."
```

## PENDING-20260702100322 — 2026-07-02
**Target:** servers/core/src/session.py
**Change:** Add actionable CTA to stale contract warning (returning dev)
**Reason:** Persona D (returning): The 30-day stale contract warning fires correctly but gives a cat command to run manually — the returning dev sees it, nods, and ignores it. Needs an in-session CTA.
**Before:** 
**After:** In start_session(), in the staleness block where days_since_last >= 30 and contracts exist, replace the current session_plan.insert(0, ...) content with:
f"Returning after {days_since_last} days — {len(contracts)} saved rule(s) may be stale. Say 'show my contracts' to review them before we start."
(
**Status:** APPLIED — 2026-07-02
**ChangeType:** CODE_EDIT
**TargetSection:** start_session staleness block
**Content:**
```
In start_session(), in the staleness block where days_since_last >= 30 and contracts exist, replace the current session_plan.insert(0, ...) content with:
f"Returning after {days_since_last} days — {len(contracts)} saved rule(s) may be stale. Say 'show my contracts' to review them before we start."
(Remove the cat command reference — it's not in-session actionable and reads as a terminal instruction.)
```

## PENDING-PROMO-SESSION-20260702101246 — 2026-07-02
**Target:** skills/session/SKILL.md
**Change:** Promote recurring gap pattern: session (3 occurrences across 0 project(s))
**Reason:** SkillGap 'session' appeared 3 times in audit logs. Sample gaps: _detect_project_type returned unknown for the youk repo itself — Docker-based Python projects not detected without requirements.txt at expected paths; no unit tests existed — bugs in _count_pending_proposals and _detect_project_type were invisible for multiple sessions; _count_pending_proposals included APPLIED entries — pending count was wrong on every session_start for sessions with prior applied proposals. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** 
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-PROMO-COMPACTION-20260702101246 — 2026-07-02
**Target:** skills/compaction/SKILL.md
**Change:** Promote recurring gap pattern: compaction (3 occurrences across 0 project(s))
**Reason:** SkillGap 'compaction' appeared 3 times in audit logs. Sample gaps: contracts verbalized mid-session existed only in conversation context until session_end — auto-compaction erased them silently, session_end had 0% fire rate; build_brief mkdir was outside try/except — checkpoint write failure could propagate as an exception instead of degrading silently; compact_context verbatim-paste framing implied it protected contracts from auto-compaction — it only improves odds via recency, actual durability required writing to file. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** 
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-PROMO-SESSION-20260702110028 — 2026-07-02
**Target:** skills/session/SKILL.md
**Change:** Promote recurring gap pattern: session (3 occurrences across 0 project(s))
**Reason:** SkillGap 'session' appeared 3 times in audit logs. Sample gaps: _detect_project_type returned unknown for the youk repo itself — Docker-based Python projects not detected without requirements.txt at expected paths; no unit tests existed — bugs in _count_pending_proposals and _detect_project_type were invisible for multiple sessions; _count_pending_proposals included APPLIED entries — pending count was wrong on every session_start for sessions with prior applied proposals. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** Created skills/session/SKILL.md with 3 gap patterns: project type detection, pending count including APPLIED entries, and missing unit tests.
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-PROMO-COMPACTION-20260702110028 — 2026-07-02
**Target:** skills/compaction/SKILL.md
**Change:** Promote recurring gap pattern: compaction (3 occurrences across 0 project(s))
**Reason:** SkillGap 'compaction' appeared 3 times in audit logs. Sample gaps: contracts verbalized mid-session existed only in conversation context until session_end — auto-compaction erased them silently, session_end had 0% fire rate; build_brief mkdir was outside try/except — checkpoint write failure could propagate as an exception instead of degrading silently; compact_context verbatim-paste framing implied it protected contracts from auto-compaction — it only improves odds via recency, actual durability required writing to file. Review and expand the skill or add to cross-project.md.
**Before:** 
**After:** Created skills/compaction/SKILL.md with 3 gap patterns: mid-session contracts not written to file, mkdir outside try/except in build_brief, and verbatim-paste framing being probabilistic not deterministic.
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT

## PENDING-20260702115501-xp2 — 2026-07-02
**Target:** /youk/knowledge/cross-project.md
**Change:** Cross-project: make sure we have tests built in for all of these — oversigh
**Reason:** Extracted from youk session on 2026-07-02. Generalizable pattern — not project-specific.
**Before:** (append to cross-project.md)
**After:** 
## make sure we have tests built in for all of these — oversight of any of this sort needs to be avoided at all circumstances
Source project: youk

**Status:** APPLIED — 2026-07-02
**ChangeType:** FILE_CREATE
**Content:**
```

## make sure we have tests built in for all of these — oversight of any of this sort needs to be avoided at all circumstances
Source project: youk
Extracted: 2026-07-02

```

## PENDING-20260702170334 — 2026-07-02
**Target:** ~/.claude/CLAUDE.md
**Change:** Wire /learn into /done — close the learning loop
**Reason:** Simulation confirmed /learn has NEVER been invoked across 33 sessions. It is a skill that exists (skills/learn/SKILL.md) but was never added to the /done ceremony sequence in CLAUDE.md. The learning loop literally cannot close without this wire. Every session that ends without /learn is a session that compounds context but not developer ability — which is the wrong north star. Acid test simulation: youk developing youk showed /learn as "missed catch #1", with responsible mechanism listed as "CLAUDE.md behavioral trigger + dev-loop skill". Fix: add /learn to the /done sequence immediately after humanize. CLAUDE.md line ~46 currently reads "code-review + verify + humanize in sequence" — must become "code-review + verify + humanize + learn in sequence".
**Before:** 
**After:** Change /done line to: /done → code-review + verify + humanize + learn in sequence, then: (1) scan conversation for any contracts not yet saved (save_contract fires immediately mid-session, this is a safety-net sweep for any missed), collect as explicit_contracts=[...], (2) session_end("done", commit
**Status:** APPLIED — 2026-07-02
**ChangeType:** CONFIG_EDIT
**TargetSection:** Workflow commands — /done
**Content:**
```
Change /done line to: /done → code-review + verify + humanize + learn in sequence, then: (1) scan conversation for any contracts not yet saved (save_contract fires immediately mid-session, this is a safety-net sweep for any missed), collect as explicit_contracts=[...], (2) session_end("done", commits_made=<bool>, explicit_contracts=[...], close_cluster=True)

Also add to the M+ task rules: "M+ task completing without /learn at /done = incomplete loop".
```

## PENDING-20260702170345 — 2026-07-02
**Target:** session
**Change:** Add M+ capability skill enforcement gate at session_end
**Reason:** Ceremony was advisory. Gate wires the warning so gap is visible.
**Status:** APPLIED — 2026-07-02 (session_end returns skill_gate_warning when close_cluster=True + no capability skill)
**ChangeType:** SKILL_EDIT
**TargetSection:** session_end — skill gate

## PENDING-20260702170401 — 2026-07-02
**Target:** simulate-experience
**Change:** Add Persona E (youk developing youk) to simulate-experience SKILL.md
**Reason:** Acid test persona missing from simulate-experience.
**Status:** APPLIED — 2026-07-02 (Persona E present in SKILL.md at line 255)

**Profile:** Simulates the youk founder using youk to build youk itself. Session ~30, active development session on the youk codebase.

**What to test:**
- Does session_start produce a brief that eliminates re-establishment cost, or does the develo
**Status:** PENDING
**ChangeType:** SKILL_EDIT
**TargetSection:** Personas
**Content:**
```
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
```

## PENDING-20260702170416 — 2026-07-02
**Target:** servers/core/src/health.py
**Change:** Per-project org_score tracking in improvement-metrics.json
**Reason:** Simulation finding (Priya, Month 3): when she runs /health, she sees youk's org_score (6.1/10), not canopy's.
**Before:** 
**After:** Per-project score tracked in improvement-metrics.json["projects"][slug]. Session_start reads it and surfaces "youk: 6.5/10" in dashboard summary.
**Status:** APPLIED — 2026-07-02
**ChangeType:** CONFIG_EDIT
**TargetSection:** _score_org — per-project tracking

## PENDING-20260702170426 — 2026-07-02
**Target:** session
**Change:** Proactive contract capture: surface unsaved contracts at session_end
**Reason:** session_end() already returns contract_phrases_detected and add_to_contracts_prompt. CLAUDE.md /done workflow already has the safety-net sweep. Machine-readable signal is in place.
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT
**TargetSection:** session_end — contract sweep

## PENDING-20260702170433 — 2026-07-02
**Target:** session
**Change:** Proactive API key validation at session_start — surface as FIRST item
**Reason:** Already wired by PENDING-20260702044456. Updated session_plan.insert(0,...) so key warning is first (not append).
**Status:** APPLIED — 2026-07-02
**ChangeType:** SKILL_EDIT
**TargetSection:** session_start — API key health check

## PENDING-20260702170440 — 2026-07-02
**Target:** health
**Change:** org_score ceiling at 6.5 until 3+ consecutive /done sessions proven
**Reason:** SUPERSEDED by session 35 formula rebalance — discipline gate now based on consecutive capability-skill skips (not /done skips). /done is a 0.5-weight bonus; capability skill invocation is the primary signal. Gate: 3+ consecutive sessions with zero capability skills → cap 6.5.
**Status:** SUPERSEDED — 2026-07-02 (replaced by capability-skill-based gate, commit 093c93a)
**ChangeType:** SKILL_EDIT
**TargetSection:** _score_org — discipline gate

## PENDING-20260702170500 — 2026-07-02
**Target:** cron/youk-research-weekly
**Change:** youk-research scheduled cron — weekly external pattern capture
**Reason:** Acid test finding: youk-research skill exists (skills/youk-research/) and is described in FR-6 and the v0.2.0 roadmap, but has NEVER run across 33 sessions. Zero external patterns have been surfaced. Zero proposals have come from external sources. The skill is designed to scan 4+ external sources weekly and generate add_proposal() calls — but no trigger exists. Without a cron, it only runs if the founder manually invokes it, which hasn't happened. Fix: add a scheduled CronCreate() trigger for youk-research to run weekly (e.g., Sundays). This is a STRUCTURAL gap — it cannot be fixed by SKILL_EDIT alone; requires a CronCreate call to wire up the trigger.
**Before:** 
**After:** Schedule youk-research skill to run weekly. CronCreate trigger: "0 9 * * 0" (Sundays 9am). Invocation: route_to_skill("youk-research", "weekly external pattern scan"). This is the v0.2.0 roadmap item "weekly scheduled cron" from PRD. Implementation requires CronCreate() call with the schedule and a 
**Status:** APPLIED — 2026-07-02 (CronCreate job 37adc6b6, cron "3 9 * * 0", prompt "/research")
**ChangeType:** CONFIG_EDIT
**Content:**
```
Schedule youk-research skill to run weekly. CronCreate trigger: "0 9 * * 0" (Sundays 9am). Invocation: route_to_skill("youk-research", "weekly external pattern scan"). This is the v0.2.0 roadmap item "weekly scheduled cron" from PRD. Implementation requires CronCreate() call with the schedule and a minimal prompt that fires route_to_skill. Token budget: ≤15k (FR-6 constraint). Run off the hot path — never triggered from session_start or route_task.
```
**Note:** CronCreate durable=true did not persist to disk in this environment — cron is session-scoped. Re-create at session start if needed: CronCreate("3 9 * * 0", "/research", recurring=true, durable=true).

## PENDING-20260702170510 — 2026-07-02
**Target:** servers/core/src/doc_graph.py
**Change:** doc_graph.py module + check_doc_graph() MCP tool for concept coherence
**Reason:** Session 33 simulation found 5 files with divergent north star definitions (PRD.md, README.md, PHILOSOPHY.md, CLAUDE.md, well-architected.md). No mechanism detected this — it required manual founder audit. The approved plan (plans/what-was-its-original-idempotent-rainbow.md) specifies: new doc_graph.py module with load_concept_graph(), check_concept_staleness(), format_staleness_warnings(); new check_doc_graph() MCP tool; wire into session_start._check_doc_freshness(); extend doc-map.yaml with concepts: section. This is deferred to v0.3.0 per the updated roadmap — implement after /learn wire and M+ gate are in place and proven.
**Before:** 
**After:** See approved plan at knowledge/projects/youk/plans/what-was-its-original-idempotent-rainbow.md for full implementation spec. Key functions: load_concept_graph(youk_root), check_concept_staleness(concepts, youk_root, claude_root), format_staleness_warnings(stale, cap=2). Uses git log commit timestamps (cross-clone stable), falls back to mtime. Concepts declared in docs/doc-map.yaml under 'concepts:' block. Also requires: server.py addition (check_doc_graph tool), session.py wire, doc-map.yaml concepts section, tests/test_doc_graph.py (6 tests).
**Status:** APPLIED — 2026-07-02 (commit 67d82de)
**ChangeType:** FILE_CREATE
**Content:**
```
See approved plan at knowledge/projects/youk/plans/what-was-its-original-idempotent-rainbow.md for full implementation spec. Key functions: load_concept_graph(youk_root), check_concept_staleness(concepts, youk_root, claude_root), format_staleness_warnings(stale, cap=2). Uses git log commit timestamps (cross-clone stable), falls back to mtime. Concepts declared in docs/doc-map.yaml under 'concepts:' block. Also requires: server.py addition (check_doc_graph tool), session.py wire, doc-map.yaml concepts section, tests/test_doc_graph.py (6 tests).
```

## PENDING-20260702170520 — 2026-07-02
**Target:** session
**Change:** Cross-project contract transfer: session_start surfaces other-project contracts
**Reason:** Simulation finding (Priya, Month 3): youk contracts (behavioral agreements, test-first discipline) don't surface when she opens canopy. Canopy has zero saved contracts after 1 session, but youk has 8–9 entries. The patterns she established on youk (commit format, test cadence, NFR discipline) are directly applicable to canopy but never transferred. Fix: session_start should scan all ~/.claude/*/contracts.md (not just the current project), identify contracts from other projects that are not already in the current project's contracts.md, and surface 1–2 of them as session_plan items: "youk uses: 'always write tests before committing' — adopt for canopy? (save this: [contract])" This is transfer, not duplication — the developer chooses to adopt each one explicitly.
**Before:** 
**After:** In _generate_session_plan(), after loading current project contracts, scan other project contract files at ~/.claude/*/contracts.md (or ~/.claude/youk/knowledge/projects/*/contracts.md). For contracts not yet in current project: surface max 1 per session as "Transfer from {project}: '{contract}' — s
**Status:** APPLIED — 2026-07-02 (commit a179e1c)
**ChangeType:** SKILL_EDIT
**TargetSection:** session_start — cross-project contract discovery
**Content:**
```
In _generate_session_plan(), after loading current project contracts, scan other project contract files at ~/.claude/*/contracts.md (or ~/.claude/youk/knowledge/projects/*/contracts.md). For contracts not yet in current project: surface max 1 per session as "Transfer from {project}: '{contract}' — say 'save this' to adopt." Cap at 1 to avoid noise. Only surface if current project has <3 contracts (prevents polluting established projects). Implementation: lightweight file scan, no API call, O(n) file reads.
```
