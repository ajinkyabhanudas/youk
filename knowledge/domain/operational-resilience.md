# Operational Resilience — Architecture Principles

Principles encoded in youk's server layer. Each entry states the rule, the enforcement point, and the gap it closes.

---

## 1. Read/Write Separation and Least Privilege

**Rule:** Read-only operations (gate checks, policy lookups) must not write side effects. Write operations must declare what they mutate.

**Enforcement:**
- `_increment_tool_call_count()` is removed from gate tools (`check_task_contract_gate`, `rebuild_knowledge_index`). Only state-mutating calls increment the counter.
- Tools that write state return `state_written: list[str]` — a declared manifest of paths written. Callers can verify side effects without reading implementation.
- Docker volume split is the infrastructure enforcement: `youk-code` mounts `~/.claude` read-only; only `youk-core` can write. Per-tool scoping via `state_written` is the code-level mirror.

**Gap closed:** `_increment_tool_call_count` was firing on every tool call including pure reads. This inflated `calls_since_compact`, triggered spurious compact nudges, and made the counter meaningless as a write-pressure signal.

---

## 2. Separation of Concerns

Five layers. Each owns exactly one responsibility:

| Layer | Owns | Does NOT own |
|---|---|---|
| **Model** | Interpretation, reasoning, selection, generation | Validation, authorization, execution, state mutation |
| **Tool / App** | Validation, authorization, execution, transactions, state mutation | Policy decisions ("is this allowed?") |
| **Policy** | "Is this allowed?" — rules from guardrails.yaml, hard/soft rule evaluation | Execution, state mutation |
| **Infrastructure** | Timeout, retry, rate limit, networking, Docker isolation | Business logic, policy |
| **Evaluator** | "Did it work?" — post-hoc verification, audit, scoring | Execution, policy |

**Consequence for tool design:** A tool that combines gate check + state write + graph mutation (`check_nfr_gate`, `check_challenge_gate`) violates this. The gate check is policy; the state write is app; the graph mutation is infrastructure. These are currently combined for pragmatic reasons (atomic passage). Future split: `check_nfr_policy(task, size, nfr_block) → {allowed: bool}` + `record_nfr_passage(slug)` as separate calls.

---

## 3. Error Classification and Retry

**Six categories (ErrorType enum in schemas.py):**

| Category | Retryable | Strategy | Trigger |
|---|---|---|---|
| `TRANSIENT` | Yes | backoff | Temporary network failure, service unavailable |
| `RATE_LIMIT` | Yes | backoff | Rate limit hit |
| `INPUT` | No | none | Invalid argument, missing field, schema violation |
| `AUTH` | No | none | Unauthorized or forbidden |
| `BUSINESS_RULE` | No | none | Gate blocked, contract violated, hard rule triggered |
| `SYSTEM` | No | none | Unexpected internal error |

**Retryable = TRANSIENT or RATE_LIMIT only.** Everything else surfaces to the appropriate human (developer for BUSINESS_RULE/INPUT, operator for AUTH/SYSTEM).

**`classify_error(error_type) → RetryDecision`** in `guardrails.py` maps any ErrorType to `{retryable, strategy, reason}`. Callers use this to decide whether to retry, surface, or escalate — without reading tool implementation.

**Tools annotate `error_type` on error paths:**
- `check_nfr_gate` blocked → `BUSINESS_RULE`
- `check_challenge_gate` blocked → `BUSINESS_RULE`
- `check_commit_quality` blocked → `BUSINESS_RULE`
- `save_contract` vague input → `INPUT`
- `write_skill_handoff` exception → `SYSTEM`

---

## 4. Idempotency

**Rule:** State-mutating operations must be safe to call twice. The second call must produce the same observable outcome as the first, or explicitly signal "already done."

**Gaps currently open:**
- `session_end` called twice overwrites the first audit entry — the second call wins silently. Fix: check for existing session close flag before writing.
- `promote_to_global_contracts` deduplicates at read time — concurrent calls can both pass the "not yet present" check before either writes. Fix: write-with-lock or atomic append + deduplicate-on-read with advisory note.

**What is correct now:** `mark_challenge_ran` accumulates rounds correctly across calls. `record_gate` in `ceremony_sequencer.py` is idempotent by design (checks for existing entry before appending).

---

## 5. Side Effect Declaration

**Rule:** Every tool that writes state declares `state_written: list[str]` in its return value. Paths use `{slug}` as a placeholder for the session slug.

**Current declarations:**
- `route_task` → `["state/{slug}/route-task-ran.json", "state/active_task.json"]`
- `check_nfr_gate` (on pass) → `["state/{slug}/nfr-check-ran.json", "state/active_task.json"]`
- `check_challenge_gate` (on pass) → `["state/{slug}/challenge-gate-passed.json", "state/active_task.json"]`
- `save_contract` (on write) → `["knowledge/projects/{slug}/contracts.md"]`
- `task_checkpoint` → `["state/task-checkpoints.jsonl"]`
- `write_skill_handoff` → `["state/session.json"]`

**Why this matters:** A caller that sees `state_written` can reason about what changed without reading the tool body. Tests can assert the right paths were declared. Future audit tooling can replay which tools mutated which state paths per session.

---

## 6. Observability

**Per-tool observability contract:**
- Return `error_type` (ErrorType enum) on all error paths so callers classify without string matching
- Return `state_written` (list of paths) on all write paths so callers know what was mutated
- `calls_since_compact` on state-mutating tools only — read-only tools do not increment

**Session-level observability:**
- `track_tokens` accumulates per-session token usage
- Audit log (`~/.claude/audit/YYYY-MM.md`) captures skills invoked, findings, autonomy depth, close cluster
- `failure_pattern_detector.py` scans audit log for recurring categories — surfaces patterns before a 4th attempt

---

## 7. Tool Granularity

**Current combined tools (known debt):**

| Tool | Policy check | State write | Graph mutation |
|---|---|---|---|
| `check_nfr_gate` | ✓ | ✓ (nfr-check-ran.json) | ✓ (task graph) |
| `check_challenge_gate` | ✓ | ✓ (challenge-gate-passed.json) | ✓ (task graph) |
| `approve_task_contract` | ✓ | ✓ (contract file) | — |

These combine policy + state for atomicity — a gate that passes but fails to write its flag would allow replay. The atomicity is correct for now. The debt is that they are not unit-testable at the policy layer independently.

**Correctly separated (reference pattern):**
- `save_contract`: validates input (INPUT error) separately from writing state (state_written). Two distinct failure modes, two distinct return shapes.
- `classify_error`: pure function, no side effects. Returns retry decision from error type alone.
