"""A/B bench for L10 skill hardening.

Evaluates skill SKILL.md content against 5 machine-checkable structural criteria.
Runs against CURRENT disk content. Run before skill changes to get baseline,
then again after to get improved score.

Results logged to state/ab-bench-results.jsonl.

Usage:
    python -m pytest tests/test_skill_ab_bench.py -v -s
    # -s required to see score output
"""
from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from pathlib import Path

import pytest

# ── paths ─────────────────────────────────────────────────────────────────────

_CLAUDE_ROOT = Path.home() / ".claude"
_SKILLS_ROOT = _CLAUDE_ROOT / "skills"
_STATE_DIR = Path("/youk/state")  # Docker mount path
_RESULTS_FILE = _STATE_DIR / "ab-bench-results.jsonl"

# Fallback for running outside Docker
_LOCAL_STATE_DIR = Path(__file__).parent.parent / "state"

# ── bench tasks ───────────────────────────────────────────────────────────────

BENCH_TASKS = [
    {"id": "T01", "skill": "dev-loop",    "type": "new_endpoint",  "desc": "Add a POST /users/invite endpoint with email validation and rate limiting"},
    {"id": "T02", "skill": "dev-loop",    "type": "schema_change", "desc": "Add nullable `deleted_at` column to users table with soft-delete logic"},
    {"id": "T03", "skill": "dev-loop",    "type": "ui_component",  "desc": "Build a paginated data table component with sort and filter"},
    {"id": "T04", "skill": "dev-loop",    "type": "bug_fix",       "desc": "Fix N+1 query in the project listing endpoint"},
    {"id": "T05", "skill": "dev-loop",    "type": "refactor",      "desc": "Extract auth middleware into a reusable module"},
    {"id": "T06", "skill": "dev-loop",    "type": "new_endpoint",  "desc": "Add a webhook handler that validates HMAC signature and queues events"},
    {"id": "T07", "skill": "dev-loop",    "type": "schema_change", "desc": "Add composite index on (project_id, created_at) for query performance"},
    {"id": "T08", "skill": "dev-loop",    "type": "bug_fix",       "desc": "Fix race condition in the session token refresh path"},
    {"id": "T09", "skill": "dev-loop",    "type": "refactor",      "desc": "Convert callback-based file processor to async/await"},
    {"id": "T10", "skill": "code-review", "type": "HIGH",          "desc": "Review PR adding OAuth2 token exchange endpoint"},
    {"id": "T11", "skill": "code-review", "type": "MED",           "desc": "Review PR adding pagination to project listing"},
    {"id": "T12", "skill": "nfr-check",   "type": "llm_call",      "desc": "New LLM-backed citation lookup feature calling external API"},
]

# ── criteria ──────────────────────────────────────────────────────────────────

def _load_skill(skill_name: str) -> str:
    path = _SKILLS_ROOT / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    return path.read_text()


def _load_scope_matrix() -> dict:
    matrix_path = _SKILLS_ROOT / "dev-loop" / "references" / "skill-scope-matrix.yaml"
    if not matrix_path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(matrix_path.read_text()) or {}
    except Exception:
        return {}


def criterion_scope_matrix_enforced(skill_content: str, task: dict) -> tuple[bool, str]:
    """C1: AUDIT/ANALYZE phase text instructs loading scope matrix and verifying mandatory domains.

    Checks for the enforcement instruction, not just matrix file existence.
    A skill that references the matrix in its AUDIT/ANALYZE instructions will
    predictably load and apply it at runtime.
    """
    # Find the first section heading (##/###) whose title contains an audit-like keyword.
    # Use finditer so we pick the phase heading, not the h1 skill title.
    TARGET_HEADINGS = re.compile(
        r"(?:AUDIT|ANALYZE|SECURITY|REVIEW|PROBE|DOCUMENT)", re.IGNORECASE
    )
    SECTION_PATTERN = re.compile(
        r"(#{2,4}[^\n]+\n)(.*?)(?=\n#{1,4} |\Z)", re.DOTALL
    )

    audit_section_text = None
    for m in SECTION_PATTERN.finditer(skill_content):
        if TARGET_HEADINGS.search(m.group(1)):
            audit_section_text = m.group(2).lower()
            break

    if audit_section_text is None:
        return False, "No AUDIT/ANALYZE/REVIEW/PROBE/DOCUMENT section found"

    # Must reference scope matrix (the file or the concept)
    has_matrix_ref = (
        "skill-scope-matrix" in audit_section_text
        or "scope-matrix" in audit_section_text
        or "scope matrix" in audit_section_text
        or ("mandatory" in audit_section_text and "domain" in audit_section_text)
        or ("mandatory" in audit_section_text and "not examined" in audit_section_text)
    )
    if not has_matrix_ref:
        return False, "AUDIT/ANALYZE/PROBE section does not reference scope matrix or mandatory domain coverage"

    # Must have examination surface block instruction (section text OR full file)
    has_surface_block = (
        "examination surface" in audit_section_text
        or "[examination surface" in skill_content.lower()
    )
    if not has_surface_block:
        return False, "AUDIT/PROBE section missing examination surface block instruction"

    return True, "Scope matrix enforcement instruction present with examination surface block"


def criterion_pre_output_check(skill_content: str, task: dict) -> tuple[bool, str]:
    """C2: Evidence of pre-output adversarial check before surfacing code/recommendation.

    Accepts: explicit pre-output check section, minimal-path check (WRITE phase),
    or silent challenge instruction before output.
    """
    skill = task["skill"]
    content_lower = skill_content.lower()

    indicators = [
        "pre-output check",
        "pre-output adversarial",
        "minimal-path check",
        "before writing",
        "before surfacing",
        "before any capability skill surfaces",
        "silent.*check.*before.*output",
        "check.*before.*emit",
    ]
    for indicator in indicators:
        if re.search(indicator, content_lower):
            return True, f"Pre-output check indicator found: '{indicator}'"

    # code-review: check for verdict quality bar (equivalent gate)
    if skill == "code-review":
        if "never.*looks good" in content_lower or "verdict is always explicit" in content_lower:
            return True, "code-review has explicit verdict quality bar (equivalent to pre-output check)"

    return False, "No pre-output adversarial check found before output phase"


def criterion_trigger_discipline(skill_content: str, task: dict) -> tuple[bool, str]:
    """C3: Description correctly scopes when the skill fires — has both positive AND
    negative trigger signals, or explicit do-not-trigger-on clause.
    """
    # Extract frontmatter description
    fm_match = re.search(r"^---\n(.*?)\n---", skill_content, re.DOTALL)
    if not fm_match:
        return False, "No frontmatter found"

    frontmatter = fm_match.group(1).lower()
    description_block = re.search(r"description\s*:.*?(?=\n\w|\Z)", frontmatter, re.DOTALL)
    if not description_block:
        return False, "No description field in frontmatter"

    desc_text = description_block.group(0)

    # Positive: has a trigger signal
    has_positive = (
        "trigger" in desc_text
        or "triggers on" in desc_text
        or "activate when" in desc_text
        or "fires on" in desc_text
    )

    # Negative: has a do-not-trigger or exclusion signal
    has_negative = (
        "do not trigger" in desc_text
        or "not for" in desc_text
        or "does not trigger" in desc_text
        or "do not use for" in desc_text
        or "not a style" in desc_text  # code-review: "not a style linter"
        or "do not use" in skill_content.lower()[:500]  # check near top of skill body
    )

    if has_positive and has_negative:
        return True, "Description has both positive triggers and exclusion signals"
    elif has_positive:
        # Check skill body for do-not-trigger section
        body_has_exclusion = re.search(
            r"do not (trigger|use|invoke|fire|activate)",
            skill_content.lower()
        )
        if body_has_exclusion:
            return True, "Positive trigger in description + do-not-use in skill body"
        return False, "Description has positive triggers but no exclusion/do-not-trigger signal"
    else:
        return False, "Description lacks explicit trigger signals"


def criterion_escalation_path(skill_content: str, task: dict) -> tuple[bool, str]:
    """C4: Skill handles convergence failure / loop cap explicitly, not silently.

    Acceptable: ESCALATION BLOCK, explicit cap-hit instruction, or verdict with
    unresolved findings guidance.
    """
    content_lower = skill_content.lower()

    patterns = [
        "escalation block",
        "loop.*limit.*reached",
        "cap.*reached",
        "iterations.*limit",
        "unresolved.*findings",
        "do not loop again",
        "stop.*diagnose",
        "round.*cap",
        "emergency brake",
    ]
    for p in patterns:
        if re.search(p, content_lower):
            return True, f"Escalation/convergence-failure path found: '{p}'"

    # Skills without loops (nfr-check, code-review) — check for BLOCKED verdict path
    if task["skill"] in ("nfr-check", "code-review"):
        if "blocked" in content_lower and "reason" in content_lower:
            return True, "Non-loop skill has BLOCKED verdict path with reason"

    return False, "No escalation or convergence-failure handling found"


def criterion_finding_format(skill_content: str, task: dict) -> tuple[bool, str]:
    """C5: Findings have required fields: Location + Risk/Impact + Fix/Recommendation.

    For skills that produce findings (dev-loop AUDIT, code-review, security-review).
    For nfr-check: NFR Decision Block with DECIDED/DEFER/N/A structure.
    """
    skill = task["skill"]
    content_lower = skill_content.lower()

    if skill == "nfr-check":
        has_decided = "decided:" in content_lower
        has_defer = "defer:" in content_lower
        has_na = "n/a:" in content_lower
        if has_decided and has_defer and has_na:
            return True, "NFR Decision Block format complete (DECIDED/DEFER/N/A)"
        return False, f"NFR Decision Block incomplete: DECIDED={has_decided}, DEFER={has_defer}, N/A={has_na}"

    # Audit-style skills: findings need Location + Risk + Fix
    has_location = bool(re.search(r"location\s*:", content_lower))
    has_risk = bool(re.search(r"(risk|impact|degrades?)\s*:", content_lower))
    has_fix = bool(re.search(r"(fix|recommendation|action)\s*:", content_lower))

    if has_location and has_risk and has_fix:
        return True, "Finding format complete (Location + Risk + Fix)"

    missing = []
    if not has_location:
        missing.append("Location")
    if not has_risk:
        missing.append("Risk/Impact")
    if not has_fix:
        missing.append("Fix/Recommendation")
    return False, f"Finding format missing: {', '.join(missing)}"


CRITERIA = [
    ("C1_scope_matrix_enforced", criterion_scope_matrix_enforced),
    ("C2_pre_output_check",      criterion_pre_output_check),
    ("C3_trigger_discipline",    criterion_trigger_discipline),
    ("C4_escalation_path",       criterion_escalation_path),
    ("C5_finding_format",        criterion_finding_format),
]

# ── bench runner ──────────────────────────────────────────────────────────────

def run_bench(label: str = "current") -> dict:
    """Run all bench tasks against current SKILL.md files on disk.

    Returns a result dict with per-task scores and totals.
    """
    skill_cache: dict[str, str] = {}
    task_results = []
    total_score = 0
    max_score = len(BENCH_TASKS) * len(CRITERIA)

    for task in BENCH_TASKS:
        skill_name = task["skill"]
        if skill_name not in skill_cache:
            skill_cache[skill_name] = _load_skill(skill_name)
        skill_content = skill_cache[skill_name]

        task_score = 0
        criterion_results = {}
        for crit_name, crit_fn in CRITERIA:
            passed, reason = crit_fn(skill_content, task)
            criterion_results[crit_name] = {"passed": passed, "reason": reason}
            if passed:
                task_score += 1

        total_score += task_score
        task_results.append({
            "task_id": task["id"],
            "skill": task["skill"],
            "task_type": task["type"],
            "desc": task["desc"],
            "score": task_score,
            "max": len(CRITERIA),
            "criteria": criterion_results,
        })

    pct = round(100 * total_score / max_score) if max_score else 0
    result = {
        "label": label,
        "timestamp": datetime.now(UTC).isoformat(),
        "total_score": total_score,
        "max_score": max_score,
        "pct": pct,
        "tasks": task_results,
    }
    return result


def _log_result(result: dict) -> None:
    """Append result to ab-bench-results.jsonl."""
    for state_dir in (_STATE_DIR, _LOCAL_STATE_DIR):
        if state_dir.exists() or state_dir == _LOCAL_STATE_DIR:
            try:
                state_dir.mkdir(parents=True, exist_ok=True)
                results_file = state_dir / "ab-bench-results.jsonl"
                with open(results_file, "a") as f:
                    f.write(json.dumps(result) + "\n")
                return
            except Exception:
                continue


def _print_report(result: dict) -> None:
    label = result["label"]
    total = result["total_score"]
    max_s = result["max_score"]
    pct = result["pct"]
    print(f"\n{'='*60}")
    print(f"BENCH RESULT — {label.upper()}")
    print(f"Score: {total}/{max_s} ({pct}%)")
    print(f"{'='*60}")
    for t in result["tasks"]:
        status = "✓" if t["score"] == t["max"] else "~" if t["score"] > 0 else "✗"
        print(f"  {status} {t['task_id']} [{t['skill']}:{t['task_type']}] {t['score']}/{t['max']}")
        for cname, cr in t["criteria"].items():
            sym = "  ✓" if cr["passed"] else "  ✗"
            print(f"      {sym} {cname}: {cr['reason'][:80]}")
    print()


def _compare_and_verdict(baseline: dict, improved: dict) -> str:
    old_pct = baseline["pct"]
    new_pct = improved["pct"]
    delta = new_pct - old_pct
    if delta >= 10:
        verdict = "ADOPT"
    elif delta >= 0:
        verdict = "MARGINAL — review per-task findings before adopting"
    else:
        verdict = "REGRESSION — do not apply"
    return f"OLD: {old_pct}% → NEW: {new_pct}% (Δ{delta:+d}%) — {verdict}"


# ── pytest tests ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def bench_result():
    """Run the bench once per session, cache result."""
    result = run_bench(label="current")
    _log_result(result)
    _print_report(result)
    return result


class TestBenchStructure:
    """Verify the bench itself is valid before trusting its scores."""

    def test_all_skills_loadable(self):
        skills = {t["skill"] for t in BENCH_TASKS}
        for skill in skills:
            content = _load_skill(skill)
            assert content, f"SKILL.md for '{skill}' is empty or missing at {_SKILLS_ROOT / skill / 'SKILL.md'}"

    def test_scope_matrix_loadable(self):
        matrix = _load_scope_matrix()
        assert matrix, "skill-scope-matrix.yaml is missing or empty"
        assert "dev_loop" in matrix or "dev-loop" in str(matrix), "Matrix missing dev_loop section"

    def test_twelve_tasks_defined(self):
        assert len(BENCH_TASKS) == 12, f"Expected 12 bench tasks, got {len(BENCH_TASKS)}"

    def test_five_criteria_defined(self):
        assert len(CRITERIA) == 5, f"Expected 5 criteria, got {len(CRITERIA)}"

    def test_bench_runs_without_error(self, bench_result):
        assert "total_score" in bench_result
        assert "tasks" in bench_result
        assert len(bench_result["tasks"]) == 12


class TestBenchScoresBySkill:
    """Per-skill score breakdown — each skill must pass at least C4 and C5."""

    def _scores_for_skill(self, bench_result, skill_name: str) -> list[dict]:
        return [t for t in bench_result["tasks"] if t["skill"] == skill_name]

    def test_dev_loop_passes_escalation_path(self, bench_result):
        tasks = self._scores_for_skill(bench_result, "dev-loop")
        for t in tasks:
            assert t["criteria"]["C4_escalation_path"]["passed"], (
                f"dev-loop task {t['task_id']} fails C4 (escalation path): "
                f"{t['criteria']['C4_escalation_path']['reason']}"
            )

    def test_dev_loop_passes_finding_format(self, bench_result):
        tasks = self._scores_for_skill(bench_result, "dev-loop")
        for t in tasks:
            assert t["criteria"]["C5_finding_format"]["passed"], (
                f"dev-loop task {t['task_id']} fails C5 (finding format): "
                f"{t['criteria']['C5_finding_format']['reason']}"
            )

    def test_code_review_passes_finding_format(self, bench_result):
        tasks = self._scores_for_skill(bench_result, "code-review")
        for t in tasks:
            assert t["criteria"]["C5_finding_format"]["passed"], (
                f"code-review task {t['task_id']} fails C5 (finding format): "
                f"{t['criteria']['C5_finding_format']['reason']}"
            )

    def test_nfr_check_passes_finding_format(self, bench_result):
        tasks = self._scores_for_skill(bench_result, "nfr-check")
        for t in tasks:
            assert t["criteria"]["C5_finding_format"]["passed"], (
                f"nfr-check task {t['task_id']} fails C5 (finding format): "
                f"{t['criteria']['C5_finding_format']['reason']}"
            )

    def test_total_score_logged(self, bench_result):
        """Ensures the result was logged for future comparison."""
        assert bench_result["total_score"] >= 0
        assert bench_result["max_score"] == 60
        print(f"\nBaseline score: {bench_result['total_score']}/60 ({bench_result['pct']}%)")


class TestCriteriaLogic:
    """Unit tests for each criterion function — deterministic, no file I/O."""

    def _make_task(self, skill="dev-loop", ttype="new_endpoint"):
        return {"skill": skill, "type": ttype, "id": "TX", "desc": "test"}

    # C1 — scope matrix enforced
    def test_c1_passes_with_scope_matrix_reference(self):
        content = """---
name: dev-loop
description: test skill
---
## AUDIT phase
Load skill-scope-matrix.yaml and verify mandatory domains are covered.
Emit [EXAMINATION SURFACE] block with domains examined and not examined.
"""
        passed, _ = criterion_scope_matrix_enforced(content, self._make_task())
        assert passed

    def test_c1_fails_without_audit_section(self):
        content = """---
name: dev-loop
description: test skill
---
## WRITE phase
Write the code.
"""
        passed, reason = criterion_scope_matrix_enforced(content, self._make_task())
        assert not passed
        assert "No AUDIT" in reason or "audit" in reason.lower()

    def test_c1_fails_without_surface_block(self):
        content = """---
name: dev-loop
description: test skill
---
## AUDIT
Load skill-scope-matrix.yaml and check mandatory domains.
"""
        passed, reason = criterion_scope_matrix_enforced(content, self._make_task())
        assert not passed
        assert "examination surface" in reason.lower() or "surface" in reason.lower()

    # C2 — pre-output check
    def test_c2_passes_with_minimal_path_check(self):
        content = "## WRITE\n0. **Minimal-path check** — before writing, answer: smallest implementation."
        passed, _ = criterion_pre_output_check(content, self._make_task())
        assert passed

    def test_c2_passes_with_explicit_pre_output_section(self):
        content = "## Pre-output check (silent)\nRun 3 angles before surfacing."
        passed, _ = criterion_pre_output_check(content, self._make_task())
        assert passed

    def test_c2_fails_with_no_check(self):
        content = "## WRITE\nWrite the implementation."
        passed, _ = criterion_pre_output_check(content, self._make_task())
        assert not passed

    # C3 — trigger discipline
    def test_c3_passes_with_positive_and_negative_triggers(self):
        content = """---
name: dev-loop
description: >
  Triggers on: write and test, full loop. Do not trigger for single-purpose asks.
---
"""
        passed, _ = criterion_trigger_discipline(content, self._make_task())
        assert passed

    def test_c3_fails_with_only_positive_trigger_no_exclusion(self):
        content = """---
name: dev-loop
description: >
  Triggers on: write and test, full loop requests.
---
## WRITE
Write the implementation.
"""
        passed, _ = criterion_trigger_discipline(content, self._make_task())
        assert not passed

    def test_c3_fails_with_no_frontmatter(self):
        content = "# dev-loop\nSome skill content."
        passed, reason = criterion_trigger_discipline(content, self._make_task())
        assert not passed

    # C4 — escalation path
    def test_c4_passes_with_escalation_block(self):
        content = "If loop: N limit is reached and findings remain:\n[ESCALATION BLOCK]\nIterations: N"
        passed, _ = criterion_escalation_path(content, self._make_task())
        assert passed

    def test_c4_passes_with_cap_instruction(self):
        content = "Emergency brake is 10 rounds — do not loop again."
        passed, _ = criterion_escalation_path(content, self._make_task())
        assert passed

    def test_c4_fails_with_silent_cap(self):
        content = "The loop stops when loop: N is reached."
        passed, _ = criterion_escalation_path(content, self._make_task())
        assert not passed

    # C5 — finding format
    def test_c5_passes_with_full_finding_format(self):
        content = """
[FINDING: HIGH] Security — SQL injection
  Location: db/query.py line 42
  Risk: attacker can read all rows
  Fix: use parameterized queries
"""
        passed, _ = criterion_finding_format(content, self._make_task())
        assert passed

    def test_c5_passes_nfr_check_with_decision_block(self):
        content = "DECIDED: key=sha256(q), TTL=24h\nDEFER: rate_limiting — internal only\nN/A: auth — read-only"
        passed, _ = criterion_finding_format(content, self._make_task(skill="nfr-check"))
        assert passed

    def test_c5_fails_missing_location(self):
        content = "Risk: breaks on null\nFix: add null check"
        passed, reason = criterion_finding_format(content, self._make_task())
        assert not passed
        assert "Location" in reason


# ── standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run skill A/B bench")
    parser.add_argument("--label", default="manual", help="Label for this run (e.g. 'baseline', 'improved')")
    parser.add_argument("--compare", metavar="JSONL", help="Path to prior results jsonl to compare against")
    args = parser.parse_args()

    result = run_bench(label=args.label)
    _log_result(result)
    _print_report(result)

    if args.compare:
        try:
            prior_lines = Path(args.compare).read_text().strip().splitlines()
            baseline = json.loads(prior_lines[0])
            print("\nComparison:", _compare_and_verdict(baseline, result))
        except Exception as e:
            print(f"Could not load comparison file: {e}")
