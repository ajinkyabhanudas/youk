from __future__ import annotations
import re
import yaml
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import HealthReport, Proposal

CLAUDE_ROOT = Path("/claude")
YOUK_ROOT = Path("/youk")
AUDIT_DIR = CLAUDE_ROOT / "audit"
PROPOSALS_FILE = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"

# Skills that directly compound developer capability — excludes meta/session-management skills
_CAPABILITY_SKILLS = frozenset({
    "pm-review", "pm_review",
    "write-spec", "write_spec",
    "nfr-check", "nfr_check",
    "stress-test", "stress_test",
    "adr",
    "dev-loop", "dev_loop",
    "code-review", "code_review",
    "security-review", "security_review",
    "verify",
    "learn",
})

# Paths that FILE_CREATE proposals are permitted to write to
_ALLOWED_WRITE_ROOTS = [YOUK_ROOT, CLAUDE_ROOT / "skills"]


def _read_recent_audit_logs(days: int = 30) -> list[str]:
    if not AUDIT_DIR.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = []
    for f in sorted(AUDIT_DIR.glob("*.md")):
        try:
            parts = f.stem.split("-")
            if len(parts) == 2:
                file_date = datetime(int(parts[0]), int(parts[1]), 1)
                if file_date >= cutoff.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
                    entries.append(f.read_text())
        except (ValueError, IndexError):
            continue
    return entries


def _parse_audit_sessions(audit_texts: list[str]) -> list[dict]:
    """Parse structured fields from audit log entries."""
    sessions = []
    full_text = "\n".join(audit_texts)
    blocks = re.split(r"(?=### Session —)", full_text)
    for block in blocks:
        if "### Session —" not in block:
            continue
        s: dict = {"raw": block}

        skills_match = re.search(r"^Skills:\s*(.+)$", block, re.MULTILINE)
        if skills_match:
            raw_skills = skills_match.group(1).strip()
            s["skills"] = [] if raw_skills.lower() == "none" else [sk.strip() for sk in raw_skills.split(",") if sk.strip()]
        else:
            s["skills"] = []
        s["capability_skills"] = [
            sk for sk in s["skills"]
            if sk.lower().replace("-", "_") in _CAPABILITY_SKILLS or sk.lower() in _CAPABILITY_SKILLS
        ]
        close_match = re.search(r"^CloseCluster:\s*(\w+)$", block, re.MULTILINE)
        s["close_cluster"] = (close_match.group(1).lower() == "yes") if close_match else False
        # Tokens: actual/budget (pct%) or Tokens: actual (no budget set)
        tokens_match = re.search(r"^Tokens:\s*(\d+)(?:/(\d+))?", block, re.MULTILINE)
        if tokens_match:
            s["tokens_actual"] = int(tokens_match.group(1))
            s["tokens_budget"] = int(tokens_match.group(2)) if tokens_match.group(2) else 0
            s["tokens_ratio"] = (s["tokens_actual"] / s["tokens_budget"]) if s["tokens_budget"] else None
        else:
            s["tokens_actual"] = 0
            s["tokens_budget"] = 0
            s["tokens_ratio"] = None
        sessions.append(s)
    return sessions[-150:]  # cap: most recent 150 sessions regardless of window size


def _consecutive_skill_skips(sessions: list[dict]) -> int:
    """Count trailing sessions (most recent first) with zero capability skills invoked."""
    count = 0
    for s in reversed(sessions):
        if not s.get("capability_skills"):
            count += 1
        else:
            break
    return count


def _compute_gap_resolution_rate(sessions: list[dict]) -> float:
    """
    Ratio of unique gap types that appear in only one session (new) vs total unique types.
    Returns 0.5 when no gap data available (neutral signal).
    High rate = system detecting fresh gaps; low rate = same gaps recurring (not being fixed).
    """
    gap_session_count: dict[str, int] = {}
    for s in sessions:
        seen: set[str] = set()
        for line in s.get("raw", "").splitlines():
            if line.startswith("SkillGap:"):
                rest = line[len("SkillGap:"):].strip()
                if " — " in rest:
                    seen.add(rest.split(" — ", 1)[0].strip())
        for gap_type in seen:
            gap_session_count[gap_type] = gap_session_count.get(gap_type, 0) + 1

    if not gap_session_count:
        return 0.5  # neutral — no gap data yet

    unique_total = len(gap_session_count)
    recurring = sum(1 for count in gap_session_count.values() if count >= 2)
    return (unique_total - recurring) / unique_total


def _score_org(audit_texts: list[str]) -> float:
    if not audit_texts:
        return 5.0

    sessions = _parse_audit_sessions(audit_texts)
    if not sessions:
        return 5.0

    total = len(sessions)
    close_count = sum(1 for s in sessions if s["close_cluster"])
    capability_count = sum(1 for s in sessions if s.get("capability_skills"))

    close_rate = close_count / total
    capability_skill_rate = capability_count / total
    gap_resolution_rate = _compute_gap_resolution_rate(sessions)

    # Token efficiency: sessions consistently >2× budget lose 1 point
    token_sessions = [s for s in sessions if s["tokens_ratio"] is not None]
    over_budget_count = sum(1 for s in token_sessions if s["tokens_ratio"] > 2.0)
    token_penalty = -1.0 if len(token_sessions) >= 2 and over_budget_count / max(len(token_sessions), 1) > 0.5 else 0.0

    # capability_skill_rate (2.0 weight): primary signal — did developer ability compound?
    # close_rate (0.5 weight): completion bonus only — /done matters but doesn't dominate
    # gap_resolution_rate (0.5 weight): are gaps being detected as new (not recurring)?
    score = 5.0 + (capability_skill_rate * 2.0) + (close_rate * 0.5) + (gap_resolution_rate * 0.5) + token_penalty

    # Discipline gate: 3+ consecutive sessions with zero capability skills → cap at 6.5.
    # Reaching 7.0+ requires demonstrated use of capability skills, not just /done ritual.
    consecutive_skips = _consecutive_skill_skips(sessions)
    if consecutive_skips >= 3:
        score = min(score, 6.5)

    return min(round(score, 1), 10.0)


def _check_project_type_coverage() -> dict | None:
    """
    Read the project_purpose stored in session.json (set by session_start) and
    find skills expected for that project type that don't yet exist in the skills dir.

    Returns {type, description, missing: [{name, purpose}]} or None when no gaps found.
    Degrades gracefully if session.json is absent or project_purpose is unset.
    """
    import json as _json

    state_file = YOUK_ROOT / "state" / "session.json"
    if not state_file.exists():
        return None

    try:
        state = _json.loads(state_file.read_text())
    except Exception:
        return None

    purpose = state.get("project_purpose", "general")
    if not purpose or purpose == "general":
        return None

    # Import the registry from session.py at runtime to stay in sync with one source.
    # Fall back to an inline copy if import fails (Docker path issues, cold start).
    try:
        import sys
        sys.path.insert(0, str(YOUK_ROOT / "servers" / "core" / "src"))
        from session import PROJECT_PURPOSE_EXPECTED_SKILLS, _PURPOSE_DESCRIPTIONS
        expected = PROJECT_PURPOSE_EXPECTED_SKILLS.get(purpose, [])
        description = _PURPOSE_DESCRIPTIONS.get(purpose, purpose)
    except Exception:
        return None

    if not expected:
        return None

    skills_dir = CLAUDE_ROOT / "skills"
    if not skills_dir.exists():
        skills_dir = YOUK_ROOT / "skills"

    existing = {d.name for d in skills_dir.iterdir() if d.is_dir()} if skills_dir.exists() else set()
    missing = [s for s in expected if s["name"] not in existing]

    if not missing:
        return None

    return {"type": purpose, "description": description, "missing": missing}


def _audit_skill_quality(skills_dir: Path) -> list[str]:
    """
    Proactively score capability skill SKILL.md files on structural quality.
    Does not wait for SkillGap audit entries — reads SKILL.md files directly.

    Scores each skill on four signals:
    - phases: has a ## Phase / ## Step / ## Execution section
    - quality_bars: has a ## Quality Bar section
    - examples: has at least one fenced code block or ## Example section
    - references: has a references/ subdirectory with content

    WEAK = score ≤ 1 (missing 3+ signals). Surfaces at most 2 findings to avoid flooding.
    Returns [] when skills_dir does not exist (fail-safe for Docker path mismatches).
    """
    if not skills_dir.exists():
        return []

    _CAPABILITY_SKILL_NAMES = frozenset({
        "code-review", "dev-loop", "nfr-check", "security-review",
        "write-spec", "adr", "stress-test", "verify", "learn",
    })

    weak: list[str] = []
    for skill_name in sorted(_CAPABILITY_SKILL_NAMES):
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            weak.append(f"'{skill_name}' has no SKILL.md")
            continue
        try:
            content = skill_file.read_text()
        except Exception:
            continue

        lower = content.lower()
        signals = {
            "phases": any(h in lower for h in ["## phase", "## step ", "## execution", "## how to", "## implement"]),
            "quality_bars": "quality bar" in lower or "## quality" in lower,
            "examples": "## example" in lower or "```" in content,
            "references": any(
                (skills_dir / skill_name / d).exists()
                for d in ["references", "domain"]
            ),
        }
        score = sum(signals.values())
        if score <= 1:
            missing = ", ".join(k for k, v in signals.items() if not v)
            weak.append(f"'{skill_name}' (missing: {missing})")

    if not weak:
        return []
    if len(weak) == 1:
        return [f"SKILL.md quality weak: {weak[0]} — run assess_skill() to improve it."]
    return [
        f"SKILL.md quality weak in {len(weak)} capability skills: "
        f"{'; '.join(weak[:3])}"
        + (f" (+{len(weak) - 3} more)" if len(weak) > 3 else "")
        + ". Run assess_skill() on each to propose improvements."
    ]


def _generate_findings(audit_texts: list[str], score: float) -> list[str]:
    findings = []
    if not audit_texts:
        findings.append("No audit logs found — this is the first health check.")
        return findings

    sessions = _parse_audit_sessions(audit_texts)
    if not sessions:
        findings.append("Audit logs exist but contain no parseable session entries.")
        return findings

    total = len(sessions)
    close_count = sum(1 for s in sessions if s["close_cluster"])
    capability_count = sum(1 for s in sessions if s.get("capability_skills"))
    skip_rate = 1 - (close_count / total)
    capability_skip_rate = 1 - (capability_count / total)

    # Discipline gate finding — surfaces when score is capped due to capability skill absence
    consecutive_skips = _consecutive_skill_skips(sessions)
    if consecutive_skips >= 3:
        findings.append(
            f"Discipline gate LOCKED — {consecutive_skips} consecutive sessions without any capability skill "
            "(code-review, nfr-check, learn, etc.). "
            "Org score capped at 6.5. Use /build or /review to invoke a capability skill before 7.0+ is reachable."
        )

    # Capability skill invocation — north star signal
    if capability_skip_rate > 0.75:
        findings.append(
            f"Capability skills absent in {capability_skip_rate:.0%} of sessions "
            f"({capability_count}/{total} used them). "
            "No compounding of developer ability. Use /build for code tasks, "
            "/review before commits, /done (includes /learn) at session end."
        )
    elif capability_skip_rate > 0.5:
        findings.append(
            f"Capability skills used in only {capability_count}/{total} sessions ({1 - capability_skip_rate:.0%}). "
            "Aim for ≥50% of sessions invoking at least one capability skill."
        )

    if skip_rate > 0.5:
        findings.append(
            f"Session-close cluster skipped {skip_rate:.0%} of sessions "
            f"({close_count}/{total} completed)."
        )

    # Detect skills that never appear across tracked sessions
    all_skills: list[str] = []
    for s in sessions:
        all_skills.extend(s["skills"])
    skill_counts: dict[str, int] = {}
    for sk in all_skills:
        skill_counts[sk] = skill_counts.get(sk, 0) + 1

    if total >= 5:
        _CORE_CAPABILITY_SKILLS = frozenset({
            "code-review", "verify", "nfr-check", "learn", "dev-loop",
            "security-review", "write-spec", "adr",
        })
        skills_used_normalized = {s.lower().replace("_", "-") for s in all_skills}
        dormant = sorted(
            s for s in _CORE_CAPABILITY_SKILLS
            if s not in skills_used_normalized
            and s.replace("-", "_") not in skills_used_normalized
        )
        if dormant:
            if len(dormant) <= 2:
                for s in dormant:
                    findings.append(f"Skill '{s}' not recorded in any of {total} sessions.")
            else:
                findings.append(
                    f"{len(dormant)} capability skills never invoked across {total} sessions: "
                    f"{', '.join(dormant[:5])}. "
                    "Run /build, /review, or /done (includes /learn) to activate them."
                )

    # Proactive SKILL.md quality audit — does not wait for explicit SkillGap log entries.
    # Reads SKILL.md files directly and surfaces structurally weak skills.
    skill_quality_findings = _audit_skill_quality(CLAUDE_ROOT / "skills")
    findings.extend(skill_quality_findings[:2])

    if score < 6.0:
        findings.append("Org score below 6.0 — review which skills are being skipped.")

    # Token efficiency findings
    token_sessions = [s for s in sessions if s["tokens_ratio"] is not None]
    if token_sessions:
        avg_ratio = sum(s["tokens_ratio"] for s in token_sessions) / len(token_sessions)
        over_budget = [s for s in token_sessions if s["tokens_ratio"] > 2.0]
        if len(over_budget) >= 2:
            findings.append(
                f"Token usage consistently {avg_ratio:.1f}× over budget "
                f"({len(over_budget)}/{len(token_sessions)} sessions). "
                "Consider adding headroom (github.com/headroomlabs-ai/headroom) "
                "for 60-95% token cost reduction."
            )
        elif avg_ratio < 0.5 and len(token_sessions) >= 3:
            findings.append(
                f"Token usage consistently under budget ({avg_ratio:.1f}× avg). "
                "Verify skills are running — under-ceremony on M+ tasks is a risk."
            )
    elif total >= 3:
        findings.append(
            f"No token data in {total} sessions. "
            "Call track_tokens(input, output, note) at session checkpoints to enable cost tracking."
        )

    # Self-evolution loop health: flag when PENDING.md and audit SkillGaps are both empty
    pending_count = PROPOSALS_FILE.read_text().count("## PENDING-") if PROPOSALS_FILE.exists() else 0
    skill_gap_count = sum(text.count("SkillGap:") for text in audit_texts)
    if total >= 3 and pending_count == 0 and skill_gap_count == 0:
        findings.append(
            f"Self-evolution loop is starved: 0 proposals in PENDING.md, "
            f"0 SkillGap entries across {total} sessions. "
            "Run simulate-experience to seed proposals, or end sessions with "
            "session_end(skill_gaps=...) to start feeding the loop."
        )

    # Project type coverage: surface missing skills for the detected project type
    coverage_gap = _check_project_type_coverage()
    if coverage_gap:
        missing_names = ", ".join(s["name"] for s in coverage_gap["missing"])
        findings.append(
            f"Project type '{coverage_gap['description']}' has {len(coverage_gap['missing'])} "
            f"skill(s) missing for this type: {missing_names}. "
            "Run /audit to confirm and generate them."
        )

    # Contract capture health: flag when active project has many sessions but no contracts
    # This catches the silent failure where contracts were verbalized but never persisted
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if total >= 5 and projects_dir.exists():
        for proj in projects_dir.iterdir():
            contracts_file = proj / "contracts.md"
            has_contracts = (
                contracts_file.exists()
                and any(
                    line.strip().startswith("- ")
                    for line in contracts_file.read_text().splitlines()
                )
            )
            if not has_contracts:
                findings.append(
                    f"Project '{proj.name}' has {total} sessions but no contracts in contracts.md. "
                    "Working agreements stated in conversation are not surviving compaction. "
                    "Call save_contract(agreement, cwd) the moment a contract is verbalized — "
                    "do not wait for /done."
                )
                break  # one finding is enough — same root cause

    if not findings:
        findings.append(f"Org health nominal. Score: {score}/10.")

    return findings


def _load_pending_proposals() -> list[Proposal]:
    if not PROPOSALS_FILE.exists():
        return []

    content = PROPOSALS_FILE.read_text()
    proposals = []
    blocks = content.split("## PENDING-")

    for block in blocks[1:]:
        lines = block.strip().split("\n")
        proposal_id = "PENDING-" + lines[0].split("—")[0].strip()
        date = lines[0].split("—")[-1].strip() if "—" in lines[0] else "unknown"

        proposals.append(Proposal(
            id=proposal_id,
            target=_extract_field(block, "Target"),
            change_description=_extract_field(block, "Change"),
            reason=_extract_field(block, "Reason"),
            before=_extract_field(block, "Before"),
            after=_extract_field(block, "After"),
            status=_extract_field(block, "Status"),
            proposed_date=date,
            change_type=_extract_field(block, "ChangeType"),
            target_section=_extract_field(block, "TargetSection"),
            content=_extract_content_block(block),
        ))
    return proposals


def _extract_field(text: str, field_name: str) -> str:
    pattern = rf"\*\*{field_name}:\*\*\s*(.+)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _extract_content_block(text: str) -> str:
    """Extract fenced code block after **Content:**."""
    match = re.search(r"\*\*Content:\*\*\s*\n```\n(.*?)\n```", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _parse_skill_gap_signals(audit_texts: list[str]) -> list[dict]:
    """Aggregate SkillGap: lines from audit into per-skill gap signal counts."""
    raw: dict[str, list[str]] = {}
    for text in audit_texts:
        for line in text.splitlines():
            if line.startswith("SkillGap:"):
                rest = line[len("SkillGap:"):].strip()
                if " — " in rest:
                    skill, gap = rest.split(" — ", 1)
                    raw.setdefault(skill.strip(), []).append(gap.strip())
    return [
        {"skill": s, "gaps": gaps, "count": len(gaps)}
        for s, gaps in sorted(raw.items(), key=lambda x: -len(x[1]))
    ]


def run_health_check() -> HealthReport:
    audit_texts = _read_recent_audit_logs(days=30)
    score = _score_org(audit_texts)
    findings = _generate_findings(audit_texts, score)
    proposals = _load_pending_proposals()

    return HealthReport(
        org_score=score,
        sessions_analyzed=sum(t.count("### Session —") for t in audit_texts),
        findings=findings,
        proposals=proposals,
    )


def _analyze_promotion_candidates(audit_texts: list[str]) -> list[dict]:
    """
    Scan SkillGap: lines across all audit sessions.
    A gap appearing 3+ times for the same skill → propose a SKILL_EDIT.
    A gap appearing across 2+ distinct projects → flag for cross-project.md addition.
    Returns a list of candidates; callers queue them as proposals (never auto-apply).
    """
    from collections import defaultdict

    # Extract (project_slug, skill, gap_description) tuples from audit blocks
    gap_records: list[tuple[str, str, str]] = []
    for text in audit_texts:
        current_slug = ""
        for line in text.splitlines():
            if line.startswith("### Session —"):
                current_slug = ""  # reset; project slug not directly in session header
            if "Project:" in line or "project:" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    current_slug = parts[1].strip().split()[0]
            if line.startswith("SkillGap:"):
                rest = line[len("SkillGap:"):].strip()
                if " — " in rest:
                    skill, gap = rest.split(" — ", 1)
                    gap_records.append((current_slug, skill.strip(), gap.strip()))

    # Group by skill
    by_skill: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for slug, skill, gap in gap_records:
        by_skill[skill].append((slug, gap))

    _CODE_SIGNALS = (".py", ".sh", "def ", "()", "function", "session_start", "route_task",
                     "session.py", "health.py", "routing.py", "compaction.py")

    candidates = []
    for skill, occurrences in by_skill.items():
        count = len(occurrences)
        projects = {slug for slug, _ in occurrences if slug}
        if count >= 3:
            # Detect code-level gaps: gap text mentions source files or function names
            all_gap_text = " ".join(gap for _, gap in occurrences).lower()
            is_code_gap = any(sig in all_gap_text for sig in _CODE_SIGNALS)
            if is_code_gap:
                change_type = "CODE_EDIT"
                promotion_target = f"servers/core/src/{skill}.py"
            elif len(projects) >= 2:
                change_type = "FILE_CREATE"
                promotion_target = "cross-project.md"
            else:
                change_type = "SKILL_EDIT"
                promotion_target = f"skills/{skill}/SKILL.md"
            candidates.append({
                "skill": skill,
                "occurrence_count": count,
                "distinct_projects": len(projects),
                "sample_gaps": list({gap for _, gap in occurrences})[:3],
                "promotion_target": promotion_target,
                "change_type": change_type,
            })
    return sorted(candidates, key=lambda x: -x["occurrence_count"])


def _queue_promotion_proposals(candidates: list[dict]) -> int:
    """Auto-queue proposals for promotion candidates. Returns count queued."""
    from datetime import datetime
    queued = 0
    for c in candidates:
        is_code_edit = c["change_type"] == "CODE_EDIT"
        proposal = Proposal(
            id=f"PENDING-PROMO-{c['skill'].upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            target=c["promotion_target"],
            change_description=f"Promote recurring gap pattern: {c['skill']} ({c['occurrence_count']} occurrences across {c['distinct_projects']} project(s))",
            reason=(
                f"SkillGap '{c['skill']}' appeared {c['occurrence_count']} times in audit logs. "
                f"Sample gaps: {'; '.join(c['sample_gaps'])}. "
                + (
                    "Code-level gap detected — set target_section to the function name and synthesize content before apply_proposal(confirmed=True)."
                    if is_code_edit else
                    "Review and expand the skill or add to cross-project.md."
                )
            ),
            before="",
            after="",
            status="PENDING",
            proposed_date=datetime.utcnow().strftime("%Y-%m-%d"),
            change_type=c["change_type"],
            target_section="",
            content="",
        )
        try:
            add_proposal(proposal)
            queued += 1
        except Exception:
            pass
    return queued


def _compute_improvement_velocity(audit_texts: list[str], current_score: float) -> dict:
    """
    Measure whether youk is getting better each health cycle.

    North star: "youk should figure out what it needs to improve and build further."
    This metric answers: is the self-improvement loop actually running and converging?

    Returns a dict with:
    - org_score_history: last 5 org_score values (oldest → newest)
    - velocity: current_score - previous_score (+ = improving, - = regressing)
    - proposals_applied_total: count of APPLIED entries in PENDING.md (work completed)
    - gaps_detected_last30: SkillGap count from last 30 days (awareness signal)
    - close_cluster_rate: pct of sessions that called /done (loop closure rate)
    - evolution_loop_active: True when gaps are detected AND proposals exist
    - loop_verdict: one-line summary of loop health
    """
    full_text = "\n".join(audit_texts)

    # Parse historical org_scores from audit entries ("Org score: X/10")
    hist_matches = re.findall(r"Org score:\s*([\d.]+)/10", full_text)
    score_history = [float(s) for s in hist_matches]
    score_history.append(current_score)  # include current
    score_history = score_history[-5:]  # keep last 5

    velocity = round(current_score - score_history[-2], 1) if len(score_history) >= 2 else 0.0

    # Count APPLIED proposals (completed improvement work)
    proposals_applied = 0
    if PROPOSALS_FILE.exists():
        for line in PROPOSALS_FILE.read_text().splitlines():
            if "**Status:** APPLIED" in line:
                proposals_applied += 1

    # Count SkillGaps in last 30 days (awareness — system is detecting issues)
    gaps_last30 = full_text.count("SkillGap:")

    # Close-cluster rate (loop-closure — sessions that fully closed)
    sessions = _parse_audit_sessions(audit_texts)
    total = len(sessions)
    close_count = sum(1 for s in sessions if s["close_cluster"])
    close_rate = round(close_count / total, 2) if total else 0.0

    # Loop health verdict
    evolution_active = gaps_last30 > 0 or proposals_applied > 0
    if close_rate == 0.0:
        verdict = "STALLED — /done never fires; audit data is thin; loop is not closing"
    elif velocity > 0:
        verdict = f"IMPROVING — org_score +{velocity} from last cycle"
    elif velocity < 0:
        verdict = f"REGRESSING — org_score {velocity} from last cycle; review skipped skills"
    elif evolution_active:
        verdict = "STEADY — no score change this cycle; gaps being logged, proposals building"
    else:
        verdict = "COLD — no gaps, no proposals; loop starved"

    # Persist metrics for dashboard trend view
    metrics_file = YOUK_ROOT / "state" / "improvement-metrics.json"
    try:
        import json
        existing_entries = []
        if metrics_file.exists():
            try:
                existing_entries = json.loads(metrics_file.read_text()).get("entries", [])
            except Exception:
                pass
        entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "org_score": current_score,
            "velocity": velocity,
            "proposals_applied": proposals_applied,
            "gaps_last30": gaps_last30,
            "close_cluster_rate": close_rate,
        }
        existing_entries.append(entry)
        existing_entries = existing_entries[-20:]  # keep last 20 health cycles

        # Per-project org_score: read current slug from state, store under "projects" key.
        # Enables session_start to surface "canopy: 7.0/10 ▲+0.1" vs system-wide score.
        existing_data = {}
        if metrics_file.exists():
            try:
                existing_data = json.loads(metrics_file.read_text())
            except Exception:
                pass
        per_project = existing_data.get("projects", {})
        state_file = YOUK_ROOT / "state" / "session.json"
        if state_file.exists():
            try:
                slug = json.loads(state_file.read_text()).get("last_project", "")
                if slug:
                    per_project[slug] = {
                        "org_score": current_score,
                        "sessions": total,
                        "close_rate": close_rate,
                        "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
            except Exception:
                pass

        metrics_file.parent.mkdir(parents=True, exist_ok=True)
        metrics_file.write_text(json.dumps(
            {"entries": existing_entries, "projects": per_project}, indent=2
        ))
    except Exception:
        pass

    return {
        "org_score_history": score_history,
        "velocity": velocity,
        "proposals_applied_total": proposals_applied,
        "gaps_detected_last30": gaps_last30,
        "close_cluster_rate": close_rate,
        "evolution_loop_active": evolution_active,
        "loop_verdict": verdict,
    }


def run_health_check_with_skill_signals(research_mode: bool = False) -> dict:
    """
    Extended health check that also returns skill gap signals for evolution
    and queues promotion proposals for skills with 3+ recurring gap occurrences.

    research_mode: when True, surfaces suggested research topics for each gap signal
    so the caller can invoke youk-research with targeted queries. Does not perform
    web research itself — keeps this function on the zero-API hot path.
    """
    _archive_applied_proposals()
    report = run_health_check()
    audit_texts = _read_recent_audit_logs(days=30)
    skill_gap_signals = _parse_skill_gap_signals(audit_texts)
    velocity = _compute_improvement_velocity(audit_texts, report.org_score)

    # Auto-queue proposals for skills that have crossed the promotion threshold
    promotion_candidates = _analyze_promotion_candidates(audit_texts)
    promotion_queued = _queue_promotion_proposals(promotion_candidates) if promotion_candidates else 0

    base = {
        "org_score": report.org_score,
        "sessions_analyzed": report.sessions_analyzed,
        "findings": report.findings,
        "proposals": [p.to_dict() for p in report.proposals],
        "proposals_count": len(report.proposals),
        "improvement_velocity": velocity,
    }

    if skill_gap_signals:
        base["skill_gap_signals"] = skill_gap_signals
        base["skill_evolution_note"] = (
            "Skills with recurring gap signals detected. "
            "Call youk-code.assess_skill(skill_name) for each, then add_proposal() "
            "with the returned proposed_additions."
        )

    if promotion_queued:
        base["promotion_proposals_queued"] = promotion_queued
        base["promotion_note"] = (
            f"{promotion_queued} skill(s) crossed the 3-occurrence threshold — "
            "proposals queued in PENDING.md for review."
        )

    # Project type coverage gaps — skills that should exist for this project type but don't
    coverage_gap = _check_project_type_coverage()
    if coverage_gap:
        base["project_type"] = coverage_gap["type"]
        base["project_type_description"] = coverage_gap["description"]
        base["coverage_gaps"] = coverage_gap["missing"]
        base["coverage_note"] = (
            f"Project type '{coverage_gap['description']}' is missing "
            f"{len(coverage_gap['missing'])} skill(s). "
            "Call youk-code.generate_skill(name, purpose, context, signal_type) for each, "
            "then add_proposal() + apply_proposal(confirmed=True, safe_types=['FILE_CREATE'])."
        )

    # Cross-project pattern detection — surface global intelligence candidates
    cross_project_candidates = _detect_cross_project_patterns(min_projects=2)
    if cross_project_candidates:
        base["global_pattern_candidates"] = cross_project_candidates[:5]  # top 5 only
        base["global_pattern_note"] = (
            f"{len(cross_project_candidates)} contract(s) found across 2+ projects. "
            "These may belong in your global intelligence layer (knowledge/global/contracts.md). "
            "Confirm promotion via: promote_to_global_contracts(contract_text)."
        )

    # Global contracts store health — surface when review or pruning is needed
    global_audit = _audit_global_contracts()
    if global_audit["auto_promoted"] > 0:
        base["global_contracts_pending_review"] = (
            f"{global_audit['auto_promoted']} auto-promoted global contracts need review "
            f"(total: {global_audit['total']}, session loads last 50). "
            "Open knowledge/global/contracts.md to confirm or prune."
        )
    if global_audit["total"] > 100:
        base["global_contracts_oversize"] = (
            f"knowledge/global/contracts.md has {global_audit['total']} entries — "
            "only 50 load per session. Consider pruning stale entries."
        )

    if research_mode and skill_gap_signals:
        # Derive search topics from gap descriptions — one topic per top gap signal.
        # These are passed back to the caller to feed into youk-research.
        # No web calls here — this function stays zero-API.
        research_topics = []
        for signal in skill_gap_signals[:3]:
            skill = signal.get("skill", "")
            gaps = signal.get("gaps", [])
            if gaps:
                topic = f"{skill}: {gaps[0]}"
                research_topics.append(topic[:80])
        if research_topics:
            base["research_topics"] = research_topics
            base["research_note"] = (
                "Run /research on these topics to find external solutions: "
                + "; ".join(research_topics)
            )

    return base


def _archive_applied_proposals() -> int:
    """Move APPLIED/SUPERSEDED proposal blocks from PENDING.md to APPLIED-ARCHIVE.md.
    Returns count of blocks archived. Called at start of each health check."""
    if not PROPOSALS_FILE.exists():
        return 0
    content = PROPOSALS_FILE.read_text()
    parts = content.split("\n## ")
    header = parts[0]
    active, archived = [], []
    for block in parts[1:]:
        status_line = next((ln for ln in block.splitlines() if "**Status:**" in ln), "")
        if "APPLIED" in status_line or "SUPERSEDED" in status_line:
            archived.append("## " + block)
        else:
            active.append("## " + block)
    if not archived:
        return 0
    PROPOSALS_FILE.write_text(header + ("\n" if active else "") + "".join(active))
    archive_file = PROPOSALS_FILE.parent / "APPLIED-ARCHIVE.md"
    with open(archive_file, "a") as f:
        f.write("".join(archived))
    return len(archived)


def _audit_global_contracts() -> dict:
    """Return count of total, auto-promoted, and manually confirmed global contracts."""
    global_file = YOUK_ROOT / "knowledge" / "global" / "contracts.md"
    if not global_file.exists():
        return {"total": 0, "auto_promoted": 0, "confirmed": 0}
    lines = [
        ln.strip() for ln in global_file.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    auto = sum(1 for ln in lines if "[auto-promoted]" in ln)
    return {"total": len(lines), "auto_promoted": auto, "confirmed": len(lines) - auto}


def _detect_cross_project_patterns(min_projects: int = 2) -> list[dict]:
    """Scan all project contracts.md files and find contracts recurring across projects.
    Returns candidates: [{contract, projects: [slug, ...], count}] sorted by count desc."""
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if not projects_dir.exists():
        return []

    # Collect contracts per project
    project_contracts: dict[str, list[str]] = {}
    for project_dir in projects_dir.iterdir():
        contracts_file = project_dir / "contracts.md"
        if not contracts_file.is_file():
            continue
        lines = [
            line.strip().lstrip("- ").lower()
            for line in contracts_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if lines:
            project_contracts[project_dir.name] = lines

    if len(project_contracts) < min_projects:
        return []

    # Find contracts appearing in min_projects or more distinct projects
    contract_to_projects: dict[str, list[str]] = {}
    for slug, contracts in project_contracts.items():
        for c in contracts:
            contract_to_projects.setdefault(c, [])
            if slug not in contract_to_projects[c]:
                contract_to_projects[c].append(slug)

    candidates = [
        {"contract": c, "projects": slugs, "count": len(slugs)}
        for c, slugs in contract_to_projects.items()
        if len(slugs) >= min_projects
    ]
    return sorted(candidates, key=lambda x: x["count"], reverse=True)


def add_proposal(proposal: Proposal) -> None:
    """Append a new proposal to PENDING.md. Never auto-applies. Deduplicates by change_description."""
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not PROPOSALS_FILE.exists():
        PROPOSALS_FILE.write_text("# youk Self-Heal Proposals\n\nPending founder review.\n\n")
    else:
        existing = PROPOSALS_FILE.read_text()
        if proposal.change_description and proposal.change_description in existing:
            return  # already queued — don't append a duplicate

    with open(PROPOSALS_FILE, "a") as f:
        f.write("\n" + proposal.to_markdown())


def _compute_diff_preview(proposal: Proposal) -> dict:
    """Return preview of what apply_proposal would write. Nothing touches disk."""
    ct = proposal.change_type
    target_path = Path(proposal.target)

    if ct == "FILE_CREATE":
        exists = target_path.exists()
        before = target_path.read_text() if exists else "(file does not exist)"
        after = proposal.content
        return {
            "target": str(target_path),
            "change_type": ct,
            "before": before[:500] + "..." if len(before) > 500 else before,
            "after": after[:500] + "..." if len(after) > 500 else after,
            "diff_lines": len(after.splitlines()) - len(before.splitlines()),
        }

    if ct == "REFERENCE_ADD":
        ref_path = CLAUDE_ROOT / "skills" / proposal.target / "references" / proposal.target_section
        before = ref_path.read_text() if ref_path.exists() else "(file does not exist)"
        after = proposal.content
        return {
            "target": str(ref_path),
            "change_type": ct,
            "before": before[:300] + "..." if len(before) > 300 else before,
            "after": after[:300] + "..." if len(after) > 300 else after,
            "diff_lines": len(after.splitlines()),
        }

    if ct == "SKILL_EDIT":
        skill_path = CLAUDE_ROOT / "skills" / proposal.target / "SKILL.md"
        if not skill_path.exists():
            return {"error": f"SKILL.md not found at {skill_path}"}
        current = skill_path.read_text()
        section = proposal.target_section
        pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
        match = re.search(pattern, current, re.DOTALL)
        before = match.group(0) if match else "(section not found)"
        after = f"## {section}\n{proposal.content}"
        return {
            "target": str(skill_path),
            "change_type": ct,
            "section": section,
            "before": before[:400] + "..." if len(before) > 400 else before,
            "after": after[:400] + "..." if len(after) > 400 else after,
            "diff_lines": len(after.splitlines()) - (len(before.splitlines()) if match else 0),
        }

    if ct == "CONFIG_EDIT":
        config_path = YOUK_ROOT / "config" / proposal.target
        if not config_path.exists():
            return {"error": f"Config not found: {config_path}"}
        before = config_path.read_text()
        return {
            "target": str(config_path),
            "change_type": ct,
            "before": before[:400] + "..." if len(before) > 400 else before,
            "after": f"(yaml fragment to merge)\n{proposal.content}",
            "diff_lines": len(proposal.content.splitlines()),
        }

    if ct == "CODE_EDIT":
        code_path = YOUK_ROOT / proposal.target
        if not code_path.exists():
            return {"error": f"File not found: {code_path}"}
        current = code_path.read_text()
        section = proposal.target_section
        match = None
        if section:
            pattern = rf"^def {re.escape(section)}\b.*?(?=^def |\nclass |\Z)"
            match = re.search(pattern, current, re.DOTALL | re.MULTILINE)
            before = match.group(0) if match else "(function not found)"
        else:
            before = current[:400] + ("..." if len(current) > 400 else "")
        after = proposal.content if proposal.content else "(content not yet set — synthesize replacement function first)"
        before_trunc = before[:500] + "..." if len(before) > 500 else before
        after_trunc = after[:500] + "..." if len(after) > 500 else after
        return {
            "target": str(code_path),
            "change_type": ct,
            "section": section,
            "before": before_trunc,
            "after": after_trunc,
            "diff_lines": len(after.splitlines()) - (len(before.splitlines()) if match else 0),
        }

    return {
        "target": proposal.target,
        "change_type": ct or "UNKNOWN",
        "note": "No change_type set — preview unavailable. Set change_type in the proposal.",
    }


def _execute_proposal(proposal: Proposal) -> dict:
    """Write the proposal to disk. Called only when confirmed=True."""
    ct = proposal.change_type

    if ct == "FILE_CREATE":
        target_path = Path(proposal.target)
        allowed = any(
            str(target_path).startswith(str(r)) for r in _ALLOWED_WRITE_ROOTS
        )
        if not allowed:
            return {
                "applied": False,
                "error": f"FILE_CREATE blocked: {target_path} is outside permitted write roots.",
            }
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(proposal.content)
        return {"applied": True, "target_file": str(target_path), "change_type": ct}

    if ct == "REFERENCE_ADD":
        ref_path = CLAUDE_ROOT / "skills" / proposal.target / "references" / proposal.target_section
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(proposal.content)
        return {"applied": True, "target_file": str(ref_path), "change_type": ct}

    if ct == "SKILL_EDIT":
        skill_path = CLAUDE_ROOT / "skills" / proposal.target / "SKILL.md"
        if not skill_path.exists():
            return {"applied": False, "error": f"SKILL.md not found at {skill_path}"}
        current = skill_path.read_text()
        section = proposal.target_section
        pattern = rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)"
        replacement = f"## {section}\n{proposal.content}"
        new_content, count = re.subn(pattern, replacement, current, flags=re.DOTALL)
        if count == 0:
            new_content = current.rstrip() + f"\n\n## {section}\n{proposal.content}\n"
        skill_path.write_text(new_content)
        return {"applied": True, "target_file": str(skill_path), "change_type": ct, "section": section}

    if ct == "CONFIG_EDIT":
        config_path = YOUK_ROOT / "config" / proposal.target
        if not config_path.exists():
            return {"applied": False, "error": f"Config not found: {config_path}"}
        try:
            existing = yaml.safe_load(config_path.read_text()) or {}
            patch = yaml.safe_load(proposal.content) or {}
            existing.update(patch)
            config_path.write_text(yaml.dump(existing, default_flow_style=False))
            return {"applied": True, "target_file": str(config_path), "change_type": ct}
        except yaml.YAMLError as e:
            return {"applied": False, "error": f"YAML parse error: {e}"}

    if ct == "CODE_EDIT":
        # Restricted to YOUK_ROOT only — SKILL_EDIT handles skills/, CONFIG_EDIT handles config/
        code_path = YOUK_ROOT / proposal.target
        if not str(code_path).startswith(str(YOUK_ROOT)):
            return {"applied": False, "error": f"CODE_EDIT blocked: {code_path} is outside YOUK_ROOT."}
        if not code_path.exists():
            return {"applied": False, "error": f"File not found: {code_path}"}
        if not proposal.content:
            return {"applied": False, "error": "CODE_EDIT requires content — synthesize replacement function before applying."}
        section = proposal.target_section
        if not section:
            return {"applied": False, "error": "CODE_EDIT requires target_section (function name to replace)."}
        current = code_path.read_text()
        pattern = rf"^def {re.escape(section)}\b.*?(?=^def |\nclass |\Z)"
        replacement = proposal.content.rstrip() + "\n"
        new_content, count = re.subn(pattern, replacement, current, flags=re.DOTALL | re.MULTILINE)
        if count == 0:
            return {"applied": False, "error": f"Function '{section}' not found in {code_path}"}
        code_path.write_text(new_content)
        return {"applied": True, "target_file": str(code_path), "change_type": ct, "section": section}

    return {
        "applied": False,
        "error": f"Unknown change_type '{ct}'. Set a valid change_type on the proposal.",
    }


def apply_proposal(
    proposal_id: str,
    confirmed: bool,
    safe_types: list[str] | None = None,
) -> dict:
    """
    Two-step proposal application with optional change_type gate.

    confirmed=False → returns diff preview, nothing written.
    confirmed=True  → executes write per change_type, marks APPLIED in PENDING.md.

    safe_types: when provided, only change_types in this list are applied.
    Types not in safe_types return blocked=True — caller must review manually.
    Use safe_types=["SKILL_EDIT","FILE_CREATE"] for autonomous /improve runs.
    """
    proposals = _load_pending_proposals()
    target = next((p for p in proposals if p.id == proposal_id), None)
    if not target:
        return {"applied": False, "error": f"Proposal {proposal_id} not found in PENDING.md"}

    if not confirmed:
        preview = _compute_diff_preview(target)
        return {
            "preview": preview,
            "blocked": True,
            "message": "Preview only — nothing written. Pass confirmed=True to apply.",
        }

    # change_type gate — enforces safe_types contract for autonomous callers
    if safe_types is not None and target.change_type not in safe_types:
        return {
            "applied": False,
            "blocked": True,
            "proposal_id": proposal_id,
            "change_type": target.change_type,
            "safe_types": safe_types,
            "message": (
                f"Proposal {proposal_id} is change_type='{target.change_type}' which is not in "
                f"safe_types={safe_types}. This requires manual review. "
                "Call apply_proposal without safe_types to apply explicitly after reviewing."
            ),
        }

    # confirmed=True path: execute + mark applied
    result = _execute_proposal(target)
    if result.get("applied"):
        content = PROPOSALS_FILE.read_text()
        content = content.replace(
            f"**Status:** {target.status}",
            f"**Status:** APPLIED — {datetime.utcnow().strftime('%Y-%m-%d')}",
            1,
        )
        PROPOSALS_FILE.write_text(content)
        result["change_summary"] = target.change_description

    return result
