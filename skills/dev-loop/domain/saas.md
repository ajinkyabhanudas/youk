# SaaS Domain — dev-loop Additions

Apply during relevant phases. Skip rows where the surface is not present.

---

## UNDERSTAND additions (SaaS)

Before writing any code, check:

1. **Billing surface**: Does this feature touch subscription state, seat counts, plan limits, or feature gating? If yes, flag before WRITE and confirm the billing model is understood.
2. **Tenant isolation**: Does this feature access data that must be scoped to a tenant/organisation? Verify the query or data path includes a tenant filter — tenant-blind queries are a CRITICAL security surface.
3. **Feature flag**: Should this feature be launched behind a flag? New user-facing behavior should be gated until QA and gradual rollout are complete.
4. **Idempotency**: Does this feature process payment webhooks, subscription events, or any event that could be delivered more than once? Idempotency is MANDATORY — flag if missing.

---

## WRITE additions (SaaS)

| Pattern to apply | When |
|---|---|
| Feature flag wrapper around new behavior | Any new user-facing feature |
| Idempotency key check before processing payment/subscription event | Any webhook handler |
| Tenant scope assertion before any DB query | Any multi-tenant data path |
| Audit log entry for plan change, seat change, or payment event | Any billing mutation |
| Graceful degradation when billing service is unavailable | Any feature gated on billing state |

---

## AUDIT additions (SaaS)

| Check | Severity |
|---|---|
| Payment/subscription webhook processed without idempotency check | CRITICAL |
| DB query on tenant-scoped table without tenant filter | CRITICAL — data leak |
| Feature flag missing on new user-facing behavior | HIGH |
| Billing state read without fallback for billing service outage | HIGH |
| Seat/plan limit not enforced before provisioning new resource | HIGH |
| Trial expiry logic doesn't deactivate the account | HIGH |
| Payment failure doesn't trigger appropriate dunning/grace period | HIGH |
| Audit log missing for billing mutation (plan upgrade, downgrade, cancel) | MEDIUM |
| Hard-coded plan name or price ID (should be config or env var) | MEDIUM |

---

## TEST additions (SaaS)

Include tests for:
- Webhook delivered twice → second delivery is a no-op (idempotency)
- Tenant A cannot access Tenant B's data (isolation test)
- Feature flag OFF → feature is completely unavailable, no partial state
- Feature flag ON → feature works end-to-end
- Payment failure → account enters grace period, not immediately deactivated
- Plan limit reached → new resource creation is rejected with clear error
