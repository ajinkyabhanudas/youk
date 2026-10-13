# youk code review and remediation

2026-10-13

## Result

All actionable implementation findings from the audit are fixed. Credential use is environment-only, hard Bash checks fail closed, state updates are safe under concurrent writers, and project research uses the configured provider adapter. CI now includes the L2, L3, and L6 integration target.

## Changes made

| Area | Fix | Proof added |
| --- | --- | --- |
| Credentials | Removed all runtime reads and writes of provider key files. Provider configuration contains no credential. | Provider tests prove legacy files are ignored and CLI setup cannot copy a key. |
| Research | Replaced the Anthropic-specific call with the shared inference provider adapter. | Project-research tests cover configured and unavailable providers. |
| Hard Bash rules | A contract-check failure now denies the command and explains why. | Hook test injects a checker failure. |
| Route-state race | Added a locked JSON read-update-write helper and use it for route records. | Threaded test confirms both concurrent route entries survive. |
| State durability | `atomic_write` now fsyncs a temporary file and replaces the destination while locked. | Test confirms a failed staging write leaves the previous file intact. |
| State paths | Path resolution is read-only. Write code creates directories explicitly. | Tests prove reads do not create a directory. |
| Session marker | Marker-write failures return a typed degraded field and a visible session-plan warning. | Session test forces an `OSError`. |
| CI | Added Docker-backed L2 routing, L3 skills, and L6 session coverage to CI. | Images build and the selected suite runs locally. |

## Value claim

No code change can establish the main product claim. The current G1 result is correctly recorded as inconclusive in `DECISIONS.md`: 14 tasks, one run per arm, no reliable delivery improvement, and about 20% extra cost. The next pre-sized evaluation must run before claiming measured user-outcome improvement.

## Validation

- `uv run ruff check servers/ scripts/ plugin/scripts/ tests/` passed.
- Focused remediation suite: 285 passed.
- Full suite: 3,766 passed, 4 skipped. One unrelated local baseline failure remains: an ignored `skills/compaction` symlink contradicts `tests/test_lean_context.py`, which requires that path not exist.
- `make build` passed for `youk-core:latest` and `youk-code:latest`.
- Standard integration invocation passed 3 tests, skipped 36 because a live session is open and the suite refuses to mutate it. An isolated Docker run exercised the tests instead of skipping. It exposed older fixtures that still assume root-level breadcrumbs and a root marker with `slug`; current runtime state correctly uses `sessions/{slug}/` and root `active_slug` as the redirect. The client and first affected fixture assertions were corrected; the remaining legacy integration assumptions should be normalized before using the new CI gate as a release blocker.
- `git diff --check` passed.
- The document graph has no broken links. It reports two existing semantic-drift items and four older policy-document checks outside this remediation.

## Review scope

The audit covered credential flow, provider boundaries, Bash gates, state mutation, session lifecycle, CI, documentation, and value evidence. No `.env` file or secret value was read.
