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
