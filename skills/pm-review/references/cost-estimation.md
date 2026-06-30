# Cost Estimation — S / M / L / XL Calibration

Used in the COST phase. Calibrated for solo Python developer with the canopy-style
stack (Python, Gradio, PostgreSQL, Anthropic API). Adjust for other stacks by analogy.

---

## Size Definitions

### S — Small (< 0.5 developer-days)

**What it is:** A well-understood, contained change. No new dependencies, no new
modules, no significant design decisions.

**Characteristics:**
- Change is localized to 1-2 files
- No new external I/O or service dependencies
- No new module created
- No schema changes
- No new NFR decisions required (change is within existing NFR decisions)
- Existing tests cover the change path; minor test additions needed

**Examples:**
- Adding a new constant or config value
- Adjusting an existing UI component (color, copy, layout)
- Adding a new column to a display table (data already exists)
- Fixing a bug where the behavior is already well-defined
- Adding a utility function that composes existing functions

---

### M — Medium (0.5 – 2 developer-days)

**What it is:** A new behavior with understood boundaries. May add a new function or
extend an existing module. Requires some design thinking but no major unknowns.

**Characteristics:**
- Change spans 2-5 files
- May require 1-2 new NFR decisions
- No new module created; extends existing ones
- May require a minor schema change (new column, index)
- Requires new tests for the new behavior
- No new external API or service dependency

**Examples:**
- Adding export-to-CSV functionality
- Adding a loading indicator to an async operation
- Adding a new filter or parameter to an existing query
- Adding caching to an existing code path
- Adding structured logging to an existing module
- A new Gradio component that reads from an existing data source

---

### L — Large (2 – 5 developer-days)

**What it is:** A new capability that requires a new module or significant integration.
Multiple unknowns exist. Requires substantial design before implementation.

**Characteristics:**
- New module created (new file in `src/canopy/`)
- Requires /nfr-check and likely /adr before implementation
- Requires new external dependency or API integration
- Requires schema changes (new table, significant column changes)
- Substantial new test coverage required
- Risk of affecting existing behavior requires careful boundary design

**Examples:**
- Adding user authentication and session management
- Integrating a new external API (IUCN Red List, other data source)
- Implementing semantic caching (new embedding model call, new similarity index)
- Building a new query analysis pipeline
- Adding export to multiple formats with different formatting logic
- Adding a background job runner

---

### XL — Extra Large (5+ developer-days)

**What it is:** A system-level change that requires architectural decisions at multiple
layers. Significant unknown territory. Should be broken into smaller pieces if possible.

**Characteristics:**
- Affects multiple modules and their interfaces
- Requires /pm-review + /nfr-check + /adr + /stress-test before any implementation
- May require infrastructure changes (new service, new DB, new deployment)
- High risk of unexpected scope expansion
- Cannot be estimated until scoped and designed

**Examples:**
- Multi-user support with authorization (auth system, per-user data isolation, session management)
- Migrating the LLM provider (changes every model interaction)
- Adding real-time streaming data integration
- Building a completely new UI paradigm (e.g., replacing Gradio with a custom React frontend)
- Full test suite rewrite or coverage campaign

**XL rule:** If a feature is XL, the first step is always to break it into L and M
pieces. Never start an XL feature as a single unit of work.

---

## Estimation Rules

### Rule 1: Estimate the unknown, not just the known

The visible implementation is usually 40-60% of the actual work. The rest is:
- Understanding the existing code before changing it
- Handling edge cases discovered during implementation
- Writing and debugging tests
- Updating documentation and living documents
- Unexpected interactions with other modules

**Calibration factor:** Multiply your first estimate by 1.5-2x for M and L work.

### Rule 2: Risk increases the estimate

| Risk type | Adjustment |
|---|---|
| Working in a module you haven't touched before | +50% |
| Depending on an external API with no prior integration | +50-100% |
| Changing a critical path (query loop, auth, data integrity) | +50% |
| No existing tests for the area being changed | +30% (must write them first) |
| Unknown data format or schema | +50% |

### Rule 3: The first-time tax

First time integrating a class of technology in this project (e.g., first external
API, first background job, first auth system): treat it as one size larger than it
would be otherwise. The second integration of the same class is the estimated size.

### Rule 4: When to escalate to SCOPE FIRST

If you cannot decide between M and L, the feature is not scoped well enough. Return
to the user with: "This could be M or L depending on whether we [specific decision].
Which do we want?"

---

## Debt Impact Assessment

Beyond size, assess what the feature does to the technical debt balance:

**Incurs debt:**
- Adds a "we'll handle this later" decision
- Bypasses an NFR (e.g., no caching because "we can add it later")
- Adds a module without tests
- Duplicates logic that should be shared

**Neutral:**
- Adds new functionality in a clean new module
- Follows existing patterns with appropriate tests

**Pays off debt:**
- Adds tests to existing untested code
- Extracts duplicated logic into a shared utility
- Adds monitoring to a previously unobservable module
- Replaces a known shortcut with the correct implementation

---

## Reference: Canopy Feature Estimates

Historical calibration for this specific project:

| Feature | Estimated | Actual | Notes |
|---|---|---|---|
| Cache module (LRU + TTL) | M | M | Well-defined, followed existing patterns |
| Query history (JSONL) | M | M | Clear spec, new module but simple I/O |
| Model abstraction layer | M | M | ABC + one implementation |
| Streaming UI | M | L | Thread+queue pattern had unexpected edge cases |
| Cache hit UI indicator | S | S | One Gradio component, existing data |
