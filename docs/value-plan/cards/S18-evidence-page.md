# S18 Evidence page

Size S. Depends: G2, S10. Metric: external credibility.

**Goal.** Publish what the numbers show, with method and limits. Nothing the data does not support.

**Why.** Superpowers has stars and no outcome data. A small, honest, reproducible result is the differentiator.

**Load.** `bench/results/`, the analysis output, the anchor's "Limits" section.

**Build.** One page: method, arms, task counts, intervals, cost, limits, how to reproduce (`make` target). Claims limited to what
the intervals support. If lean does not beat bare, say so and publish the finding anyway.

**Tests.** A script regenerates the page numbers from `bench/results/`; CI checks they match.

**Out of scope.** Marketing copy beyond the results.

**DoD.** Standard DoD. the owner reviews before it is shared (publishing is outward-facing).

**Kill criterion.** None.

**Handoff.** Link and the list of claims with their supporting rows.
