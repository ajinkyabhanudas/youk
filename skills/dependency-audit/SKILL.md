---
name: dependency-audit
description: >
  Audits Python project dependencies for pinning discipline, transitive vulnerability
  exposure, and pyproject.toml / requirements.txt health. Fires when: new dependency
  added to pyproject.toml or requirements.txt, "are our deps safe?", "check for
  vulnerabilities", unpinned dependency found during code-review, pre-release gate,
  dependency version conflict reported. Produces: pinning audit, known CVE report
  (via pip-audit output or manual CVE check), and concrete remediation steps.
  Do NOT use for install sequence verification (install-experience), runtime errors
  (dev-loop), or system dependency checks (install-experience SCAN phase).
---

# dependency-audit — Python Dependency Pinning and Vulnerability Audit

Checks that every dependency is pinned, that transitive dependencies don't carry
known CVEs, and that pyproject.toml is structured for reproducible installs.

Built on the pattern that unpinned dependencies in AI engineering systems are a
reliability risk — not just a security risk. `anthropic>=0.20` resolves differently
in CI, on the developer's machine, and on a fresh install six months later.

---

## Invocation Grammar

| Invocation | Behaviour |
|------------|-----------|
| *(no directive)* | Full audit: INVENTORY → PINNING → VULNERABILITIES → REMEDIATE |
| `quick` | INVENTORY + PINNING only — skip vulnerability scan |
| `new: {package}` | Audit a single new package before adding it |
| `cve only` | VULNERABILITIES only — assumes pinning is already audited |
| `enter: REMEDIATE` | Skip to REMEDIATE — issues already identified |

fast-path: |
  If pyproject.toml and requirements.txt haven't changed since last audit (check git log):
  emit "Dependencies unchanged since last audit — skipping." Only re-run VULNERABILITIES
  if it's been > 30 days (new CVEs published since last check).

---

## Context Capture (Always First)

```
DEP_FILES:       [pyproject.toml and/or requirements.txt — read both if both exist]
SERVERS:         [list of server directories under servers/ — each may have its own deps]
PYTHON_VERSION:  [infer from pyproject.toml [tool.python] or .python-version file]
PIP_AUDIT_AVAIL: [check if pip-audit is installed: `which pip-audit` — yes | no]
LAST_AUDIT:      [git log --oneline -1 -- pyproject.toml requirements.txt — infer last change]
```

---

## The Four Phases

### Phase 1 — INVENTORY

1. Read `pyproject.toml` — extract all `[project] dependencies` entries and `[project.optional-dependencies]` groups.
2. Read `requirements.txt` if it exists — extract all package lines.
3. Check for per-server dependency files: `servers/{name}/requirements.txt` or per-server `pyproject.toml`.
4. Build a flat inventory:
   ```
   Package            Pinning     Specifier         Source
   anthropic          PINNED      ==0.25.0          pyproject.toml
   fastmcp            PINNED      ==0.4.1           pyproject.toml
   httpx              UNPINNED    >=0.24.0           pyproject.toml
   pytest             PINNED      ==8.1.0           pyproject.toml [dev]
   ```

5. Count totals: {N} packages, {M} pinned, {K} unpinned.

> Compact phase summary: full dependency inventory built; unpinned packages identified for Phase 2.

---

### Phase 2 — PINNING

For each unpinned package:

1. Classify the specifier:
   - `>=X.Y.Z` — minimum-only pin: installs latest compatible, not reproducible → **WARN**
   - `^X.Y.Z` or `~X.Y.Z` — range pin: better but still not reproducible → **WARN**
   - No specifier (bare package name) — completely unpinned → **FAIL**
   - `==X.Y.Z` — exact pin: reproducible → PASS

2. For each WARN/FAIL, determine the remediation:
   - Run (mentally or via Bash): `pip show {package}` to find current installed version
   - Suggest pinning to the currently installed version: `{package}=={current_version}`
   - If version unknown: flag as "pin to version verified in your environment before merging"

3. Check for version conflicts: if `pyproject.toml` requires `anthropic>=0.25` and `requirements.txt` requires `anthropic==0.20`, that is a CONFLICT → **FAIL**

4. Emit:
   ```
   [PINNING AUDIT]
   anthropic==0.25.0:   PASS
   httpx>=0.24.0:       WARN — range pin; suggest: httpx==0.27.0 (current installed)
   requests:            FAIL — no specifier; suggest: requests==2.31.0
   anthropic conflict:  FAIL — pyproject.toml >=0.25 vs requirements.txt ==0.20

   Summary: {N} PASS, {M} WARN, {K} FAIL
   ```

> Compact phase summary: pinning issues enumerated with suggested remediations; FAIL count determines severity.

---

### Phase 3 — VULNERABILITIES

1. If `pip-audit` is available:
   - Emit the command to run: `pip-audit --requirement requirements.txt` or `pip-audit` (from pyproject.toml)
   - Ask the developer to paste the output, OR if Bash access is available: run it directly
   - Parse the output for CVE IDs, package names, affected versions, and fixed versions

2. If `pip-audit` is NOT available:
   - For each PINNED package at a specific version, check known high-severity CVEs from training knowledge (limited — flag that this is not a substitute for pip-audit)
   - Flag: `pip-audit not installed — install with: pip install pip-audit. Manual CVE check is incomplete.`

3. For any CVE found:
   - Severity: CRITICAL / HIGH / MEDIUM / LOW (from CVE score)
   - Affected version: {version currently pinned}
   - Fixed version: {version that patches the CVE}
   - Remediation: `{package}=={fixed_version}` — update and re-run tests

4. Check for packages that are end-of-life or deprecated:
   - Python 2-only packages with no Python 3 version → FAIL
   - Packages with published deprecation notices (e.g. `pkg_resources` → `importlib.resources`) → WARN

5. Emit:
   ```
   [VULNERABILITY SCAN]
   Method: pip-audit | manual (incomplete)
   
   requests==2.28.0:   CRITICAL — CVE-2023-32681 (redirect header leak); fix: requests==2.31.0
   httpx==0.23.0:      HIGH — CVE-2023-38323; fix: httpx==0.24.1
   anthropic==0.25.0:  PASS — no known CVEs
   
   Summary: {N} CRITICAL, {M} HIGH, {K} MEDIUM, {J} PASS
   ```

> Compact phase summary: CVE exposure enumerated with fixed versions; CRITICAL/HIGH require immediate remediation.

---

### Phase 4 — REMEDIATE

1. Compile the full remediation list:
   - All FAIL pinning issues → exact pin suggestions
   - All WARN pinning issues → exact pin suggestions (lower priority)
   - All CRITICAL/HIGH CVEs → updated version requirements
   - All version conflicts → resolution recommendation

2. Emit a ready-to-apply patch for `pyproject.toml` or `requirements.txt`:
   ```
   [REMEDIATION — apply these changes]
   
   pyproject.toml changes:
     httpx>=0.24.0      → httpx==0.27.0
     requests           → requests==2.31.0
   
   requirements.txt changes:
     anthropic==0.20.0  → anthropic==0.25.0  (resolves conflict with pyproject.toml)
   
   After applying: run `pip install -e .` and `make test-unit` to verify no breakage.
   ```

3. Emit the final verdict:
   ```
   [DEPENDENCY AUDIT VERDICT]
   Pinning:        {PASS | FAIL — N unpinned packages}
   Vulnerabilities:{PASS | FAIL — N CRITICAL/HIGH CVEs}
   Conflicts:      {PASS | FAIL — N version conflicts}
   
   OVERALL: {PASS | FAIL}
   Blockers: {list of FAIL items, or "none"}
   Recommended: {list of WARN items to address before release}
   ```

> Compact phase summary: remediation ready to apply; FAIL verdict blocks release.

---

## Quality Bars (Non-Negotiable)

- **Exact pins for all production dependencies**: `>=` and `^` are WARN in dev/test deps, FAIL in production deps. AI engineering systems that call external APIs have version-dependent behavior — exact pins are mandatory.
- **pip-audit is the authoritative CVE source**: manual CVE checks from training knowledge are incomplete and must be marked as such. If pip-audit is not installed, the audit is incomplete — say so explicitly.
- **Version conflicts are FAIL, not WARN**: two files requiring different versions of the same package will produce non-deterministic installs. This is a FAIL.
- **Remediation must be copy-pasteable**: "update requests" is not remediation. `requests==2.31.0` in the exact line format of the target file is remediation.
- **Per-server deps must be audited**: if `servers/code/requirements.txt` exists, it is audited — not just the root pyproject.toml. Server-specific deps can carry their own CVEs.

## Hiring Validation

1. **Range pin classification test**: `anthropic>=0.25.0` is in pyproject.toml. Does the skill classify this as WARN (not PASS) with suggestion `anthropic==0.25.0`? Correct: yes — range pin is reproducibility risk.
2. **Conflict detection test**: pyproject.toml has `requests>=2.28` and requirements.txt has `requests==2.20.0`. Does Phase 2 flag CONFLICT → FAIL? Correct: yes with both source lines.
3. **pip-audit absent handling test**: pip-audit is not installed. Does the skill flag "Manual CVE check is incomplete — install pip-audit" rather than silently doing a partial check? Correct: explicit incompleteness flag.
4. **Copy-pasteable remediation test**: Phase 4 output contains `requests==2.31.0` in the exact pyproject.toml format. Is it a diff-ready line, not a prose description? Correct: yes.
5. **Per-server audit test**: `servers/core/requirements.txt` exists with an unpinned package. Does the audit catch it? Correct: yes — all servers/{name}/requirements.txt are included in INVENTORY.

---

## Reference Files

| File | When to read |
|------|-------------|
| `pyproject.toml` | Phase 1 (INVENTORY) and Phase 2 (PINNING) — primary dep source |
| `requirements.txt` | Phase 1 (INVENTORY) — secondary dep source, check for conflicts |
| `servers/*/requirements.txt` | Phase 1 (INVENTORY) — per-server dependencies |

---

## Example Flows

**New dependency review before adding:**
> "we're adding 'pydantic>=2.0' to pyproject.toml — quick check first"

Invocation: `new: pydantic`
INVENTORY (current pydantic status: not present) →
PINNING (proposed: `pydantic>=2.0` → WARN: range pin; suggest `pydantic==2.7.0`) →
VULNERABILITIES (pydantic 2.7.0: no known CRITICAL/HIGH CVEs) →
Output: "Safe to add. Pin to pydantic==2.7.0 — range pin >=2.0 is a reproducibility risk."

**Pre-release full audit:**
> "run dependency audit before we tag the release"

INVENTORY (12 packages across pyproject.toml + servers/core/requirements.txt) →
PINNING (10 PASS, 1 WARN: httpx>=0.24.0, 1 FAIL: bare `click`) →
VULNERABILITIES (pip-audit run: 0 CRITICAL, 1 HIGH: click==7.1.2 CVE-2023-XXXX) →
REMEDIATE (patch: `click==8.1.7`, `httpx==0.27.0`) →
VERDICT: FAIL — 1 FAIL pinning + 1 HIGH CVE. Blockers resolved before release tag.

**CVE-only scan after security advisory:**
> "dependency-audit cve only — heard there's a new anthropic CVE"

VULNERABILITIES only (pip-audit output or manual check on anthropic=={current_version}) →
Report CVE status: PASS or FAIL with fix version
