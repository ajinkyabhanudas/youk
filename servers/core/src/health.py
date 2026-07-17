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


def _read_forge_run() -> dict | None:
    """Return the skill-forge run summary from state, or None. Written by skill-forge."""
    forge_file = YOUK_ROOT / "state" / "skill-forge-run.json"
    if not forge_file.exists():
        return None
    try:
        import json as _json
        return _json.loads(forge_file.read_text())
    except Exception:
        return None


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
        # DeveloperCaught: skills pre-empted by the developer count toward capability_skills.
        # A developer who answered nfr_check questions unprompted exercised the capability —
        # the audit should credit it even if route_to_skill("nfr_check") was never called.
        caught_early = re.search(r"^DeveloperCaught:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
        if caught_early:
            existing_normalized = {c.lower().replace("-", "_") for c in s["capability_skills"]}
            for sk in caught_early.group(1).split(","):
                sk = sk.strip()
                if sk and (sk.lower().replace("-", "_") in _CAPABILITY_SKILLS or sk.lower() in _CAPABILITY_SKILLS):
                    if sk.lower().replace("-", "_") not in existing_normalized:
                        s["capability_skills"].append(sk)
                        existing_normalized.add(sk.lower().replace("-", "_"))
        # TaskCheckpoints M+: tool-enforced evidence that M+ routing ran (check_challenge_gate
        # passed, task_checkpoint called). Credit dev-loop even if route_to_skill("dev-loop")
        # was skipped — the gate ran, the work happened.
        if re.search(r"^TaskCheckpoints:\s*\d+.*\((XL|L|M)\)", block, re.MULTILINE | re.IGNORECASE):
            if "dev-loop" not in s["capability_skills"] and "dev_loop" not in s["capability_skills"]:
                s["capability_skills"].append("dev-loop")
        close_match = re.search(r"^CloseCluster:\s*(\w+)$", block, re.MULTILINE)
        s["close_cluster"] = (close_match.group(1).lower() == "yes") if close_match else False
        project_match = re.search(r"^Project:\s*(.+)$", block, re.MULTILINE)
        s["project"] = project_match.group(1).strip() if project_match else ""
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

        # Outcome quality fields
        findings_match = re.search(r"^Findings:\s*(\d+)(.*)?$", block, re.MULTILINE)
        if findings_match:
            s["findings_total"] = int(findings_match.group(1))
            critical_match = re.search(r"CRITICAL=(\d+)", findings_match.group(2) or "")
            high_match = re.search(r"HIGH=(\d+)", findings_match.group(2) or "")
            s["findings_critical"] = int(critical_match.group(1)) if critical_match else 0
            s["findings_high"] = int(high_match.group(1)) if high_match else 0
        else:
            s["findings_total"] = 0
            s["findings_critical"] = 0
            s["findings_high"] = 0

        categories_match = re.search(r"^FindingCategories:\s*(.+)$", block, re.MULTILINE)
        s["finding_categories"] = (
            [c.strip() for c in categories_match.group(1).split(",") if c.strip()]
            if categories_match else []
        )

        nfr_gaps = re.findall(r"^NFRGap:\s*(.+)$", block, re.MULTILINE)
        s["nfr_gaps"] = [g.strip() for g in nfr_gaps]

        reversal_match = re.search(r"^DirectionReversal:\s*yes$", block, re.MULTILINE | re.IGNORECASE)
        s["direction_reversal"] = bool(reversal_match)

        # FramingCorrect: yes/no — written by session_end when direction_reversal is False/True.
        # Absent = not yet tracked (treated as correct to avoid penalising old sessions).
        framing_match = re.search(r"^FramingCorrect:\s*(\w+)$", block, re.MULTILINE | re.IGNORECASE)
        if framing_match:
            s["framing_correct"] = framing_match.group(1).lower() == "yes"
        else:
            s["framing_correct"] = None  # unknown — old audit entry predates this signal

        # DeveloperCaught: skills the developer pre-empted by answering unprompted.
        # Rising presence across sessions = compounding loop working.
        caught_match = re.search(r"^DeveloperCaught:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
        if caught_match:
            s["developer_caught"] = [c.strip() for c in caught_match.group(1).split(",") if c.strip()]
        else:
            s["developer_caught"] = []

        # Loop-dry tracking — measures run-until-dry behavioral DNA health.
        s["loop_correction"] = bool(re.search(r"^LoopCorrection:\s*yes$", block, re.MULTILINE | re.IGNORECASE))
        s["loop_gap"] = bool(re.search(r"^LoopGap:\s*yes$", block, re.MULTILINE | re.IGNORECASE))
        rounds_match = re.search(r"^ChallengeRounds:\s*(\d+)$", block, re.MULTILINE)
        s["challenge_rounds"] = int(rounds_match.group(1)) if rounds_match else None

        # HumanPrecision: written by session_end when developer pre-loaded context AND
        # challenge resolved in ≤1 round. Feeds human_precision_rate in _score_org().
        s["human_precision"] = bool(re.search(r"^HumanPrecision:\s*yes$", block, re.MULTILINE | re.IGNORECASE))

        # Loop A — Decision retrospectives: decisions validated/invalidated this session.
        retro_match = re.search(r"^Retrospectives:\s*(\d+)\s*\(VALIDATED=(\d+),\s*INVALIDATED=(\d+)\)", block, re.MULTILINE)
        if retro_match:
            s["retrospectives_total"] = int(retro_match.group(1))
            s["retrospectives_validated"] = int(retro_match.group(2))
            s["retrospectives_invalidated"] = int(retro_match.group(3))
        else:
            s["retrospectives_total"] = 0
            s["retrospectives_validated"] = 0
            s["retrospectives_invalidated"] = 0

        # Loop B — Autonomy depth: depth level per skill when developer caught something.
        depth_match = re.search(r"^AutonomyDepth:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
        if depth_match:
            depth_raw = depth_match.group(1).strip()
            depth_dict: dict[str, str] = {}
            for part in depth_raw.split(","):
                if "=" in part:
                    skill_d, level_d = part.strip().split("=", 1)
                    depth_dict[skill_d.strip()] = level_d.strip().upper()
            s["autonomy_depth"] = depth_dict
        else:
            s["autonomy_depth"] = {}

        # Loop C — Contract violations: contracts not followed this session.
        violations = re.findall(r"^ContractViolation:\s*(.+)$", block, re.MULTILINE)
        s["contract_violations"] = [v.strip() for v in violations]

        # Outcome signal — what happened to the work and how did it land?
        outcome_match = re.search(r"^Outcome:\s*(\w+)$", block, re.MULTILINE)
        s["outcome"] = outcome_match.group(1).upper() if outcome_match else "NONE"
        result_match = re.search(r"^OutcomeResult:\s*(\w+)$", block, re.MULTILINE)
        s["outcome_result"] = result_match.group(1).upper() if result_match else "UNKNOWN"

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


def _compute_prevented_cost(sessions: list[dict], days: int = 30) -> dict:
    """
    Compute outcome-quality signals from audit log fields.

    Returns a dict with:
    - critical_findings: total CRITICAL findings caught before commit (30d)
    - high_findings: total HIGH findings
    - direction_reversals: sessions where challenge rejected initial direction
    - nfr_gaps_flagged: NFR gaps caught pre-build
    - sessions_with_findings: count of sessions that had any findings

    These feed the PREVENTED block in the /health report — the product value claim.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    critical = 0
    high = 0
    reversals = 0
    nfr_gaps = 0
    sessions_with_findings = 0

    for s in sessions:
        # Parse session date from raw block header "### Session — YYYY-MM-DD HH:MM UTC"
        date_match = re.search(r"### Session — (\d{4}-\d{2}-\d{2})", s.get("raw", ""))
        if date_match:
            try:
                session_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                if session_date < cutoff:
                    continue
            except ValueError:
                pass

        critical += s.get("findings_critical", 0)
        high += s.get("findings_high", 0)
        if s.get("direction_reversal"):
            reversals += 1
        nfr_gaps += len(s.get("nfr_gaps", []))
        if s.get("findings_total", 0) > 0:
            sessions_with_findings += 1

    return {
        "critical_findings": critical,
        "high_findings": high,
        "direction_reversals": reversals,
        "nfr_gaps_flagged": nfr_gaps,
        "sessions_with_findings": sessions_with_findings,
        "days": days,
    }


def _detect_recurring_findings(sessions: list[dict], min_sessions: int = 3, days: int = 30) -> list[dict]:
    """
    Detect finding categories that appear in 3+ sessions within 30 days.

    Returns a list of dicts: [{category, count, sessions_pct}]
    These surface as PATTERN items in the /health report — the "you keep doing this" signal.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    category_session_count: dict[str, int] = {}

    for s in sessions:
        date_match = re.search(r"### Session — (\d{4}-\d{2}-\d{2})", s.get("raw", ""))
        if date_match:
            try:
                session_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                if session_date < cutoff:
                    continue
            except ValueError:
                pass

        seen_in_session: set[str] = set()
        for cat in s.get("finding_categories", []):
            seen_in_session.add(cat)
        for cat in seen_in_session:
            category_session_count[cat] = category_session_count.get(cat, 0) + 1

    total_sessions = max(len(sessions), 1)
    patterns = []
    for cat, count in sorted(category_session_count.items(), key=lambda x: -x[1]):
        if count >= min_sessions:
            patterns.append({
                "category": cat,
                "count": count,
                "sessions_pct": round(count / total_sessions * 100),
            })
    return patterns


def _compute_prevented_cost_score(prevented_cost: dict) -> float:
    """
    Convert prevented_cost dict to a 0.0–1.0 score.
    Weighted sum of outcome signals, normalized on ~10 events/month.
    Each CRITICAL finding caught = 2.0 pts, HIGH = 1.0, reversal = 1.5, NFR gap = 0.8.
    """
    signals = (
        prevented_cost.get("critical_findings", 0) * 2.0
        + prevented_cost.get("high_findings", 0) * 1.0
        + prevented_cost.get("direction_reversals", 0) * 1.5
        + prevented_cost.get("nfr_gaps_flagged", 0) * 0.8
    )
    return min(signals / 10.0, 1.0)


def _compute_autonomy_rate(sessions: list[dict]) -> float:
    """
    Fraction of sessions where the developer pre-empted at least one capability skill
    by providing the answers unprompted (DeveloperCaught field).

    Session 1–5: no data expected → returns 0.0 (neutral, not penalised).
    Session 6+: rising rate means the compounding loop is working.
    """
    if len(sessions) < 6:
        return 0.0  # not enough history to measure — no penalty, no bonus
    tracked = [s for s in sessions if s.get("developer_caught") is not None]
    if not tracked:
        return 0.0
    caught_count = sum(1 for s in tracked if s["developer_caught"])
    return caught_count / len(tracked)


def _compute_skill_autonomy_rate(sessions: list[dict], skill: str) -> float:
    """
    Autonomy rate for a specific skill — fraction of sessions (after session 5)
    where developer_caught contains that skill name.

    Used to determine adaptive ceremony mode per skill (e.g. nfr_check → validate mode).
    Returns 0.0 when fewer than 6 sessions exist (no adaptation before history exists).
    """
    if len(sessions) < 6:
        return 0.0
    skill_lower = skill.lower().replace("-", "_")
    tracked = [s for s in sessions if s.get("developer_caught") is not None]
    if not tracked:
        return 0.0
    caught_count = sum(
        1 for s in tracked
        if any(c.lower().replace("-", "_") == skill_lower for c in s["developer_caught"])
    )
    return caught_count / len(tracked)


_AUTONOMY_DEPTH_WEIGHTS: dict[str, float] = {
    "SURFACE": 0.25,
    "WORKING": 0.5,
    "DEEP": 1.0,
    "ELITE": 1.5,
}


def _compute_decision_durability_rate(sessions: list[dict]) -> float | None:
    """
    Fraction of retrospective entries that are VALIDATED over recent sessions.

    None when fewer than 3 sessions have retrospective data (insufficient history).
    Rising rate over time = developer's decisions are getting more durable.
    This is the closest measurable proxy for the system's core value hypothesis.
    """
    retro_sessions = [s for s in sessions if s.get("retrospectives_total", 0) > 0]
    if len(retro_sessions) < 3:
        return None
    total_validated = sum(s.get("retrospectives_validated", 0) for s in retro_sessions)
    total_all = sum(s.get("retrospectives_total", 0) for s in retro_sessions)
    if total_all == 0:
        return None
    return round(total_validated / total_all, 2)


def _compute_autonomy_depth_score(sessions: list[dict]) -> float:
    """
    Weighted autonomy score that rewards depth of engagement, not just presence.

    Replaces binary autonomy_rate with a weighted score:
      SURFACE=0.25, WORKING=0.5, DEEP=1.0, ELITE=1.5
    Normalized to [0, 1] against the ELITE ceiling.

    Sessions with developer_caught but no autonomy_depth get WORKING weight (backward compat).
    Sessions before session 6 contribute 0 (no history yet).
    """
    if len(sessions) < 6:
        return 0.0
    tracked = [s for s in sessions if s.get("developer_caught")]
    if not tracked:
        return 0.0
    total_weight = 0.0
    for s in tracked:
        depth_map = s.get("autonomy_depth", {})
        caught = s.get("developer_caught", [])
        if not caught:
            continue
        if depth_map:
            # Average depth weight across all caught skills this session
            weights = [_AUTONOMY_DEPTH_WEIGHTS.get(depth_map.get(skill, "WORKING"), 0.5) for skill in caught]
            session_weight = sum(weights) / len(weights)
        else:
            session_weight = 0.5  # default: WORKING weight for sessions before depth tracking
        total_weight += session_weight
    # Normalize: max possible weight per session is ELITE (1.5); divide by that ceiling
    return min(total_weight / (len(tracked) * 1.5), 1.0)


def _compute_contract_compliance_rate(sessions: list[dict]) -> float:
    """
    Fraction of sessions (last 20) with zero contract violations.

    Sessions without ContractViolation lines score as compliant (backward compatible —
    absence of violation data ≠ violation). Only sessions that explicitly log a
    ContractViolation are counted as non-compliant.
    Returns 1.0 when no violation data exists (no penalty for old sessions).
    """
    window = sessions[-20:]
    if not window:
        return 1.0
    non_compliant = sum(1 for s in window if s.get("contract_violations"))
    return round(1.0 - (non_compliant / len(window)), 2)


def _compute_outcome_rates(sessions: list[dict]) -> dict:
    """
    Compute outcome_signal_rate and outcome_quality_rate from audit sessions.

    outcome_signal_rate: fraction of SHIPPED/STAGED sessions that have a non-NONE outcome recorded.
    Active only when ≥10 sessions carry outcome data (warmup gate).

    outcome_quality_rate: fraction of resolved outcomes (WORKED|FAILED) that are WORKED.
    Active only when ≥10 sessions carry outcome data.

    Returns:
        outcome_signal_rate: float (0.0–1.0) or None when warmup not met
        outcome_quality_rate: float (0.0–1.0) or None when warmup not met
        sessions_with_outcome: int
        sessions_resolved: int
    """
    sessions_with_outcome = [s for s in sessions if s.get("outcome") and s["outcome"] != "NONE"]
    if len(sessions_with_outcome) < 10:
        return {
            "outcome_signal_rate": None,
            "outcome_quality_rate": None,
            "sessions_with_outcome": len(sessions_with_outcome),
            "sessions_resolved": 0,
        }

    # outcome_signal_rate: sessions that shipped/staged and recorded an outcome
    shipped_staged = [s for s in sessions if s.get("outcome") in ("SHIPPED", "STAGED")]
    with_outcome_recorded = [s for s in shipped_staged if s.get("outcome_result") not in (None, "UNKNOWN", "PENDING")]
    outcome_signal_rate = round(len(with_outcome_recorded) / len(shipped_staged), 2) if shipped_staged else 1.0

    # outcome_quality_rate: among resolved outcomes, fraction that WORKED
    resolved = [s for s in sessions_with_outcome if s.get("outcome_result") in ("WORKED", "FAILED")]
    worked = [s for s in resolved if s.get("outcome_result") == "WORKED"]
    outcome_quality_rate = round(len(worked) / len(resolved), 2) if resolved else None

    return {
        "outcome_signal_rate": outcome_signal_rate,
        "outcome_quality_rate": outcome_quality_rate,
        "sessions_with_outcome": len(sessions_with_outcome),
        "sessions_resolved": len(resolved),
    }


def _compute_convergence_velocity(sessions: list[dict]) -> dict:
    """
    Measure whether challenge loops are reaching global optimum in fewer rounds over time.

    challenge_rounds per session is already written to audit as ChallengeRounds: N.
    Velocity = slope of rounds across the last 10 challenge sessions (negative = improving).

    Returns:
        mean_rounds: average rounds across recent challenge sessions
        trend: "improving" | "stable" | "degrading" | "insufficient_data"
        velocity: float (negative = fewer rounds over time = improving)
        sessions_with_data: int
    """
    challenge_sessions_with_rounds = [
        s for s in sessions
        if "challenge" in ",".join(s.get("skills", []))
        and s.get("challenge_rounds") is not None
        and s["challenge_rounds"] > 0
    ]
    if len(challenge_sessions_with_rounds) < 3:
        return {
            "mean_rounds": None,
            "trend": "insufficient_data",
            "velocity": 0.0,
            "sessions_with_data": len(challenge_sessions_with_rounds),
        }

    recent = challenge_sessions_with_rounds[-10:]
    rounds_seq = [s["challenge_rounds"] for s in recent]
    mean_rounds = sum(rounds_seq) / len(rounds_seq)

    # Simple linear slope: velocity = (last half mean - first half mean) / half_size
    mid = len(rounds_seq) // 2
    first_half = rounds_seq[:mid] if mid > 0 else rounds_seq[:1]
    second_half = rounds_seq[mid:] if mid > 0 else rounds_seq[1:]
    first_mean = sum(first_half) / len(first_half)
    second_mean = sum(second_half) / len(second_half)
    velocity = round(second_mean - first_mean, 2)  # negative = improving

    if velocity < -0.3:
        trend = "improving"
    elif velocity > 0.3:
        trend = "degrading"
    else:
        trend = "stable"

    return {
        "mean_rounds": round(mean_rounds, 1),
        "trend": trend,
        "velocity": velocity,
        "sessions_with_data": len(challenge_sessions_with_rounds),
    }


def _compute_human_precision_rate(sessions: list[dict]) -> float:
    """
    Proxy for how well the human front-loads context, reducing challenge loop depth.

    High-precision sessions: HumanPrecision: yes in audit (written by session_end when
    developer pre-empted ≥1 skill AND challenge resolved in ≤1 round).

    Also accepts proxy computation from DeveloperCaught + challenge_rounds when
    HumanPrecision field is absent (pre-fix sessions).

    Returns fraction of challenge sessions (after session 5) that are high-precision.
    Returns 0.0 when fewer than 6 total sessions (not enough history).
    """
    if len(sessions) < 6:
        return 0.0

    challenge_sessions = [
        s for s in sessions
        if "challenge" in ",".join(s.get("skills", []))
    ]
    if not challenge_sessions:
        return 0.0

    high_precision = sum(
        1 for s in challenge_sessions
        if s.get("human_precision")  # direct field (sessions after this change)
        or (  # proxy for pre-fix sessions
            s.get("developer_caught")
            and (s.get("challenge_rounds") or 0) <= 1
            and (s.get("challenge_rounds") or 0) >= 1
        )
    )
    return high_precision / len(challenge_sessions)


def _compute_depth_multiplier(sessions: list[dict]) -> float:
    """
    Score multiplier based on session depth with this project.

    Early sessions (1–5): multiplier 0.7 — a 9/10 process score on session 3
    means youk followed its checklist, not that compounding happened.
    Mature sessions (20+): multiplier 1.0 — score is fully earned.

    This prevents a new project from reading as 9/10 on pure process compliance.
    The score has to be earned over time, not just in one session.
    """
    n = len(sessions)
    if n <= 5:
        return 0.7
    if n <= 10:
        return 0.8
    if n <= 20:
        return 0.9
    return 1.0


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

    # Outcome quality: prevented_cost_score rewards catching real findings, reversals, NFR gaps
    prevented_cost = _compute_prevented_cost(sessions, days=30)
    prevented_score = _compute_prevented_cost_score(prevented_cost) * 0.5

    # Framing accuracy: sessions where the goal was correctly translated before implementation.
    # Only counted when FramingCorrect is explicitly written (sessions predating this signal
    # return None and are excluded — no penalty for old sessions that lacked the gate).
    framing_sessions = [s for s in sessions if s.get("framing_correct") is not None]
    if framing_sessions:
        framing_correct_count = sum(1 for s in framing_sessions if s["framing_correct"])
        framing_accuracy_rate = framing_correct_count / len(framing_sessions)
    else:
        framing_accuracy_rate = 1.0  # no data → assume correct (no penalty)

    # Autonomy depth score: weighted score rewarding depth of engagement when catching things.
    # Replaces binary autonomy_rate in the scoring formula.
    # SURFACE=0.25, WORKING=0.5, DEEP=1.0, ELITE=1.5 (normalized to [0,1]).
    autonomy_depth_score = _compute_autonomy_depth_score(sessions)

    # Decision durability rate: fraction of retrospective entries that are VALIDATED.
    # None when insufficient data — treated as neutral (0.5) to avoid penalising early sessions.
    decision_durability_rate = _compute_decision_durability_rate(sessions)
    durability_bonus = (decision_durability_rate - 0.5) * 0.5 if decision_durability_rate is not None else 0.0

    # Contract compliance rate: fraction of sessions with zero contract violations.
    # 1.0 when no data (backward compat). Penalty when violations are recurring.
    contract_compliance_rate = _compute_contract_compliance_rate(sessions)
    compliance_penalty = (1.0 - contract_compliance_rate) * -0.5  # up to -0.5 penalty

    # Loop-dry rate: fraction of challenge sessions with no correction and no gap detected.
    # Measures whether run-until-dry behavioral DNA is working as intended.
    # Only counted when challenge skill ran (has Skills: containing "challenge").
    challenge_sessions = [s for s in sessions if "challenge" in ",".join(s.get("skills", []))]
    if challenge_sessions:
        clean_loops = sum(
            1 for s in challenge_sessions
            if not s.get("loop_correction") and not s.get("loop_gap")
        )
        loop_dry_rate = clean_loops / len(challenge_sessions)
    else:
        loop_dry_rate = 1.0  # no data → no penalty

    # Human precision rate: fraction of challenge sessions where human front-loaded context
    # (DeveloperCaught ≥1 AND challenge_rounds ≤ 1). Rising rate = human is learning to
    # support the reasoning loop — fewer correction rounds needed because input is precise.
    human_precision_rate = _compute_human_precision_rate(sessions)

    # Convergence velocity: trend of challenge_rounds across sessions.
    # Negative velocity = improving (fewer rounds to reach optimum over time).
    # Only contributes to score when trend is "improving" — no penalty for early sessions.
    conv_velocity = _compute_convergence_velocity(sessions)
    convergence_bonus = 0.5 if conv_velocity["trend"] == "improving" else 0.0

    # Depth multiplier: a 9/10 on session 3 = checklist compliance, not compounding.
    # Score is discounted until the project has enough sessions to demonstrate growth.
    depth_multiplier = _compute_depth_multiplier(sessions)

    # Outcome rates: active only when ≥10 sessions carry outcome data (warmup gate).
    # outcome_signal_rate: are shipped sessions getting their results recorded?
    # outcome_quality_rate: when recorded, what fraction worked?
    # Each contributes ×0.5 when active.
    outcome_rates = _compute_outcome_rates(sessions)
    outcome_signal_bonus = (
        (outcome_rates["outcome_signal_rate"] * 0.5)
        if outcome_rates["outcome_signal_rate"] is not None else 0.0
    )
    outcome_quality_bonus = (
        (outcome_rates["outcome_quality_rate"] * 0.5)
        if outcome_rates["outcome_quality_rate"] is not None else 0.0
    )

    # capability_skill_rate (2.0 weight): primary signal — did developer ability compound?
    # close_rate (0.5 weight): completion bonus only — /done matters but doesn't dominate
    # gap_resolution_rate (0.5 weight): are gaps being detected as new (not recurring)?
    # prevented_score (0.5 weight): outcome quality — did skills catch something real?
    # framing_accuracy_rate (0.5 weight): was the goal correctly translated before work started?
    # autonomy_depth_score (1.0 weight): developer catching things at DEEP/ELITE depth = compounding
    #   (replaces binary autonomy_rate — rewards depth, not just presence)
    # loop_dry_rate (1.0 weight): reasoning loops reaching global optimum before verdict
    # human_precision_rate (0.5 weight): human front-loading context = shorter loops
    # convergence_bonus (0.5 max): reward when rounds-to-optimum trend is improving
    # durability_bonus (±0.25 max): decisions proving correct over time = hypothesis signal
    # compliance_penalty (up to -0.5): contracts being violated = behavioral regression
    # outcome_signal_bonus (0.5 max): shipped work gets outcomes recorded (active ≥10 sessions)
    # outcome_quality_bonus (0.5 max): recorded outcomes are WORKED (active ≥10 sessions)
    raw_score = (
        5.0
        + (capability_skill_rate * 2.0)
        + (close_rate * 0.5)
        + (gap_resolution_rate * 0.5)
        + prevented_score
        + (framing_accuracy_rate * 0.5)
        + (autonomy_depth_score * 1.0)
        + (loop_dry_rate * 1.0)
        + (human_precision_rate * 0.5)
        + convergence_bonus
        + durability_bonus
        + compliance_penalty
        + token_penalty
        + outcome_signal_bonus
        + outcome_quality_bonus
    )
    score = raw_score * depth_multiplier

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

    # Developer autonomy signal — the proof the compounding loop is actually working.
    # Only surfaces after session 5; before that there's not enough history to measure.
    autonomy_rate = _compute_autonomy_rate(sessions)
    depth_multiplier = _compute_depth_multiplier(sessions)
    if total >= 6:
        if autonomy_rate >= 0.4:
            findings.append(
                f"Developer autonomy: {autonomy_rate:.0%} of sessions — developer pre-empted at least one "
                f"capability skill (DeveloperCaught). The compounding loop is working: developer judgment "
                f"is internalising what youk was previously catching."
            )
        elif autonomy_rate > 0:
            findings.append(
                f"Developer autonomy: {autonomy_rate:.0%} of sessions ({total} total). "
                "Rising trend expected by session 20 — developer should be catching NFR gaps "
                "before nfr_check runs. Pass developer_caught=['nfr_check'] to session_end when observed."
            )
        else:
            findings.append(
                f"Developer autonomy: 0% across {total} sessions. "
                "Target: developer pre-empts nfr_check by including performance/reliability/"
                "security answers in their initial request. No DeveloperCaught signal recorded yet. "
                "When observed, pass developer_caught=['nfr_check'] to session_end."
            )
    if depth_multiplier < 1.0:
        findings.append(
            f"Depth discount active ({depth_multiplier:.0%} multiplier, {total} sessions). "
            f"Score reflects process compliance, not compounding — full weight reached at session 20+."
        )

    # Loop-dry rate: measures whether run-until-dry behavioral DNA is working.
    # Only surfaces when challenge has run at least 3 sessions (enough signal to measure).
    challenge_sessions_count = sum(1 for s in sessions if "challenge" in ",".join(s.get("skills", [])))
    if challenge_sessions_count >= 3:
        loop_dry_sessions = sum(
            1 for s in sessions
            if "challenge" in ",".join(s.get("skills", []))
            and not s.get("loop_correction") and not s.get("loop_gap")
        )
        loop_dry_pct = loop_dry_sessions / challenge_sessions_count
        if loop_dry_pct >= 0.9:
            findings.append(
                f"Loop-dry rate: {loop_dry_pct:.0%} ({loop_dry_sessions}/{challenge_sessions_count} "
                "challenge sessions reached global optimum without correction). Run-until-dry DNA is working."
            )
        elif loop_dry_pct >= 0.7:
            corrections = challenge_sessions_count - loop_dry_sessions
            findings.append(
                f"Loop-dry rate: {loop_dry_pct:.0%} — {corrections} challenge session(s) had post-verdict "
                "corrections or retrospective gaps. Loop exits before dry in ~{1-loop_dry_pct:.0%} of sessions. "
                "Review challenge skill exit condition."
            )
        else:
            findings.append(
                f"Loop-dry rate: {loop_dry_pct:.0%} — BELOW THRESHOLD. Run-until-dry behavioral DNA is "
                f"not holding: {challenge_sessions_count - loop_dry_sessions}/{challenge_sessions_count} "
                "challenge sessions had post-verdict corrections or gaps. "
                "Run assess_skill('challenge') to diagnose."
            )

    # Convergence velocity: is the challenge loop reaching optimum in fewer rounds over time?
    # Surfaces when enough challenge sessions exist to compute a trend (≥3 with round data).
    # "Improving" means the skill+human system is learning — first-pass reasoning is deepening.
    conv_velocity = _compute_convergence_velocity(sessions)
    if conv_velocity["sessions_with_data"] >= 3:
        mean_r = conv_velocity["mean_rounds"]
        trend = conv_velocity["trend"]
        vel = conv_velocity["velocity"]
        n = conv_velocity["sessions_with_data"]
        if trend == "improving":
            findings.append(
                f"Convergence velocity: improving — challenge loop averaging {mean_r} rounds "
                f"({vel:+.1f} rounds/half-window, {n} sessions). First-pass reasoning depth is growing: "
                "fewer correction rounds needed to reach global optimum."
            )
        elif trend == "degrading":
            findings.append(
                f"Convergence velocity: degrading — challenge loop rounds increasing "
                f"({vel:+.1f} rounds/half-window, avg {mean_r} over {n} sessions). "
                "First-pass reasoning is shallowing or task complexity is rising faster than skill depth. "
                "Run assess_skill('challenge') to diagnose."
            )
        # stable: no finding — stable is expected baseline, not worth surfacing

    # Human precision rate: are humans front-loading enough context to shorten the loop?
    # Only surfaces after session 5 and when challenge has run at least 3 times.
    human_prec = _compute_human_precision_rate(sessions)
    challenge_sessions_count = sum(1 for s in sessions if "challenge" in ",".join(s.get("skills", [])))
    if total >= 6 and challenge_sessions_count >= 3:
        if human_prec >= 0.5:
            findings.append(
                f"Human precision: {human_prec:.0%} of challenge sessions resolved in ≤1 round with "
                "pre-loaded context (DeveloperCaught). Human articulation is compounding: "
                "requests are precise enough that the loop converges fast."
            )
        elif human_prec > 0:
            findings.append(
                f"Human precision: {human_prec:.0%} — human front-loading is partial. "
                "To reduce challenge rounds: include key tradeoffs, constraints, and failure modes "
                "in your initial request before the skill runs."
            )
        else:
            findings.append(
                "Human precision: 0% — no sessions where human pre-loaded context AND challenge "
                f"completed in ≤1 round ({challenge_sessions_count} challenge sessions tracked). "
                "Tip: state the key angles you've already considered in your request — "
                "this is the fastest path to reducing correction rounds."
            )

    # Retrospective recovery: a session closed without /done is recovered when the *next*
    # session opened with /learn (youk detects the missed close and runs /learn automatically).
    # Count those as recovered for messaging — they are not actually lost.
    retrospective_recoveries = 0
    for i, s in enumerate(sessions):
        if not s["close_cluster"] and i + 1 < len(sessions):
            next_s = sessions[i + 1]
            if "learn" in [sk.lower() for sk in next_s.get("skills", [])]:
                retrospective_recoveries += 1
    effective_close_count = close_count + retrospective_recoveries
    effective_skip_rate = 1 - (effective_close_count / total)

    if effective_skip_rate > 0.5:
        unrecovered = total - effective_close_count
        findings.append(
            f"Session-close loop incomplete in {effective_skip_rate:.0%} of sessions "
            f"({effective_close_count}/{total} closed or recovered via retrospective /learn). "
            f"{unrecovered} session(s) have no /done and no retrospective recovery — "
            "knowledge from those sessions did not compound. "
            "Tab-close is fine; just ensure the next session opens in the same project so /learn fires."
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

    # Project-level skill override check — when close_cluster_rate is 0 for 3+
    # consecutive sessions, check whether a project .claude/skills/done exists that is
    # silently swallowing /done without calling youk's session_end.
    consecutive_no_close = 0
    for _s in reversed(sessions):
        if not _s.get("close_cluster"):
            consecutive_no_close += 1
        else:
            break
    if consecutive_no_close >= 3:
        import json as _json
        state_file = YOUK_ROOT / "state" / "session.json"
        last_project = ""
        try:
            last_project = _json.loads(state_file.read_text()).get("last_project", "")
        except Exception:
            pass
        project_done_skill = Path(last_project) / ".claude" / "skills" / "done" if last_project else None
        if project_done_skill and project_done_skill.exists():
            findings.append(
                f"close_cluster_rate is 0% for {consecutive_no_close} consecutive sessions, but the project "
                f"has its own .claude/skills/done that overrides youk's /done. "
                "youk's session bookkeeping is not running after that skill fires. "
                "Fix: after any project /done skill runs, call session_end(close_cluster=True) "
                "manually, or use the phrase 'ship it' to trigger youk's version instead."
            )
        elif consecutive_no_close >= 3:
            # Retrospective recovery: /learn at next session open is equivalent to /done for
            # knowledge accumulation. Only flag when neither path ran.
            retrospective_count = sum(
                1 for _s in sessions[-consecutive_no_close:]
                if "learn" in [sk.lower() for sk in _s.get("skills", [])]
            )
            if retrospective_count == 0:
                findings.append(
                    f"Session-close loop missed for {consecutive_no_close} consecutive sessions — "
                    "neither /done nor retrospective /learn at next session open ran. "
                    "Tab-close is fine; ensure the next session opens in the same project "
                    "so youk can run retrospective /learn automatically."
                )

    # Task checkpoint coverage — surface when sessions lack checkpoint data.
    # Low coverage means tab-close recovery breadcrumbs are not being written.
    cp_count = sum(1 for s in sessions if "TaskCheckpoints:" in s.get("raw", ""))
    cp_coverage = round(cp_count / total, 2) if total else 0.0
    if total >= 5 and cp_coverage < 0.4:
        findings.append(
            f"task_checkpoint data in only {round(cp_coverage * 100)}% of sessions "
            f"({cp_count}/{total}). Tab-close recovery (session breadcrumbs) only fires when "
            "/build is used for code tasks. Use /build to anchor context at each commit — "
            "this also feeds the progressive learning loop."
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

    # Contract capture health: flag when a project has many real sessions but no contracts.
    # Uses per-project session count from audit (not global total) to avoid false alarms
    # from cross-project session inflation. Skips projects with only stub/tab-close entries.
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if projects_dir.exists():
        # Build per-project session counts from parsed audit sessions (exclude stubs)
        proj_session_counts: dict[str, int] = {}
        for s in sessions:
            proj_name = s.get("project", "")
            if not proj_name:
                continue
            is_stub = "tab-close" in s.get("raw", "") or "compact-checkpoint" in s.get("raw", "")
            if not is_stub:
                proj_session_counts[proj_name] = proj_session_counts.get(proj_name, 0) + 1

        for proj in projects_dir.iterdir():
            proj_session_count = proj_session_counts.get(proj.name, 0)
            if proj_session_count < 5:
                continue  # not enough real sessions to flag
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
                    f"Project '{proj.name}' has {proj_session_count} sessions but no contracts in contracts.md. "
                    "Working agreements stated in conversation are not surviving compaction. "
                    "Call save_contract(agreement, project_dir) the moment a contract is verbalized — "
                    "do not wait for /done."
                )
                break  # one finding is enough — same root cause

    # Release readiness — structural checks on plugin, install, and UX integrity.
    # These don't depend on audit history; they read files directly.
    release_issues = _check_release_readiness()
    if release_issues:
        for issue in release_issues[:2]:  # cap at 2 so they don't flood findings
            findings.append(issue)

    # Git outcome signals — churn hotspots, reverts, commits-without-done.
    # These are the only outcome metrics that survive beyond session end.
    git_findings = _check_git_outcomes(sessions)
    findings.extend(git_findings[:2])  # cap at 2 so audit findings don't get buried

    if not findings:
        findings.append(f"Org health nominal. Score: {score}/10.")

    return findings


def _check_release_readiness() -> list[str]:
    """
    Structural checks that a marketplace reviewer or senior engineer would run
    before approving a plugin submission. Checks file integrity, install path
    validity, and first-run UX gaps. Returns a list of blocker descriptions.
    Does not depend on audit history — reads files directly.
    """
    import json as _json
    issues: list[str] = []

    # 1. Plugin manifest integrity
    plugin_json = YOUK_ROOT / "plugin" / ".claude-plugin" / "plugin.json"
    if plugin_json.exists():
        try:
            manifest = _json.loads(plugin_json.read_text())

            # Hooks path must resolve to a real file
            hooks_rel = manifest.get("hooks", "")
            if hooks_rel:
                hooks_path = (plugin_json.parent / hooks_rel).resolve()
                if not hooks_path.exists():
                    issues.append(
                        f"plugin.json hooks path '{hooks_rel}' does not resolve to an existing file "
                        f"(looked for {hooks_path}). Marketplace install will silently skip hooks."
                    )

            # Install script must be fetchable (check it exists in repo at expected path)
            install_cmd = manifest.get("install", {}).get("command", "")
            if "install.sh" in install_cmd:
                install_sh = YOUK_ROOT / "scripts" / "install.sh"
                if not install_sh.exists():
                    issues.append(
                        "plugin.json install command references scripts/install.sh but the file "
                        "does not exist. Marketplace install will fail on first run."
                    )

            # Version field must be present and semver-like
            version = manifest.get("version", "")
            if not version or not any(c.isdigit() for c in version):
                issues.append(
                    f"plugin.json version field is missing or non-semver ('{version}'). "
                    "Marketplace submissions require a valid version string."
                )
        except _json.JSONDecodeError:
            issues.append("plugin.json is not valid JSON — marketplace submission will be rejected.")
    elif (YOUK_ROOT / "plugin").exists():
        issues.append(
            "plugin/.claude-plugin/plugin.json not found. "
            "Required for marketplace submission."
        )
    else:
        # No plugin directory at all — not a marketplace project, skip structural checks
        return issues

    # 2. First-session UX gap: does session_plan mention /done for session_counter == 1?
    # Proxy: check that the first-session branch in session.py contains '/done'
    session_py = YOUK_ROOT / "servers" / "core" / "src" / "session.py"
    if session_py.exists():
        src = session_py.read_text()
        first_session_block_start = src.find("is_cold_start")
        first_session_block = src[first_session_block_start:first_session_block_start + 800]
        if "/done" not in first_session_block and "done" not in first_session_block.lower():
            issues.append(
                "First-session plan does not mention /done. "
                "New users who don't type /done after session 1 get no compounding — "
                "youk is invisible to them. Add a /done prompt to the cold-start session plan item."
            )

    # 3. Doctor script must exist and be executable
    doctor_sh = YOUK_ROOT / "scripts" / "doctor.sh"
    if not doctor_sh.exists():
        issues.append(
            "scripts/doctor.sh not found. "
            "Marketplace users need a post-install verification command."
        )

    # 4. README must have a verification step (proxy: 'doctor' appears in README)
    readme = YOUK_ROOT / "README.md"
    if readme.exists() and "doctor" not in readme.read_text().lower():
        issues.append(
            "README.md has no mention of doctor.sh. "
            "New users need a 'did it work?' step after install."
        )

    return issues


def _check_git_outcomes(sessions: list[dict]) -> list[str]:
    """
    Read git history to surface outcome signals that process metrics miss.
    Checks: churn hotspots (files changed in 3+ consecutive sessions),
    recent reverts (revert commits in last 30 days), and sessions where
    commits happened but /done was not typed.
    Returns findings list — empty if git is unavailable or clean.
    """
    import subprocess as _sp
    findings: list[str] = []

    # Find the most recently touched project directory from audit sessions
    project_dirs: list[str] = []
    for s in sessions:
        proj = s.get("project", "")
        if proj and proj not in project_dirs:
            project_dirs.append(proj)

    # Resolve to actual paths by looking in knowledge/projects/{slug}/context.md
    candidate_paths: list[str] = []
    for slug in project_dirs[:3]:  # check up to 3 recent projects
        ctx = YOUK_ROOT / "knowledge" / "projects" / slug / "context.md"
        if ctx.exists():
            # context.md doesn't store the full path — use HOST_HOME heuristic
            candidate_paths.append(str(Path("/host-home") / "Desktop" / slug))
            candidate_paths.append(str(Path("/host-home") / slug))

    # Also try the youk repo itself as a known git root
    candidate_paths.append(str(YOUK_ROOT))

    # 1. Commits-without-done: audit says Commits: yes but CloseCluster: no
    commits_no_done = sum(
        1 for s in sessions[-20:]  # last 20 sessions only
        if s.get("commits") and not s.get("close_cluster")
    )
    if commits_no_done >= 3:
        findings.append(
            f"{commits_no_done} recent sessions had commits but no /done. "
            "Work is shipping without patterns being extracted. "
            "Type /done before closing — it takes 60 seconds and is the compounding trigger."
        )

    # 2. Revert detection — git log for revert commits in last 30 days
    for git_root in candidate_paths:
        try:
            result = _sp.run(
                ["git", "-C", git_root, "log", "--oneline", "--since=30 days ago",
                 "--grep=^[Rr]evert", "--no-walk=unsorted"],
                capture_output=True, text=True, timeout=5
            )
            reverts = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
            if len(reverts) >= 2:
                findings.append(
                    f"{len(reverts)} revert commits in the last 30 days "
                    f"({Path(git_root).name}). "
                    "Consider /stress-test before the next major change in this area."
                )
                break
        except Exception:
            continue

    # 3. Churn hotspots — files changed in 3+ of the last 10 commits
    for git_root in candidate_paths:
        try:
            result = _sp.run(
                ["git", "-C", git_root, "log", "--name-only", "--pretty=format:", "-20"],
                capture_output=True, text=True, timeout=5
            )
            file_counts: dict[str, int] = {}
            for line in result.stdout.splitlines():
                f = line.strip()
                if f and not f.startswith("#"):
                    file_counts[f] = file_counts.get(f, 0) + 1
            hotspots = [f for f, c in file_counts.items() if c >= 4]
            if hotspots:
                top = hotspots[:3]
                findings.append(
                    f"Churn hotspot detected ({Path(git_root).name}): "
                    + ", ".join(top)
                    + f" — changed in {file_counts[top[0]]}+ of last 20 commits. "
                    "Consider /adr or /stress-test before the next change here."
                )
                break
        except Exception:
            continue

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

    sessions = _parse_audit_sessions(audit_texts)
    real_sessions = sum(
        1 for s in sessions
        if "tab-close" not in s.get("raw", "") and "compact-checkpoint" not in s.get("raw", "")
    )
    return HealthReport(
        org_score=score,
        sessions_analyzed=real_sessions,
        findings=findings,
        proposals=proposals,
    )


def _parse_skill_patch_signals(audit_texts: list[str]) -> dict[str, int]:
    """Return {skill_name: patch_count} for all SkillPatch: lines in audit."""
    patches: dict[str, int] = {}
    for text in audit_texts:
        for line in text.splitlines():
            if line.startswith("SkillPatch:"):
                rest = line[len("SkillPatch:"):].strip()
                skill = rest.split(" — ")[0].strip() if " — " in rest else rest
                patches[skill] = patches.get(skill, 0) + 1
    return patches


def _analyze_promotion_candidates(audit_texts: list[str]) -> list[dict]:
    """
    Scan SkillGap: lines across all audit sessions.
    A gap appearing 3+ times for the same skill → propose a SKILL_EDIT.
    A gap appearing across 2+ distinct projects → flag for cross-project.md addition.
    When a skill has both SkillGap and SkillPatch entries in the same window,
    flag as a patch-cycle: the auto-applied fix didn't resolve the gap.
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

    patch_counts = _parse_skill_patch_signals(audit_texts)

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
            patch_cycle = patch_counts.get(skill, 0) > 0
            candidates.append({
                "skill": skill,
                "occurrence_count": count,
                "distinct_projects": len(projects),
                "sample_gaps": list({gap for _, gap in occurrences})[:3],
                "promotion_target": promotion_target,
                "change_type": change_type,
                "patch_cycle": patch_cycle,
                "patch_count": patch_counts.get(skill, 0),
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

    # skill_invocation_rate: primary org_score driver (weight 2.0) — persisted so trend is visible
    capability_count = sum(1 for s in sessions if s.get("capability_skills"))
    skill_invocation_rate = round(capability_count / total, 2) if total else 0.0

    # nfr_check_hit_rate: % of sessions where nfr_check fired (gate discipline signal)
    nfr_sessions = sum(
        1 for s in sessions
        if any(sk.lower().replace("-", "_") in ("nfr_check", "nfr-check") for sk in s.get("skills", []))
    )
    nfr_check_hit_rate = round(nfr_sessions / total, 2) if total else 0.0

    # contracts_total: total contracts saved across all projects (knowledge growth signal)
    contracts_total = 0
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if projects_dir.exists():
        for contracts_file in projects_dir.glob("*/contracts.md"):
            try:
                contracts_total += sum(
                    1 for line in contracts_file.read_text().splitlines()
                    if line.startswith("- ")
                )
            except Exception:
                pass

    # skill_patch_rate: % of sessions with within-session skill adaptations applied
    # MidSessionAdaptations: N audit line (N > 0 = patch happened in-session)
    patched_sessions = sum(
        1 for s in sessions
        if re.search(r"MidSessionAdaptations:\s*[1-9]", s.get("raw", ""))
    )
    skill_patch_rate = round(patched_sessions / total, 2) if total else 0.0

    # Loop health verdict
    # Retrospective recovery (/learn at next session open) recovers a no-/done close.
    # A low close_rate alone is not a stall signal — check skill_invocation_rate instead.
    evolution_active = gaps_last30 > 0 or proposals_applied > 0
    if skill_invocation_rate == 0.0 and close_rate == 0.0:
        verdict = "STALLED — no capability skills and no /done; loop is not running"
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
        # Compute convergence and human precision for persistence
        sessions_for_conv = _parse_audit_sessions(audit_texts)
        _conv = _compute_convergence_velocity(sessions_for_conv)
        _hpr = _compute_human_precision_rate(sessions_for_conv)
        entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "org_score": current_score,
            "velocity": velocity,
            "proposals_applied": proposals_applied,
            "gaps_last30": gaps_last30,
            "close_cluster_rate": close_rate,
            "skill_invocation_rate": skill_invocation_rate,
            "nfr_check_hit_rate": nfr_check_hit_rate,
            "contracts_total": contracts_total,
            "skill_patch_rate": skill_patch_rate,
            "convergence_velocity": _conv.get("velocity", 0.0),
            "convergence_trend": _conv.get("trend", "insufficient_data"),
            "convergence_mean_rounds": _conv.get("mean_rounds"),
            "human_precision_rate": round(_hpr, 2),
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


def _compute_knowledge_velocity(audit_texts: list[str], slug: str) -> dict:
    """Measure how fast the developer's personal knowledge base is growing.

    org_score measures youk health. knowledge_velocity measures whether the developer
    is accumulating intelligence — measures developer knowledge growth, separate from org_score.
    """
    full_text = "\n".join(audit_texts)

    # Project contracts total — count only "- " prefixed lines (actual contracts).
    # Prose headers, separator lines, and blank lines must be excluded.
    project_contracts_file = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    contract_total = 0
    if project_contracts_file.exists():
        contract_total = sum(
            1 for ln in project_contracts_file.read_text().splitlines()
            if ln.startswith("- ")
        )

    # avg_contracts_per_session — derived from ContractsSaved audit lines (written by
    # session_end after each /done). Falls back to file-based estimate for pre-fix sessions.
    contract_saves_raw = re.findall(r"ContractsSaved:\s*(\d+)", full_text)
    audit_has_contracts_saved = bool(contract_saves_raw)
    if contract_saves_raw:
        rates = [int(x) for x in contract_saves_raw[-5:]]
        avg_contracts_per_session = round(sum(rates) / len(rates), 1)
    elif contract_total > 0:
        # Audit predates ContractsSaved field — derive floor from file
        sessions = _parse_audit_sessions(audit_texts)
        denom = max(len(sessions), 1)
        avg_contracts_per_session = round(contract_total / denom, 1)
    else:
        avg_contracts_per_session = 0.0

    # Domain concept count — absolute, from files (not derived from audit)
    domain_dir = YOUK_ROOT / "knowledge" / "domain"
    domain_concepts = (
        sum(1 for f in domain_dir.glob("*.md") if f.name != "gaps.md")
        if domain_dir.exists() else 0
    )

    # /learn invocation rate across recent sessions
    sessions = _parse_audit_sessions(audit_texts)
    total = len(sessions)
    learn_count = sum(1 for s in sessions if "learn" in s.get("skills", []))
    learn_rate = round(learn_count / total, 2) if total else 0.0

    # Verdict — STALLED requires that no ContractsSaved lines appear in the audit,
    # meaning session_end ran but saved nothing recently (vs. pre-fix sessions
    # where ContractsSaved was never written — those get the file-based fallback
    # which should show in avg_contracts_per_session but not suppress STALLED).
    # When audit has ContractsSaved lines, use the rate to pick the verdict tier.
    # When audit has NO ContractsSaved lines but contracts exist: STALLED.
    if avg_contracts_per_session >= 1.0 and domain_concepts > 0 and audit_has_contracts_saved:
        verdict = "GROWING — contracts and domain concepts accumulating each session"
    elif (avg_contracts_per_session >= 0.3 or domain_concepts > 0) and audit_has_contracts_saved:
        verdict = "SLOW — knowledge accumulating but below 1 contract/session average"
    elif contract_total > 0:
        verdict = "STALLED — existing knowledge loaded but nothing added recently"
    else:
        verdict = "EMPTY — no knowledge accumulated yet; run /learn at session end"

    return {
        "avg_contracts_per_session": avg_contracts_per_session,
        "domain_concepts_total": domain_concepts,
        "project_contracts_total": contract_total,
        "learn_rate": learn_rate,
        "verdict": verdict,
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

    # Knowledge velocity — measures developer-ability growth (separate from org_score)
    import json as _j
    _state_file = YOUK_ROOT / "state" / "session.json"
    _slug = ""
    try:
        _slug = _j.loads(_state_file.read_text()).get("last_project", "")
    except Exception:
        pass
    knowledge_velocity = _compute_knowledge_velocity(audit_texts, _slug)

    # Outcome quality signals — what youk actually prevented (product value claim)
    sessions_parsed = _parse_audit_sessions(audit_texts)
    prevented_cost = _compute_prevented_cost(sessions_parsed, days=30)
    recurring_patterns = _detect_recurring_findings(sessions_parsed, min_sessions=3, days=30)

    autonomy_rate = _compute_autonomy_rate(sessions_parsed)
    autonomy_depth_score = _compute_autonomy_depth_score(sessions_parsed)
    decision_durability_rate = _compute_decision_durability_rate(sessions_parsed)
    contract_compliance_rate = _compute_contract_compliance_rate(sessions_parsed)
    depth_multiplier = _compute_depth_multiplier(sessions_parsed)
    conv_velocity = _compute_convergence_velocity(sessions_parsed)
    human_precision_rate = _compute_human_precision_rate(sessions_parsed)

    # Developer growth report — five longitudinal signals that answer "is the developer improving?"
    # Each signal tracks a different dimension of growth. Trend direction is the key reading.
    framing_sessions = [s for s in sessions_parsed if s.get("framing_correct") is not None]
    framing_accuracy = (
        round(sum(1 for s in framing_sessions if s["framing_correct"]) / len(framing_sessions), 2)
        if framing_sessions else None
    )
    growth_signals = []
    if decision_durability_rate is not None:
        pct = int(decision_durability_rate * 100)
        growth_signals.append(f"Decision durability:  {pct}% (decisions proving correct, last sessions with data)")
    else:
        growth_signals.append("Decision durability:  — (no retrospective data yet — pass decision_retrospectives to session_end)")
    depth_pct = int(autonomy_depth_score * 100)
    growth_signals.append(f"Autonomy depth:       {depth_pct}% weighted score (SURFACE=25%, WORKING=50%, DEEP=100%, ELITE=150%)")
    compliance_pct = int(contract_compliance_rate * 100)
    growth_signals.append(f"Contract compliance:  {compliance_pct}% (sessions with zero violations, last 20)")
    if conv_velocity["trend"] != "insufficient_data":
        v = conv_velocity.get("velocity", 0)
        direction = "↓ improving" if v < 0 else "→ stable" if v == 0 else "↑ degrading"
        growth_signals.append(f"Convergence velocity: {v:+.1f} rounds/session ({direction})")
    else:
        growth_signals.append("Convergence velocity: — (need 3+ challenge sessions)")
    if framing_accuracy is not None:
        growth_signals.append(f"Framing accuracy:     {int(framing_accuracy * 100)}%")
    else:
        growth_signals.append("Framing accuracy:     — (no data yet)")

    positive_signals = sum([
        decision_durability_rate is not None and decision_durability_rate > 0.6,
        autonomy_depth_score > 0.4,
        contract_compliance_rate > 0.85,
        conv_velocity["trend"] == "improving",
        framing_accuracy is not None and framing_accuracy > 0.8,
    ])
    if positive_signals >= 4:
        growth_trend = "IMPROVING"
    elif positive_signals >= 2:
        growth_trend = "DEVELOPING"
    else:
        growth_trend = "EARLY"
    developer_growth_report = (
        "[DEVELOPER GROWTH]\n"
        + "\n".join(f"  {s}" for s in growth_signals)
        + f"\n  Trend: {growth_trend} — {positive_signals} of 5 growth signals positive"
    )
    if compliance_pct < 85:
        developer_growth_report += f"\n  ⚠ Contract compliance below threshold ({compliance_pct}%) — review ContractViolation entries"
    if autonomy_depth_score > 0 and autonomy_depth_score < 0.4:
        developer_growth_report += "\n  ↑ Autonomy depth low — review SURFACE/WORKING/DEEP/ELITE rubrics in skill files"

    base = {
        "org_score": report.org_score,
        "sessions_analyzed": report.sessions_analyzed,
        "findings": report.findings,
        "proposals": [p.to_dict() for p in report.proposals],
        "proposals_count": len(report.proposals),
        "improvement_velocity": velocity,
        "knowledge_velocity": knowledge_velocity,
        "prevented_this_month": prevented_cost,
        "developer_autonomy_rate": round(autonomy_rate, 2),
        "autonomy_depth_score": round(autonomy_depth_score, 2),
        "decision_durability_rate": decision_durability_rate,
        "contract_compliance_rate": contract_compliance_rate,
        "developer_growth_report": developer_growth_report,
        "depth_multiplier": depth_multiplier,
        "convergence_velocity": conv_velocity,
        "human_precision_rate": round(human_precision_rate, 2),
        "compounding_verdict": (
            "ELITE — developer pre-empting skills at DEEP/ELITE depth; compounding loop closed"
            if autonomy_depth_score >= 0.6
            else "ELITE — developer pre-empting skills; compounding loop closed"
            if autonomy_rate >= 0.4
            else "GROWING — autonomy signal emerging" if autonomy_rate > 0
            else "EARLY — not enough sessions or no DeveloperCaught signal yet"
        ),
    }

    # PREVENTED block — leads the health report as the product value claim
    prevented_items = []
    if prevented_cost["critical_findings"] > 0:
        prevented_items.append(
            f"{prevented_cost['critical_findings']} CRITICAL finding(s) caught before commit"
        )
    if prevented_cost["high_findings"] > 0:
        prevented_items.append(
            f"{prevented_cost['high_findings']} HIGH finding(s) flagged in review"
        )
    if prevented_cost["direction_reversals"] > 0:
        prevented_items.append(
            f"{prevented_cost['direction_reversals']} direction reversal(s) — "
            "wrong-path work avoided"
        )
    if prevented_cost["nfr_gaps_flagged"] > 0:
        prevented_items.append(
            f"{prevented_cost['nfr_gaps_flagged']} NFR gap(s) caught pre-build"
        )
    if prevented_items:
        base["prevented_summary"] = "PREVENTED THIS MONTH: " + "; ".join(prevented_items)
    else:
        base["prevented_summary"] = (
            "PREVENTED: no outcome data yet — pass findings/direction_reversal/nfr_gaps "
            "to session_end after review skills run"
        )

    if recurring_patterns:
        base["recurring_patterns"] = recurring_patterns
        pattern_names = ", ".join(p["category"] for p in recurring_patterns[:3])
        base["recurring_patterns_warning"] = (
            f"RECURRING: {pattern_names} — same finding category in 3+ sessions. "
            "This is a systematic weakness, not an individual error."
        )

    # Surface knowledge velocity warnings when stalled or empty
    if knowledge_velocity["verdict"].startswith(("STALLED", "EMPTY")):
        base["knowledge_velocity_warning"] = (
            f"Knowledge velocity: {knowledge_velocity['verdict']}. "
            "Run /learn at the end of each session to extract patterns into knowledge/domain/."
        )

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

    # Patch-cycle detection: skills with both SkillGap and SkillPatch entries
    # indicate that an auto-applied SKILL_EDIT didn't resolve the gap.
    patch_cycles = [c for c in promotion_candidates if c.get("patch_cycle")]
    if patch_cycles:
        base["patch_cycle_warning"] = (
            f"{len(patch_cycles)} skill(s) have both SkillGap and SkillPatch entries — "
            "auto-applied patches did not resolve the gap. Manual review required: "
            + ", ".join(c["skill"] for c in patch_cycles)
        )

    # Proactive-improvement signal — skill-forge run (the forward half of the loop).
    # Distinct from reactive proposals above: forge anticipates from stack analysis,
    # self_heal/proposals correct from past session evidence.
    forge = _read_forge_run()
    if forge:
        created = len(forge.get("skills_created", []))
        sharpened = len(forge.get("skills_sharpened", []))
        if created or sharpened:
            base["proactive_improvement"] = {
                "stack": forge.get("stack", "unknown"),
                "skills_created": created,
                "skills_sharpened": sharpened,
                "converged": forge.get("converged", False),
                "ceiling_hit": forge.get("ceiling_hit", False),
            }
            _conv = "converged" if forge.get("converged") else "ceiling hit (not converged)"
            base["proactive_improvement_note"] = (
                f"skill-forge ran on {forge.get('stack', 'unknown')}: {created} created, "
                f"{sharpened} sharpened, {_conv}. Proactive half of the improvement loop."
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

    # Multi-directional convergence check — applies uniform pressure across all seven
    # angles against the current state of youk. Not structured adversary personas —
    # the same question applied from every direction until all angles converge or
    # unknown-unknowns are flagged. Stops only when no new divergence appears.
    convergence_check = _run_convergence_check(sessions_parsed, report)
    if convergence_check:
        base["convergence_check"] = convergence_check

    return base


def _run_convergence_check(sessions: list[dict], report: object) -> dict:
    """
    Multi-directional convergence check for youk itself.

    Applies pressure from all seven angles against the current state of youk.
    Returns findings per angle and overall verdict. Called at every health cycle.
    Stops when all angles return the same answer or flags unknown-unknowns.

    This is the "is there more?" loop made structural — not a question but a
    convergence engine that finds holes the four lenses and structured adversaries miss.
    """
    _YOUK_ROOT = Path("/youk")

    findings: dict[str, str] = {}
    unknown_unknowns: list[str] = []

    # STRUCTURAL — what weak links exist regardless of feature quality?
    structural_gaps = []
    if not (_YOUK_ROOT / "CHANGELOG.md").exists():
        structural_gaps.append("no CHANGELOG — upgrade path undocumented")
    if not (_YOUK_ROOT / "SECURITY.md").exists():
        structural_gaps.append("no SECURITY.md — threat model undocumented")
    # Check Dockerfile pinning
    for df_path in [_YOUK_ROOT / "servers" / "core" / "Dockerfile",
                    _YOUK_ROOT / "servers" / "code" / "Dockerfile"]:
        if df_path.exists():
            content = df_path.read_text()
            if "FROM python:" in content and "@sha256:" not in content:
                structural_gaps.append(f"{df_path.name} base image not pinned to digest")
    # Check state bug — coverage file should not accumulate across goals
    coverage_file = _YOUK_ROOT / "state" / "session-goal-coverage.json"
    goal_file = _YOUK_ROOT / "state" / "session-goal.json"
    if coverage_file.exists() and not goal_file.exists():
        structural_gaps.append("session-goal-coverage.json exists without active goal — stale coverage")
    findings["structural"] = "CLEAR" if not structural_gaps else "GAPS: " + "; ".join(structural_gaps)

    # OPERATIONAL — can a stranger use this without hand-holding?
    operational_gaps = []
    if not (_YOUK_ROOT / "scripts" / "install.sh").exists():
        operational_gaps.append("no install script")
    if not (_YOUK_ROOT / "scripts" / "doctor.sh").exists():
        operational_gaps.append("no doctor script")
    if not (_YOUK_ROOT / "docs" / "getting-started.md").exists():
        operational_gaps.append("no getting-started doc")
    findings["operational"] = "CLEAR" if not operational_gaps else "GAPS: " + "; ".join(operational_gaps)

    # EXPERIENTIAL — would a principal engineer deploying to 50 engineers approve?
    # Proxy: are there enough sessions with skill invocation to demonstrate real value?
    total_sessions = len(sessions)
    sessions_with_skills = sum(1 for s in sessions if s.get("capability_skills"))
    skill_rate = sessions_with_skills / total_sessions if total_sessions else 0.0
    if total_sessions < 5:
        findings["experiential"] = "UNKNOWN — insufficient session history for principal engineer assessment"
        unknown_unknowns.append("experiential: requires real principal engineer evaluation after 20+ sessions")
    elif skill_rate < 0.5:
        findings["experiential"] = f"WEAK — only {skill_rate:.0%} of sessions invoked capability skills; principal engineer would question ROI"
    else:
        findings["experiential"] = f"CLEAR — {skill_rate:.0%} skill invocation rate across {total_sessions} sessions"

    # ADVERSARIAL — what would a competitor with deeper context reject?
    adversarial_gaps = []
    if total_sessions < 20:
        adversarial_gaps.append(f"only {total_sessions} sessions — compounding claims unverifiable before session 20")
    framing_sessions = [s for s in sessions if s.get("framing_correct") is not None]
    if framing_sessions:
        wrong_framing = sum(1 for s in framing_sessions if not s["framing_correct"])
        if wrong_framing > 0:
            adversarial_gaps.append(f"{wrong_framing} session(s) with wrong goal framing — competitor would call this an autonomy gap")
    if not adversarial_gaps:
        unknown_unknowns.append("adversarial: requires real competitor analysis — cannot be self-assessed")
        findings["adversarial"] = "UNKNOWN — self-assessment cannot substitute for real competitor analysis"
    else:
        findings["adversarial"] = "GAPS: " + "; ".join(adversarial_gaps)

    # TEMPORAL — does this hold across model generations?
    # Proxy: are contracts and skills version-controlled? Is there a continuity mechanism?
    temporal_gaps = []
    if not (_YOUK_ROOT / "knowledge").exists():
        temporal_gaps.append("no knowledge directory — nothing to persist across model generations")
    if not (_YOUK_ROOT / "config").exists():
        temporal_gaps.append("no config directory — behavioral contracts not versioned")
    unknown_unknowns.append("temporal: model generation transition requires real testing when next model ships")
    findings["temporal"] = "PARTIALLY CLEAR — contracts versioned; real model transition test pending" if not temporal_gaps else "GAPS: " + "; ".join(temporal_gaps)

    # OUTCOME — do predictions match reality? (lagged signal — requires real usage)
    outcome_sessions_with_convergence = [
        s for s in sessions if "ConvergenceAtClose" in s.get("raw", "")
    ]
    if not outcome_sessions_with_convergence:
        unknown_unknowns.append("outcome: no sessions with ConvergenceAtClose audit field yet — loop just instrumented")
        findings["outcome"] = "UNKNOWN — outcome tracking just instrumented; requires sessions to accumulate"
    else:
        findings["outcome"] = f"TRACKING — {len(outcome_sessions_with_convergence)} session(s) with convergence data"

    # SEMANTIC — given angles 1-6, does the label "elite" fit?
    gap_angles = [a for a, v in findings.items() if v.startswith(("GAPS", "WEAK", "UNKNOWN"))]
    if len(gap_angles) == 0:
        findings["semantic"] = "CONVERGED — all angles clear; label is justified"
        verdict = "CONVERGED"
    elif len(gap_angles) <= 2 and all(findings[a].startswith("UNKNOWN") for a in gap_angles):
        findings["semantic"] = f"PARTIALLY CONVERGED — {len(gap_angles)} angle(s) require external validation"
        verdict = "PARTIALLY_CONVERGED"
    else:
        findings["semantic"] = f"LABEL NOT YET JUSTIFIED — {len(gap_angles)} angle(s) not clear: {', '.join(gap_angles)}"
        verdict = "DIVERGED"

    return {
        "angles": findings,
        "unknown_unknowns": unknown_unknowns,
        "verdict": verdict,
        "angles_clear": sum(1 for v in findings.values() if v.startswith("CLEAR")),
        "distance_from_optimum": f"{len(gap_angles)}/7 angles not yet clear",
        "note": (
            "This check applies uniform pressure from all seven angles. "
            "Contradictions between angles are the signal — follow them. "
            "Unknown-unknowns require real external collision to resolve."
        ),
    }


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


_CROSS_PROJECT_THEMES = {
    "Testing discipline":    ["test", "coverage", "assert", "verify", "pytest", "mock"],
    "Commit hygiene":        ["commit", "lint", "format", "ruff", "push", "pr ", "pull request"],
    "Context-before-action": ["context", "config", "project", "read", "check first", "makefile", "ci "],
    "Knowledge abstraction": ["contract", "principle", "abstract", "pattern", "transfer", "generalise", "generalize"],
    "Security":              ["secret", "api key", "credential", "env", "token", ".env"],
    "Error handling":        ["error", "exception", "fail", "fallback", "surface", "blocked"],
}


def _classify_theme(contract: str) -> str:
    lower = contract.lower()
    for theme, keywords in _CROSS_PROJECT_THEMES.items():
        if any(kw in lower for kw in keywords):
            return theme
    return "General"


def _detect_cross_project_patterns(min_projects: int = 2) -> list[dict]:
    """Scan all project contracts.md files and find contracts recurring across projects.
    Returns candidates: [{contract, projects, count, theme}] sorted by count desc.
    When 3+ candidates share a theme, writes a grouped summary to knowledge/global/patterns.md."""
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
        {"contract": c, "projects": slugs, "count": len(slugs), "theme": _classify_theme(c)}
        for c, slugs in contract_to_projects.items()
        if len(slugs) >= min_projects
    ]
    candidates = sorted(candidates, key=lambda x: x["count"], reverse=True)

    # Write thematic groupings to knowledge/global/patterns.md when 3+ candidates share a theme
    if candidates:
        _write_patterns_summary(candidates)

    return candidates


def _write_patterns_summary(candidates: list[dict]) -> None:
    """Write thematic groupings to knowledge/global/patterns.md for structured cross-project synthesis."""
    from collections import defaultdict
    global_dir = YOUK_ROOT / "knowledge" / "global"
    if not global_dir.exists():
        return
    patterns_file = global_dir / "patterns.md"

    # Group by theme
    by_theme: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        by_theme[c["theme"]].append(c)

    # Only write themes with 3+ candidates (signal, not noise)
    themes_to_write = {t: cs for t, cs in by_theme.items() if len(cs) >= 3}
    if not themes_to_write:
        return

    try:
        existing = patterns_file.read_text() if patterns_file.exists() else ""
        lines = [
            "# Cross-project pattern synthesis",
            "# Auto-generated by _detect_cross_project_patterns() — edit or prune as needed.",
            "",
        ]
        for theme, theme_candidates in sorted(themes_to_write.items()):
            lines.append(f"## {theme}")
            lines.append(f"*{len(theme_candidates)} contracts found across 2+ projects*")
            lines.append("")
            for c in theme_candidates[:5]:
                projects_str = ", ".join(c["projects"])
                lines.append(f"- {c['contract']}  *(projects: {projects_str})*")
            lines.append("")

        new_content = "\n".join(lines)
        if new_content != existing:
            patterns_file.write_text(new_content)
    except Exception:
        pass


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
        # Write audit trail so self-heal can detect patch→gap cycles.
        try:
            month = datetime.utcnow().strftime("%Y-%m")
            audit_file = CLAUDE_ROOT / "audit" / f"{month}.md"
            if audit_file.exists():
                with open(audit_file, "a") as _af:
                    _af.write(f"SkillPatch: {proposal.target} — section '{section}' auto-applied (proposal {proposal.id})\n")
        except Exception:
            pass  # audit write failure must never block the apply
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
    Types not in safe_types return blocked=True — caller must surface to founder.

    Tier 1 (require human approval): CODE_EDIT, CONFIG_EDIT — silent blast radius,
    may break gates or guardrails, requires Docker rebuild to recover.
    Tier 2 (auto-applicable): SKILL_EDIT, FILE_CREATE — visible blast radius,
    recoverable within a session without rebuild. See ADR-002 for full rationale.

    Use safe_types=["SKILL_EDIT","FILE_CREATE"] for autonomous /improve and /forge runs.
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
