# Threat Scenarios — Pre-built by Surface Type

Load the sections matching the surfaces identified in Phase 1 (SURFACE).
For each listed threat: confirm whether the current control is present, absent, or partial.

---

## Auth endpoint (login, token refresh, OAuth, session management)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Token forged or replayed | Spoofing | HIGH | Signature verified? Expiry checked? Nonce/state used? |
| Session not invalidated after logout | Elevation | MED | Old session tokens rejected after logout call? |
| Brute-force on credential endpoint | DoS | MED | Rate limiting present? Account lockout after N failures? |
| Token leaked in URL or logs | Info disclosure | HIGH | Token in query param? Logged in access logs or error output? |
| OAuth state parameter missing | Tampering | HIGH | CSRF protection via `state` param? Validated on callback? |

---

## External API caller (outbound request with API key or credential)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Key exposed in error response or logs | Info disclosure | MED | Key visible in log lines, error messages, or response bodies? |
| Unbounded wait if external service hangs | DoS | HIGH | Request timeout set? Retry budget bounded? |
| SSRF — attacker controls URL destination | Elevation | MED (HIGH if user-controlled URL) | URL constructed from user input? Allowlist enforced? |
| Stale/revoked key used silently | Spoofing | LOW | 401 from external API surfaces as error to caller? |
| Excessive scope on API credential | Elevation | MED | Key permissions limited to minimum required? |

---

## Data persistence (write to DB, file, or cache)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Injection via unsanitised input | Tampering | HIGH | Parameterised queries? ORM safe? No f-string SQL? |
| Overwrite another user's data | Elevation | HIGH | Row/record scoped to current user before write? |
| PII written to non-encrypted store | Info disclosure | MED | Sensitive fields encrypted at rest or excluded from storage? |
| Destructive write without rollback | Tampering | MED | Transaction boundary present? Failure leaves consistent state? |
| Audit trail missing | Repudiation | MED | Write logged with actor + timestamp? |

---

## Credential handling (read, write, or pass API keys/passwords)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Credential hardcoded in source | Info disclosure | CRITICAL when present | Any literal key/password/token in code or config committed? |
| Credential in environment but logged | Info disclosure | HIGH | Env var content printed to stdout, logs, or error output? |
| Credential not rotatable | Elevation | MED | Is the credential reference soft (env var / secret mount) not hard? |
| Credential passed in URL param | Info disclosure | HIGH | Credential in query string or path — shows in access logs |
| Secret in test fixture | Info disclosure | MED | Test data uses real credentials instead of mocks? |

---

## Destructive operation (delete, reset, purge, overwrite)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Accidental mass deletion | Tampering | HIGH | Scope bounded? Wildcard match checked? Dry-run mode available? |
| No confirmation gate | Tampering | HIGH | confirmed=True or equivalent required before execution? |
| Irreversible without backup | Tampering | MED | Soft-delete or backup available? Point-in-time recovery possible? |
| No audit trail | Repudiation | HIGH | Destructive action logged with actor, timestamp, scope? |

---

## Access control decision (permission check, role check, resource guard)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Path-based auth bypass | Elevation | HIGH | Check is on resource, not URL pattern? Route wildcards safe? |
| Horizontal privilege escalation | Elevation | HIGH | User A cannot access User B's resource by guessing ID? |
| Auth before expensive compute | DoS | MED | Auth check happens first, before any DB query or heavy work? |
| Missing role check on admin path | Elevation | HIGH | Admin endpoints check role, not just authentication? |
| Trust-by-default for internal caller | Elevation | MED | Internal services still validated, not implicitly trusted? |

---

## User input processing (form data, API params, file upload, URL params)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Injection (SQL, command, template) | Tampering | HIGH | Input reaches an interpreter without escaping? |
| Oversized input causes OOM or timeout | DoS | MED | Max length / size enforced before processing? |
| Malicious file type accepted | Elevation | MED | File type validated by content, not extension? Stored outside webroot? |
| Reflected content enables XSS | Tampering | HIGH | User input echoed back to a browser without escaping? |
| Mass assignment from request body | Elevation | MED | Only allowlisted fields bound from request to model? |

---

## youk MCP tool (new tool in youk-core or youk-code server)

| Threat | STRIDE | Likelihood | What to check |
|---|---|---|---|
| Tool writes outside permitted paths | Elevation | CRITICAL check | Any file write targets outside /youk/ or /claude/skills/? |
| confirmed=True bypassed | Elevation | CRITICAL check | Destructive action requires confirmation before executing? |
| Tool stores raw conversation content | Info disclosure | CRITICAL check | No transcript, message, or chat history written anywhere? |
| Tool exposes credential via return value | Info disclosure | HIGH | Return value includes API key, token, or password? |
| Tool allows path traversal via parameter | Elevation | MED | File path params sanitised? No `../` traversal possible? |
