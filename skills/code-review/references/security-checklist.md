# Security Checklist — By Risk Tier

Run only the checks for the detected risk tier and above. Each check is pass/fail.
Emit findings using the standard FINDING format with severity tagged.

---

## Always (any risk tier)

- [ ] **Hardcoded secrets** — no API keys, tokens, passwords, or connection strings in code
- [ ] **Credential in test fixtures** — no real credentials in test data, even as examples
- [ ] **Shell injection** — subprocess/os.system calls with user-controlled input?
- [ ] **Path traversal** — file paths constructed from user input without sanitisation?

**youk-specific (always):**
- [ ] **Write-path** — no new code writes outside `/youk/` or `/claude/skills/`
- [ ] **Transcript storage** — no code stores raw conversation content or message history
- [ ] **confirmed=True** — no MCP tool applies destructive changes without this gate

---

## MEDIUM risk tier (business logic — adds to the above)

- [ ] **Input validation** — all data crossing a trust boundary is validated before use
- [ ] **Type coercion** — implicit coercions that produce unexpected values (e.g. JS `==`, Python truthy on 0)
- [ ] **Logging PII** — does log output include names, emails, phone numbers, or user IDs?
- [ ] **Logging credentials** — do error messages or debug logs include tokens, keys, or passwords?
- [ ] **Error messages** — do error responses reveal internal state, stack traces, or server paths?

---

## HIGH risk tier (auth / data / infra / external API — adds to MEDIUM above)

**Authentication:**
- [ ] **Auth bypass** — can the authentication check be short-circuited? (e.g., truthy check on falsy value, early return)
- [ ] **Token validation** — token signature verified before use? Expiry checked?
- [ ] **Session fixation** — session ID regenerated on privilege change?

**Authorization:**
- [ ] **Resource-level check** — auth check is on the resource, not just the path or route
- [ ] **Horizontal privilege** — user A can't access user B's data through predictable IDs?
- [ ] **Auth before compute** — expensive operation gated on auth (not auth after work is done)
- [ ] **Internal trust** — internal callers are not trusted by default; still validated

**External dependencies:**
- [ ] **New package** — name + purpose stated, no known CVEs, not a transitive of a known-bad package
- [ ] **Timeout** — all external calls have a request timeout set
- [ ] **429 handling** — rate limit response handled (not silently retried or silently failed)
- [ ] **SSRF** — URL constructed from user input? Must be allowlisted, not blocklisted

**Data persistence:**
- [ ] **SQL injection** — parameterised queries used? No f-string or concatenated SQL
- [ ] **Mass assignment** — ORM model updated from raw request dict without allowlisting fields?
- [ ] **Sensitive data at rest** — PII, credentials, or tokens stored in plaintext?
- [ ] **Audit trail** — destructive data operations logged with timestamp and actor?

**Infra / config:**
- [ ] **Least privilege** — new IAM role / API scope is minimal for the stated purpose
- [ ] **Secret rotation** — new secrets/keys can be rotated without code change?
- [ ] **TLS** — new external connections use TLS; no `verify=False`

---

## Verdict mapping

| Finding | Severity |
|---|---|
| Hardcoded secret (any tier) | CRITICAL |
| Auth bypass possible | CRITICAL |
| youk write-path or transcript rule violated | CRITICAL |
| confirmed=True bypassed | CRITICAL |
| SQL injection | CRITICAL |
| Token not validated before use | HIGH |
| Logging credentials | HIGH |
| Auth before compute violated | HIGH |
| Missing timeout on external call | HIGH |
| SSRF without allowlist | HIGH |
| PII in logs | MEDIUM |
| Error message leaks internals | MEDIUM |
| New package without CVE check | MEDIUM |
| Missing 429 handling | LOW |
| Secret not rotatable | LOW |
