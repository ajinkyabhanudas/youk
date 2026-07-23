---
name: security-review
rationale_why: "Security flaws in auth and data paths are invisible until exploited. Building a threat model before checking means you look for what can go wrong, not just what you remember to check."
description: >
  Focused security review for changes touching auth, credentials, external
  APIs, destructive operations, data persistence, or access control. Goes
  deeper than code-review's security phase — builds a threat model first,
  then runs targeted checks against it. Produces a SAFE / SAFE WITH NOTES /
  BLOCKED verdict with evidence. Triggers on: /check workflow command when
  auth or credentials are in scope, any change to guardrails config, any
  new external integration, any change to how data is written or stored.

auto-skip: |
  Skip if code-review already ran a HIGH-tier security phase this session
  AND no new auth/credential surface was added since. Check if
  code-review verdict includes "Security: HIGH-tier complete".
---

# security-review — Security-Focused Review Skill

Threat-model-first security review. Does not repeat what code-review
already covers — runs only when the change has a meaningful security
surface and goes deeper than code-review's checklist.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full review: SURFACE → THREAT MODEL → CHECKS → VERDICT |
| `quick` | SURFACE → CHECKS (skip formal threat model for simple changes) |
| `credentials only` | Check only for credential exposure and storage patterns |
| `destructive only` | Check only for destructive operation guard rails |

---

## Context Capture

```
CHANGE:       [what changed — one sentence]
SURFACE:      [auth / credentials / external API / data write / destructive op / access control]
TRUST BOUNDARY: [does this change move data across a trust boundary?]
PRIOR DECISIONS: [relevant ADRs or guardrails this touches]
```

If no security surface is identified in SURFACE — state it and stop.
Not every change needs a security review. The value is in identifying
the actual surface, not running a checklist on code that has none.

---

## The Four Phases

Each phase begins with `[PHASE: NAME]`.

---

### Phase 1 — SURFACE

1. Identify all security surfaces in the change. Be specific:
   - Where does data enter the system from an untrusted source?
   - Where does the code make an access control decision?
   - Where are credentials read, written, or passed?
   - Where does the code call external systems?
   - Where does the code perform destructive or irreversible operations?
2. For each surface: state what it does and what happens if it is bypassed or compromised.
3. If no meaningful surface: emit `[NO SECURITY SURFACE]` and stop. This is a valid outcome.

> Compact phase summary: "N surfaces identified: [list]. Proceeding to threat model."

---

### Phase 2 — THREAT MODEL

For each identified surface, enumerate threats. Use STRIDE as a lens —
pick only the categories that apply, skip the rest:

- **Spoofing**: can an attacker impersonate a trusted party?
- **Tampering**: can input be modified in transit or at rest?
- **Repudiation**: can actions be denied because they aren't logged?
- **Information disclosure**: can sensitive data leak through errors, logs, or responses?
- **Denial of service**: can the surface be abused to exhaust resources?
- **Elevation of privilege**: can a lower-trust caller gain higher-trust access?

For each relevant threat:
```
THREAT: {STRIDE category} — {specific attack scenario}
Surface: {which surface}
Likelihood: HIGH | MED | LOW
Impact: HIGH | MED | LOW
Current control: {what mitigates this, if anything}
Gap: {what is missing}
```

> Compact phase summary: "N threats modelled. Highest severity: ___. Proceeding to checks."

---

### Phase 3 — CHECKS

Run targeted checks against the surfaces and threats identified.

**Credential handling:**
- Credentials read from env vars or mounted secrets — not hardcoded
- Credentials not logged, not included in error messages, not returned in API responses
- Credential files excluded from any serialisation or export path

**youk-specific hard rules (any violation = BLOCKED immediately):**
- No code writes outside `/youk/` or `/claude/skills/` paths
- No code stores raw conversation content (transcripts, message history)
- No MCP tool applies proposals without `confirmed=True`
- No guardrail hard rule is bypassed or soft-coded out
- No new `--no-verify` or equivalent bypass added to any commit or push path

**External API / integration:**
- API key scoped to minimum required permissions
- Request timeouts set — no unbounded wait
- Error responses from external service handled — no silent success on failure
- Rate limit handling present if endpoint can 429

**Destructive operations:**
- Confirmation gate present before write (`confirmed=True` pattern)
- Scope is bounded — no wildcards that affect more than intended
- Audit trail: destructive action is logged with timestamp and caller context

**Access control:**
- Check is on the resource, not just the path (path-based auth bypass)
- Auth check happens before expensive operations (auth before compute)
- No trust-by-default for internal callers (internal ≠ trusted)

After all checks:
- List passed checks briefly
- List failed checks with finding format (same as code-review ANALYZE)

> Compact phase summary: "N checks run. N passed, N failed. Highest finding: ___."

---

### Phase 3.5 — SELF-CHECK

Mandatory before emitting VERDICT. Two questions — each requires a specific named answer.

**Q1 — Depth check:**
"What is the attack vector this review would miss if the attacker already has read access
to the application config? Name the specific escalation path. If I cannot name it, I have
run a checklist, not a threat model."

**Q2 — Fit check:**
"Is the most dangerous finding in my output actually dangerous in THIS system's threat model,
or am I applying a generic checklist to a context that doesn't fit? If the answer is 'generic
checklist' — the finding gets demoted or removed."

Emit one of:
- `[DEPTH NOTE: {specific escalation path named, or "none — config read access not applicable"}]`
- `[FIT CHECK: {N findings confirmed context-specific / "all findings are context-appropriate"}]`
- `[SHALLOW: {what wasn't looked at — specific surface missed}]`

`[SHALLOW]` is a valid and honest outcome. Do not manufacture a threat.

---

### Phase 4 — VERDICT

```
[SECURITY VERDICT]
Status:  SAFE | SAFE WITH NOTES | BLOCKED

Threat summary:
  {Top threat and current mitigation, or "No significant threats identified."}

Must resolve before merge:
  {CRITICAL/HIGH findings. Empty if none.}

Notes (non-blocking):
  {MEDIUM/LOW findings. Merge allowed with acknowledged risk.}

Evidence:
  {Surfaces checked, threat categories applied, hard rules verified.}
```

Rules:
- `BLOCKED` if any youk hard rule violation OR any CRITICAL finding
- `SAFE WITH NOTES` if MEDIUM findings remain but no CRITICAL/HIGH
- `SAFE` if all findings are LOW or INFO
- `BLOCKED` overrides everything — no partial approval on hard rule violations

---

## Quality Bars (Non-Negotiable)

- **Threat model before checklist.** Checks without a threat model produce false confidence. Identify the surface first.
- **youk hard rules are non-negotiable.** A change that bypasses confirmed=True or writes outside permitted paths is BLOCKED regardless of intent.
- **"No surface" is a valid outcome.** Not every change needs this skill. Stating "no security surface found" is correct when true.
- **Evidence is mandatory.** State which surfaces were checked and which checks were run. "Looks secure" is not a verdict.
- **Credentials in code = CRITICAL.** Caught here: immediate block. No exceptions for test values, example values, or "temporary" tokens.

---

## Reference Files

| File | When to read |
|------|--------------|
| `references/threat-scenarios.md` | THREAT MODEL phase — pre-built scenarios by surface type |

---

## Example Flows

**Auth change — /check triggered:**
> "Added OAuth token refresh logic to the API client."

SURFACE (credential read + external API call) → THREAT MODEL (spoofing:
can token be reused after expiry? Information disclosure: does error
response include token? Tampering: is token validated before use?) →
CHECKS (timeout set ✓, token not logged ✓, refresh failure handled ✓,
credential not hardcoded ✓) → VERDICT (SAFE — all checks passed, token
lifecycle handled correctly)

**New guardrail config change:**
> "Modified guardrails.yaml to add a new soft rule."

SURFACE (guardrails config — governs all hard rule enforcement) →
THREAT MODEL (elevation: does new rule weaken existing hard rule coverage?
Repudiation: is the change logged?) → CHECKS (hard rules unchanged ✓,
new rule is additive not subtractive ✓, no bypass introduced ✓) →
VERDICT (SAFE WITH NOTES: soft rule trigger phrase could be more specific)

**Credential accidentally committed:**
> "Added ANTHROPIC_API_KEY=sk-... to .env.example"

SURFACE (credential in tracked file) → CHECKS (youk hard rule: no
credential commits → CRITICAL) → VERDICT (BLOCKED — credential in
committed file. Remove immediately, rotate the key, add to .gitignore.)
