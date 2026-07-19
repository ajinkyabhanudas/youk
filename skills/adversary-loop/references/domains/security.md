# Domain Angles — Security

Load when direction involves: authentication, authorization, user input handling,
secrets management, file access, inter-service trust, audit logging, or any
feature that controls what a user can see or do.

These angles supplement the 11 standard angles — they do not replace them.
Run standard angles first, then inject these as additional attack surfaces.

---

## SEC-1 — Input Validation and Injection

**Angle:** Does this direction trust input it shouldn't, or fail to sanitize
input before using it in a sensitive context?

Attack questions:
- Is any user-supplied input used in a SQL query without parameterization?
- Is any user-supplied input rendered in a response without escaping?
- Is any user-supplied input used in a shell command, file path, or URL without validation?
- Does the code validate input at the boundary (first point of entry), or does it
  assume sanitization happened upstream?
- Are there inputs that are valid individually but dangerous in combination?

Weight signal: BLOCKING if SQL injection or command injection possible. BLOCKING if XSS on authenticated surface.

---

## SEC-2 — Authentication and Session Management

**Angle:** Can an unauthenticated user reach this endpoint or data,
or can an authenticated user escalate their privileges?

Attack questions:
- Is authentication checked before any data is returned or action is taken?
- Is the authentication check in a middleware/decorator, or inline in each handler
  (inline = easier to forget)?
- Can a user manipulate their session token to impersonate another user?
- Does the session expire? Can it be invalidated on logout?
- Does the code distinguish between "not authenticated" and "authenticated but unauthorized"?

Weight signal: BLOCKING if unauthenticated access to sensitive data. HIGH if no session expiry.

---

## SEC-3 — Authorization (What an Authenticated User Can Do)

**Angle:** Does this direction enforce that a user can only access their own data,
or data they have explicit permission to see?

Attack questions:
- Does the code filter query results by the authenticated user's ID, or could a user
  request another user's records by changing an ID parameter?
- Is ownership checked on every write operation, not just reads?
- Are there admin-only operations that check for admin role, or just authentication?
- Is there a horizontal privilege escalation path (user A accessing user B's data)?
- Is there a vertical privilege escalation path (regular user accessing admin function)?

Weight signal: BLOCKING if horizontal privilege escalation is possible (IDOR).

---

## SEC-4 — Secrets and Credential Exposure

**Angle:** Could secrets, credentials, or sensitive data be exposed through
logs, error messages, responses, or version control?

Attack questions:
- Are any secrets (API keys, passwords, tokens) hardcoded in source files?
- Are any secrets logged at any log level?
- Are full error messages (including stack traces with file paths) returned to the client?
- Does any response include fields that should be server-side only (password hashes, internal IDs)?
- Are secrets excluded from version control (.gitignore, .env pattern)?

Weight signal: BLOCKING if secrets could reach logs or responses.

---

## SEC-5 — Audit Trail

**Angle:** Will this direction leave enough of a trail to diagnose a security
incident after it happens?

Attack questions:
- Are authentication successes and failures logged with enough context (user ID, IP, timestamp)?
- Are permission denials logged?
- Are writes to sensitive data logged with before/after values?
- Are audit logs write-once (append-only), or can they be modified or deleted?
- Is there a way to detect if audit logging itself failed?

Weight signal: HIGH if no auth failure logging. HIGH if sensitive writes are unlogged.

---

## Promotion history
Generated: 2026-07-19 | Source: seed domain file
