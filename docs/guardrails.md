# Guard Rails

Guard rails in youk are versioned contracts, not prompt suggestions. They live in `config/guardrails.yaml`, are enforced at the MCP tool level, and change only via a git commit.

---

## How they work

**Hard rules** block at the tool level. When a hard rule is violated, the tool returns `{"blocked": true, "rule_id": "...", "error": "..."}`. Claude cannot override this — the tool refused, not Claude.

**Soft rules** return warnings in the routing decision. They're surfaced once per session and are always skippable. They nudge toward better ceremony, never block.

---

## Hard rules

### `no-auto-apply-proposals`
**Enforced by:** `youk-core.apply_proposal()`

youk can observe patterns, generate health reports, and write proposals to `knowledge/proposals/PENDING.md`. It cannot apply those proposals without your explicit approval.

The `apply_proposal` tool requires `confirmed=True` to proceed. If you call it without that parameter, it returns an error explaining why. This is intentional — not a bug.

**Why it matters:** A system that upgrades itself without oversight isn't an assistant. It's a liability.

### `no-credential-commits`
**Enforced by:** `youk-code.check_commit_quality()`

Files matching these patterns are blocked from commits:
- `*.env`, `.env.*`
- `*secret*`, `*credential*`
- `*api_key*`, `*password*`

If any file in the commit matches, the tool returns `blocked: true` and names the specific file. The commit must not proceed.

**Why it matters:** The blast radius of a credential leak is unbounded. This rule has no exceptions.

### `knowledge-extraction-not-logging`
**Enforced by:** `youk-core.session_end()`

Before writing anything to `knowledge/`, session_end validates that the content is structured — not raw conversation. Content containing `Human:`, `Assistant:`, or other transcript markers is rejected.

**Why it matters:** An ever-growing transcript is noise. Structured knowledge that improves routing is signal.

### `no-destructive-without-confirm`
**Enforced by:** CLAUDE.md proactive pattern + Pre-bash hooks

Operations like `rm -rf`, `DROP TABLE`, `git reset --hard`, and `git push --force` must confirm intent before executing. Confirmation is per-operation, not per-session — approving one `rm -rf` doesn't approve the next one.

**Why it matters:** These operations are irreversible. The cost of pausing to confirm is low; the cost of an unwanted deletion is very high.

---

## Soft rules

### `nfr-before-m-tasks`
**Surfaced by:** `youk-core.route_task()` for M+ tasks

For any task sized M or larger, youk surfaces a reminder to run an NFR check first. NFR = Non-Functional Requirements: what breaks, what scales, what's observable, what's secure.

You can skip this. The point is to make it a conscious choice, not an oversight.

### `spec-before-l-tasks`
**Surfaced by:** `youk-core.route_task()` for L+ tasks

For L and XL tasks (system-level work, multi-day), write a spec first. youk-code's `route_to_skill("write-spec", task)` runs the spec skill.

### `session-close-cluster`
**Surfaced by:** `youk-core.session_end()`

At session end, surface the three closing skills as one prompt: context-sync (update sprint state), learn (extract knowledge), humanize (review voice in outputs). Surfaced once — you can skip any or all.

### `adr-for-real-alternatives`
**Surfaced by:** CLAUDE.md proactive pattern

When a recommendation has real alternatives that were rejected, an Architecture Decision Record is worth making. The ADR skill documents the decision, the context, the alternatives, and why they were rejected. This is what makes architecture decisions auditable months later.

---

## Changing guard rails

To add, remove, or modify a rule:

1. Edit `config/guardrails.yaml`
2. If it's a hard rule, update the enforcement logic in the relevant server file
3. Commit the change with a note on why
4. Rebuild: `make rebuild`

A guard rail that's only in a markdown file is a suggestion. A guard rail that's in `guardrails.yaml` and enforced at the tool level is a contract.
