# SaaS Domain — code-review Additions

Layer these checks on top of the base ANALYZE and SECURITY phases for SaaS codebases.

---

## Billing and subscription checks

| Check | Severity |
|---|---|
| Payment webhook handler processes without idempotency key check | CRITICAL |
| Subscription state mutated without an audit log entry | HIGH |
| Plan limits enforced client-side only (not server-side) | CRITICAL — trivially bypassed |
| Feature gating checks billing state without fallback when billing service is unavailable | HIGH |
| Stripe/Paddle/billing provider secret key referenced outside of server-side code | CRITICAL |
| Hard-coded plan ID, price ID, or product ID (should be env var or config) | MEDIUM |
| Proration or billing timing logic not covered by a test | HIGH |
| Trial expiry check relies on wall clock without timezone handling | HIGH |

---

## Tenant isolation checks

| Check | Severity |
|---|---|
| DB query on a multi-tenant table without a `tenant_id` / `org_id` filter | CRITICAL — data leak across tenants |
| Tenant ID taken from request body or URL param (not from authenticated session) | CRITICAL — tenant spoofing |
| Bulk operation (update, delete) without explicit tenant scope | CRITICAL |
| File storage path includes tenant ID from request, not from auth context | HIGH |
| API response includes resources from multiple tenants | CRITICAL |

---

## Feature flag and rollout checks

| Check | Severity |
|---|---|
| New user-facing behavior shipped without feature flag | HIGH |
| Feature flag evaluation result is cached without respecting TTL | MEDIUM |
| Feature flag SDK called on every request without caching (performance) | MEDIUM |
| Gradual rollout percentage hardcoded in code (not in flag config) | MEDIUM |
| Feature flag removal missed after full rollout (flag debt) | INFO |

---

## SaaS security additions

| Check | Severity |
|---|---|
| Payment method or card data handled directly (must flow through payment provider) | CRITICAL — PCI violation |
| PII (name, email, payment info) written to application logs | CRITICAL |
| User email used as a unique key without case normalization | HIGH — duplicate account risk |
| Password reset token not invalidated after first use | CRITICAL |
| API key scopes not enforced on endpoints that accept them | HIGH |
