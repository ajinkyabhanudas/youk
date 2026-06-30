# Prioritization Framework — P0 / P1 / P2 Criteria

Used in the RECOMMEND phase. Determines the priority level of a feature based on
user impact, urgency, and cost.

---

## Priority Levels

### P0 — Do This Now

**Definition:** The product or a critical workflow is broken or blocked without this.
OR: An imminent external deadline requires this.

**Criteria (any one is sufficient):**
- A current P0 feature cannot be completed without this
- A committed stakeholder demo, handover, or deadline depends on this
- The product is incorrect or misleading without this (data integrity / safety issue)
- A security vulnerability requires this to be addressed immediately
- A blocking user-facing error cannot be worked around

**P0 examples:**
- Fixing a SQL injection vulnerability before a user demo
- Adding a missing feature that was committed to a handover deadline
- Correcting results that are factually wrong (schema mismatch, wrong column used)

**What P0 is NOT:**
- "This would make the product much better"
- "Users have asked for this"
- "This is technically elegant"

---

### P1 — Do This Soon

**Definition:** High user value with understood technical cost. Should be the next
thing after current P0s complete.

**Criteria:**
- Directly improves the primary use case for the primary user
- Cost is understood (S or M complexity, no significant unknowns)
- Would be noticed and valued by users within the first week of use
- No hard deadline, but meaningful to ship before the next major milestone

**P1 examples:**
- Cache hit UI indicator (Jajean would see faster responses and trust the tool more)
- Export to CSV (enables the primary workflow of sharing results with donors)
- Better error messages (reduces user confusion on SQL failures)

**What P1 is NOT:**
- Features that would be used less than once a week by the primary user
- Features with XL technical cost relative to their user impact
- Features that depend on resolving an unknown first

---

### P2 — Do This Eventually

**Definition:** Real value, but not urgent. Will be built when P0s and P1s are clear.

**Criteria:**
- Improves the product but doesn't change whether it works for the primary use case
- Could be deferred one or two releases without the user noticing significantly
- OR: High value but L/XL cost that can't be justified yet against current priorities

**P2 examples:**
- Multi-language support (important long-term, not needed for v1 handover)
- Usage analytics dashboard (helpful for understanding patterns, not needed for core use)
- Advanced query history filtering (power user feature, primary use case works without it)

---

### DEFER — Not Now, But Real

**Definition:** The problem is real and the feature has value, but the timing is wrong.
Deferral requires a specific trigger — not "later."

**Valid deferral triggers:**
- "When active users exceed N"
- "After we have usage data on query patterns"
- "After the handover deadline is met"
- "When the external API provides the required capability"
- "After a specific dependency is unblocked"

**DEFER examples:**
- IUCN integration: deferred until API key is obtained
- Semantic caching: deferred until usage patterns justify embedding cost
- Multi-user authentication: deferred until product moves beyond single-user pilot

---

### REJECT — Not Ever

**Definition:** This should not be built. The problem it solves is out of scope, or
the cost permanently outweighs the benefit, or it conflicts with the product's core value.

**When to REJECT (not just DEFER):**
- The feature serves a user type that is explicitly out of scope for this product
- Building it would compromise the core user experience or security model
- It requires infrastructure that will never be justified for this product's scale
- It addresses a problem that is better solved by a different product

**REJECT examples:**
- Real-time data streaming from the DB (canopy is a query tool, not a monitoring dashboard — different product)
- Administrative user management UI (single-user Docker deployment; out of scope for v1 and likely v2)
- LLM fine-tuning on Jocotoco data (out of scope, different capability entirely)

---

## Calibration for Small Teams

Standard PM frameworks are built for large teams. Calibrations for solo / small team:

| Standard concept | Small team equivalent |
|---|---|
| OKRs | Single goal per week/sprint |
| Sprint planning | "What are the 3 most important things this week?" |
| Roadmap | 4-6 features with P0/P1/P2 labels |
| Stakeholder alignment | 1:1 with the one person who has final say |
| Metrics | 1-2 proxy metrics that are easy to track |
| User research | 1 conversation with the primary user |

---

## Impact vs. Cost Matrix

When prioritizing between multiple features, use this quick matrix:

```
          LOW COST         HIGH COST
HIGH   ┌─────────────┬─────────────┐
IMPACT │  DO FIRST   │  DO SECOND  │
       │  (P0/P1)    │  (P1/P2)   │
LOW    ├─────────────┼─────────────┤
IMPACT │ QUICK WINS  │   REJECT    │
       │  (P2/DEFER) │  or DEFER   │
       └─────────────┴─────────────┘
```

High impact + low cost = no-brainer P1.
High impact + high cost = P1 with clear scope reduction plan.
Low impact + low cost = P2 or quick win batch.
Low impact + high cost = REJECT until the cost drops or impact is re-assessed.

---

## Priority Conflicts

When a new feature competes with an in-flight P0:

**Rule:** New P0 features can only displace in-flight P0 work if the new P0 is more
urgent by the criteria above — not just more interesting. State the displacement explicitly:
"This becomes P0, which means [current P0] is delayed by N days."

Never silently add to the P0 queue. Make the trade-off visible.
