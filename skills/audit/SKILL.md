---
name: audit
description: >
  Project-aware skill coverage audit. Detects what kind of project this is, compares
  the active skill ecosystem against what that project type needs, and generates the
  missing skills on the spot. Distinct from /health (org_score and session metrics)
  and /improve (improves existing skills). This one asks: does youk have the right
  capabilities for THIS project? Triggers on: "/audit", "audit the project",
  "audit yourself", "what skills are we missing", "what could youk add for this
  project", "what skills should exist for this", "self-audit".
---

# audit — Project-Aware Skill Coverage Audit

Confirms what type of project you're working on, compares the skill ecosystem against
what that project type needs, and generates missing skills without leaving the session.

---

## Execution sequence

**Step 1 — Get coverage data**

Call `youk-core.self_heal()`. Extract:
- `project_type` and `project_type_description` (set by session_start at each session open)
- `coverage_gaps` — list of `{name, purpose}` dicts for missing skills
- `org_score` and `findings` — surface these briefly alongside the coverage report

If `project_type` is absent or `project_type_description` is "General software project":
State: "Project type not detected yet — run /start or start a new session to let youk
re-scan the project. If this is a new project type not in the registry, describe what
kind of project this is and I can register a new type."

**Step 2 — Report**

Output this card:

```
Project type confirmed: {project_type_description}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Skill coverage for this project type:
  ✓ {count of present expected skills} skills present
  ✗ {len(coverage_gaps)} missing:
    {for each gap: "- {name}: {purpose}"}

{IF coverage_gaps is empty}
  All expected skills for this project type are present.
  Run /health for org_score and session metrics, or /improve for skill quality improvements.
{END IF}

{IF coverage_gaps non-empty}
  Generate the missing skill(s) now? [yes / skip / describe what {name} should cover]
{END IF}
```

**Step 3 — Generate missing skills (on approval)**

For each skill in `coverage_gaps` (or whichever the user approves):

1. Call `youk-code.generate_skill(name, purpose, context, signal_type)` where:
   - `name` = skill name from the gap
   - `purpose` = purpose from the gap
   - `context` = "Project type: {project_type_description}. Stack: {stack/framework from session context}."
   - `signal_type` = "session_trigger"

2. Review the returned draft. State: "Draft generated for '{name}'. Key sections: [list phases/triggers]. Applying..."

3. Call `youk-core.add_proposal(...)` with the generated skill content as a FILE_CREATE proposal targeting `skills/{name}/SKILL.md`

4. Call `youk-core.apply_proposal(confirmed=True, safe_types=["FILE_CREATE"])`

5. Confirm: "Skill '{name}' created. It will activate from the next session."

**Step 4 — Offer to register a new project type (if user describes one)**

If the user says "this is actually a [type] project", or if `project_type` came back as
"general" and the user wants to register the type:

State: "I can add '{described type}' to the project type registry. What skills should
exist for every project of this type?"

Once the user confirms the skills list:
- The new type + expected skills should be added to `session.py`'s
  `PROJECT_PURPOSE_EXPECTED_SKILLS` dict and `_detect_project_purpose()`'s
  detection logic as a CODE_EDIT proposal queued in PENDING.md for manual review.

---

## Rules

- Do NOT run /health in full — just extract the coverage fields and surface org_score briefly
- Do NOT generate skills without user confirmation at Step 2
- Each missing skill gets its own generate_skill() call — do not batch
- After generating, confirm exactly which file was created and where
- This is not a session-closing command — do not call session_end
