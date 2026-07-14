---
name: docs
description: >
  Doc-sync enforcer. Detects when behavioral gates, commands, or skill behavior change
  and ensures all derived documentation surfaces are updated in the same session.
  Triggers on: any behavioral gate change (tool-level enforcement, plan item content,
  return value semantics), check_doc_graph() returning stale concepts, and /done step 5b
  doc-staleness sweep. Covers README, getting-started.md, CHANGELOG, GitHub wiki, and
  skill files as derived surfaces. Does NOT rewrite docs from scratch — only surfaces
  the delta between what changed and what the docs still say.
---

# docs — Doc-Sync Enforcer

Every behavioral gate change has at least four surfaces that can drift: README,
getting-started, CHANGELOG, and the skill file that governs the behavior. When any
one of them contradicts the code, a developer forms a wrong mental model — and the
wrong model trains behavior silently across sessions before anyone notices.

This skill closes the gap in the same session the change ships.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full sync: IDENTIFY → DIFF → PATCH → VERIFY |
| `quick` | IDENTIFY → DIFF only — surfaces gaps without writing |
| `concept: [name]` | Focus on one stale concept from check_doc_graph() output |
| `sweep` | Run check_doc_graph() and process all stale concepts in sequence |
| `enter: PATCH` | Skip to PATCH (diff already known, just write the updates) |

---

## Context Capture (Always First)

```
TRIGGER:        [behavioral gate change | check_doc_graph stale concept | /done step 5b]
CONCEPT:        [which behavioral concept changed — e.g. session_close_contract]
AUTHORITY:      [the file that holds the new truth — e.g. CLAUDE.md, servers/core/src/session.py]
DERIVED_IN:     [files that should reflect the authority — from doc-map.yaml or manual scan]
WHAT_CHANGED:   [one sentence: the old behavior vs. the new behavior]
```

If triggered by check_doc_graph(), read its `stale_concepts` list — each entry gives
`concept`, `authority`, and `stale_in` directly. No inference needed.

---

## The Four Phases

### Phase 1 — IDENTIFY

1. If triggered by check_doc_graph(): read the returned `stale_concepts` list.
2. If triggered by a code/skill change this session: call `check_doc_graph()` now.
3. For each stale concept, confirm whether files changed this session touch its
   `derived_in` list. A concept whose authority didn't change this session is
   pre-existing drift — flag it as INFO, do not block the session.
4. Triage: separate concepts introduced by this session's changes (BLOCK) from
   pre-existing drift (INFO).

> Compact summary: "N concepts stale. M introduced this session (must fix). K pre-existing (flag only)."

---

### Phase 2 — DIFF

For each BLOCK concept:

1. Read the authority file — extract the current behavior in one sentence.
2. Read each stale derived file — extract what it currently says about this concept.
3. State the delta explicitly:
   ```
   CONCEPT: {name}
   Authority says: {current behavior, verbatim if short}
   Derived file says: {what the stale file claims}
   Gap: {the specific contradiction — one sentence}
   ```

Do not write anything yet. This phase only surfaces gaps.

> Compact summary: "Gaps found in: {file list}. Ready to patch."

---

### Phase 3 — PATCH

For each gap identified in Phase 2:

1. Write the minimal update to the derived file — change only the contradicting claim,
   preserve surrounding structure.
2. For CHANGELOG: add an entry under the current date describing the behavioral change
   in plain English (not "updated docs" — state what the behavior now is).
3. For skill files: update the phase, quality bar, or example that contains the stale claim.
4. For README / getting-started: update the specific sentence or step that contradicts
   the authority — do not rewrite the surrounding section.

Rule: one patch per file per concept. If a file has two stale claims for the same
concept, fix both in one edit — don't produce two diffs for the same file.

> Compact summary: "{N} files patched. Concepts now consistent."

---

### Phase 4 — VERIFY

1. Re-run `check_doc_graph()`.
2. Confirm the concepts patched this session no longer appear in `stale_concepts`.
3. If any remain stale: return to Phase 3 for that concept only.
4. Surface pre-existing drift (INFO items from Phase 1) as a one-line list:
   "Pre-existing drift (not introduced this session): {concept list} — address in a future session."

> Compact summary: "All session-introduced gaps closed. Pre-existing drift flagged."

---

## Quality Bars (Non-Negotiable)

- **Authority-first:** Never update derived files from memory or conversation — always
  read the authority file first. The authority file is the source of truth; everything
  else is downstream.
- **Minimal diffs:** Patch only the contradicting claim. A doc-sync edit that rewrites
  paragraphs is a doc improvement, not a doc-sync — wrong scope for this skill.
- **CHANGELOG entry is mandatory:** Any behavioral gate change must produce a CHANGELOG
  entry describing the new behavior in plain English. "Docs updated" is not an entry.
- **Verify closes the loop:** Phase 4 must run. A patch that isn't verified may have
  missed a derived file — check_doc_graph() is the exit condition, not "I think I got them all."
- **Pre-existing drift is not blocked, but must be surfaced:** Don't silently skip
  stale concepts that predate this session. Name them so they can be addressed.

### Hiring Validation

1. Given `check_doc_graph()` returning `session_close_contract` stale in `getting-started.md`
   and `skills/done/SKILL.md`: does the skill read CLAUDE.md (authority) before touching
   either file? Correct: yes — reads authority first, derives delta, patches minimum.
2. Given a behavioral change where the old behavior is still correct in one derived file:
   does the skill patch it anyway? Correct: only if it contradicts the authority. If it
   already matches, skip it — don't produce noise.
3. Given two stale concepts from check_doc_graph(): does the skill process both? Correct:
   yes — one pass per concept, in sequence, Phase 2→3 for each before moving to verify.
4. Given a pre-existing stale concept (authority unchanged this session): does the skill
   block the session? Correct: no — surfaces as INFO, does not patch, does not block.

---

## Reference Files

| File | When to read |
|------|-------------|
| `docs/doc-map.yaml` | Phase 1 — `derived_in` lists for each concept |
| `docs/getting-started.md` | Phase 2/3 — common derived surface for behavioral contracts |
| `CHANGELOG` | Phase 3 — always add entry for behavioral gate changes |

---

## Example Flows

**Behavioral gate change — force_learn shipped:**
> Trigger: `force_learn` gate added to session.py; check_doc_graph() returns `session_close_contract` stale in getting-started.md and skills/done/SKILL.md.

IDENTIFY (2 stale, both introduced this session, both BLOCK) →
DIFF (getting-started says "youk surfaces nudge at next open"; authority says gate fires automatically; done/SKILL.md says learn is optional) →
PATCH (getting-started: replace nudge sentence with "force_learn gate fires automatically at next session open"; done/SKILL.md: update Step 4 to "learn is required — not optional"; CHANGELOG: "force_learn gate: /learn now fires automatically at session start if prior session skipped it") →
VERIFY (check_doc_graph() — session_close_contract no longer stale)

**Pre-existing drift sweep at /done:**
> Trigger: /done step 5b — check_doc_graph() returns 3 stale concepts: scope_collapse_gate (pre-existing), api_key_required (pre-existing), session_close_contract (introduced this session).

IDENTIFY (triage: 1 BLOCK, 2 INFO) →
DIFF (session_close_contract only) →
PATCH (1 file) →
VERIFY →
Surface: "Pre-existing drift: scope_collapse_gate, api_key_required — address in future session."

**Quick mode — checking without writing:**
> "/docs quick" after a skill change.

IDENTIFY → DIFF only → Output gap list → Stop. No files written.
