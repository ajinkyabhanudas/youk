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
