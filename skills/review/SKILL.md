---
name: review
description: >
  GitHub PR review skill. Reviews open pull requests: reads the diff, tests the
  logic against the stated intent, surfaces blocking issues and non-blocking notes.
  Distinct from code-review (which reviews local session work) — this reviews a
  GitHub PR that already exists.
---

# review — GitHub PR Review

Reviews a GitHub pull request against its stated intent. Reads the diff, not just
the description. Surfaces what the description claims and what the code actually does.

Distinct from `/code-review`, which reviews local work-in-progress.
This skill reviews a PR that already exists on GitHub.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| `review: #{PR number}` | Review specific PR — `gh pr view {n} --json` + `gh pr diff {n}` |
| `review: {URL}` | Review PR by URL |
| *(no directive)* | Review the current branch's open PR if exactly one exists |
| `review: quick` | Only blocking issues — no style notes |
| `review: summary` | 3-sentence summary of the PR's changes, no review |

---

## Execution Sequence

**Phase 1 — FETCH**

```bash
gh pr view {n} --json title,body,author,baseRefName,headRefName,state,additions,deletions
gh pr diff {n}
```

If no PR number given: `gh pr list --author @me --state open` — take the first result
if exactly one exists, else ask.

Extract from the PR body:
- `## Summary` — what the author says they changed
- `## Test plan` — what the author says they tested

**Phase 2 — READ**

Read the diff. For each file changed:
- What is the stated change (from PR description)?
- What does the diff actually do?
- Do they match?

Flag mismatches immediately — "description says X, code does Y" is always a finding.

**Phase 3 — REVIEW**

Apply four lenses:

**Lens 1 — Correctness**
Does the code do what the PR says it does?
Does it handle the edge cases in the test plan?

**Lens 2 — Completeness**
Are there missing cases the author didn't test?
Is the test plan sufficient for the change size?

**Lens 3 — Scope**
Does this PR include changes unrelated to its stated purpose?
Unrelated changes in a PR = silent bugs waiting to be missed.

**Lens 4 — Risk**
Does this change touch critical paths (auth, payments, data migration)?
Does it have a rollback plan?

**Phase 4 — OUTPUT**

```
PR #{n} — {title}
Author: {author}  |  +{additions} −{deletions}

[SUMMARY]
{2-sentence summary of what actually changed}

[BLOCKING]
{B1}: {specific issue — line number if possible}
{B2}: ...

[NON-BLOCKING]
{N1}: {note}
...

[VERDICT]: APPROVE | NEEDS REVISION | BLOCKING
```

If no blocking issues: APPROVE with inline notes.

---

## Quality Bar

- Every BLOCKING item names the specific file and behavior, not a category.
- "This might cause issues" is not a finding. "Line 47: `user.delete()` runs before
  the transaction commits — a crash here orphans the session" is a finding.
- Non-blocking items are optional suggestions, not required changes.
- APPROVE means the reviewer is confident it's safe to merge — not just "looks okay."
