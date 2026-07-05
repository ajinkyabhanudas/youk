# SaaS Domain — write-spec Additions

Apply this structure when writing specs for a SaaS product. These sections are
MANDATORY for any feature that touches billing, onboarding, user activation, or retention.

---

## Required spec sections (SaaS)

### Objective + Key Results

Every spec must open with:

```
Objective: {What we're trying to achieve — one sentence, outcome-oriented}

Key Results:
- KR1: {Measurable metric} from {baseline} to {target} by {date}
- KR2: {Measurable metric} from {baseline} to {target} by {date}
- KR3: {Measurable metric} from {baseline} to {target} by {date}
```

Rules:
- Key Results must be measurable. "Improve onboarding" is not a KR. "Increase day-7 activation rate from 32% to 48%" is.
- If the team does not have a baseline metric, the first KR must be "Establish baseline: instrument X and report by {date}."
- Maximum 3 KRs. If there are more, the scope is too broad.

---

### User stories (SaaS format)

```
As a {persona}: {free, trial, paying, admin, power user}
I want to {action}
So that {outcome for me}

Acceptance criteria:
- [ ] {specific, testable condition}
- [ ] {specific, testable condition}
```

Persona must be one of the defined SaaS personas — not a generic "user."
Common SaaS personas: `free user`, `trial user`, `paying customer`, `team admin`, `org owner`, `internal ops`.

---

### Billing and plan impact

For any feature touching access or limits:

```
Plan availability:
- Free:  {included / excluded / limited to N}
- Pro:   {included / excluded / limited to N}
- Team:  {included / excluded / unlimited}

Upgrade prompt: {Shown when? What copy? Where does it lead?}
Downgrade behavior: {What happens to data/state when user downgrades?}
Grandfathering: {Are existing users on old plans affected? Yes/No + rationale}
```

---

### Activation and success metrics

```
Primary metric:   {The single number that tells us if this shipped successfully}
Secondary metric: {Supporting signal — leading indicator or guardrail}
Guardrail metric: {What must NOT get worse — churn rate, support ticket volume, etc.}

How to measure:
- {Specific event or query for each metric}
- Dashboard: {Mixpanel / Amplitude / Metabase / custom}
- Alert threshold: {When do we get paged if primary metric drops?}
```

---

### Risks and rollback

```
Launch risk:   {What could go wrong in the first 24h?}
Rollback plan: {How do we disable this if it's broken — feature flag? migration reversal? hotfix?}
Rollout order: {Internal → beta users → 10% → 50% → 100%? Or full launch?}
```

---

## Quality bar for SaaS specs

A spec is complete when all of these are true:
- [ ] Objective is outcome-framed, not output-framed ("activation improves" not "feature is built")
- [ ] All KRs are measurable with a named metric, baseline, and target
- [ ] Plan availability is explicitly stated (not implied)
- [ ] Acceptance criteria are testable by QA without reading the PR
- [ ] Rollback mechanism is named (not "we'll figure it out")
- [ ] Success metric has a named data source or query
