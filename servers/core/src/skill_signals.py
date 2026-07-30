"""Skill self-improvement signal detector.

Reads the audit log after session_end and produces typed signals per
skill-dimension pair. Three signal types:

  GAP        — downstream skill found HIGH finding in domain upstream examined & missed
  SCOPE_MISS — downstream skill found HIGH finding in domain upstream never declared examining
  SURPLUS    — developer pre-empted a skill dimension at DEEP for 3+ consecutive sessions
  STABLE     — output survived, no correction, no pre-emption (no deduction)

Writes signals to state/skill-signals.jsonl (append-only, one JSON line per
skill-session pair). Called silently from session_end(); never blocks.

Point deduction weights (informational — ledger applied by health.py):
  GAP:        -4 points
  SCOPE_MISS: -6 points  (1.5x GAP — not looking is worse than looking & missing)
  SURPLUS:    -2 points/session  (over-scaffolding penalty, 3+ consecutive sessions)
  STABLE:     +2 points recovery
  PRE_EMPTED: +3 points (skill successfully transferred knowledge)
  VALIDATED:  +4 points (retrospective confirmed skill's recommendation)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal

# ── paths ────────────────────────────────────────────────────────────────────

_YOUK_ROOT = Path("/youk")
_STATE_DIR = _YOUK_ROOT / "state"
_SIGNALS_FILE = _STATE_DIR / "skill-signals.jsonl"
_POINTS_FILE = _STATE_DIR / "skill-points.json"

# ── types ────────────────────────────────────────────────────────────────────

SignalType = Literal["GAP", "SCOPE_MISS", "SURPLUS", "STABLE", "PRE_EMPTED", "VALIDATED"]

POINT_WEIGHTS: dict[SignalType, float] = {
    "GAP": -4.0,
    "SCOPE_MISS": -6.0,
    "SURPLUS": -2.0,
    "STABLE": 2.0,
    "PRE_EMPTED": 3.0,
    "VALIDATED": 4.0,
}

# Skills tracked by this system
_TRACKED_SKILLS = {"dev-loop", "code-review", "nfr-check", "challenge", "learn"}

# Skill starting budget
_STARTING_POINTS = 100.0
_FORK_THRESHOLD = 40.0


# ── examination surface parsing ──────────────────────────────────────────────

def _parse_examination_surfaces(audit_block: str) -> dict[str, dict[str, list[str]]]:
    """Extract [EXAMINATION SURFACE] blocks from an audit entry.

    Returns: {skill_name: {"examined": [...], "not_examined": [...]}}
    """
    surfaces: dict[str, dict[str, list[str]]] = {}
    pattern = re.compile(
        r"\[EXAMINATION SURFACE — ([^\]]+)\]\s*\n"
        r"(?:.*?:.*?\n)*?"
        r"Examined:\s*\[([^\]]*)\]\s*\n"
        r"Not examined:\s*\[([^\]]*)\]",
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(audit_block):
        raw_skill = m.group(1).strip()
        # Normalize: "dev-loop AUDIT" → "dev-loop", "code-review" → "code-review"
        skill = raw_skill.split()[0].lower().replace("_", "-")
        examined_raw = m.group(2).strip()
        not_examined_raw = m.group(3).strip()
        examined = [d.strip() for d in examined_raw.split(",") if d.strip()]
        # Not examined entries may have "domain — reason" format; extract domain only
        not_examined = []
        for item in not_examined_raw.split(","):
            item = item.strip()
            if item:
                domain = item.split("—")[0].strip()
                if domain:
                    not_examined.append(domain)
        surfaces[skill] = {"examined": examined, "not_examined": not_examined}
    return surfaces


# ── downstream finding extraction ────────────────────────────────────────────

def _extract_downstream_findings(audit_block: str) -> list[dict[str, str]]:
    """Extract HIGH/CRITICAL findings and their categories from the audit block.

    Returns list of {severity, category} dicts.
    """
    findings = []
    finding_pattern = re.compile(
        r"\[FINDING:\s*(CRITICAL|HIGH)\]\s+([^\n—–-]+)",
        re.MULTILINE,
    )
    for m in finding_pattern.finditer(audit_block):
        severity = m.group(1).strip()
        category_raw = m.group(2).strip()
        # Normalize category: "Error handling" → "error_handling"
        category = re.sub(r"[^a-z0-9]+", "_", category_raw.lower()).strip("_")
        findings.append({"severity": severity, "category": category})

    # Also read FindingCategories: line from audit structured fields
    cats_match = re.search(r"^FindingCategories:\s*(.+)$", audit_block, re.MULTILINE)
    if cats_match:
        for cat in cats_match.group(1).split(","):
            cat = cat.strip().lower().replace("-", "_").replace(" ", "_")
            if cat and not any(f["category"] == cat for f in findings):
                findings.append({"severity": "HIGH", "category": cat})

    return findings


# ── scope matrix lookup ───────────────────────────────────────────────────────

def _load_scope_matrix() -> dict:
    """Load skill-scope-matrix.yaml. Returns empty dict on any error."""
    try:
        import yaml  # type: ignore[import]
        matrix_path = (
            Path("/claude/skills/dev-loop/references/skill-scope-matrix.yaml")
        )
        if not matrix_path.exists():
            return {}
        with matrix_path.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _mandatory_domains(skill: str, task_type: str, matrix: dict) -> set[str]:
    """Return mandatory examination domains for a skill + task type."""
    try:
        skill_key = skill.replace("-", "_")
        return set(matrix[skill_key]["task_types"][task_type]["mandatory"])
    except (KeyError, TypeError):
        return set()


# ── signal computation ────────────────────────────────────────────────────────

def compute_signals_for_session(audit_block: str, session_n: int) -> list[dict]:
    """Compute skill signals from a single audit log session block.

    Returns list of signal dicts ready to append to skill-signals.jsonl.
    """
    signals: list[dict] = []
    now = datetime.now(UTC).isoformat()

    # Extract examination surfaces declared by skills this session
    surfaces = _parse_examination_surfaces(audit_block)

    # Extract downstream HIGH/CRITICAL findings (code-review, verify output in block)
    downstream_findings = _extract_downstream_findings(audit_block)

    # Extract autonomy depth signals
    autonomy_match = re.search(r"^AutonomyDepth:\s*(.+)$", audit_block, re.MULTILINE)
    autonomy_depth: dict[str, str] = {}
    if autonomy_match:
        for pair in autonomy_match.group(1).split(","):
            pair = pair.strip()
            if "=" in pair:
                sk, depth = pair.split("=", 1)
                autonomy_depth[sk.strip().lower().replace("_", "-")] = depth.strip().upper()

    # Extract loop correction
    loop_correction = bool(re.search(r"^LoopCorrection:\s*yes", audit_block, re.MULTILINE | re.IGNORECASE))

    # Extract retrospectives
    retro_matches = re.findall(r"- (.+?):\s*(VALIDATED|INVALIDATED)", audit_block)
    retrospectives = [{"decision": d.strip(), "outcome": o} for d, o in retro_matches]

    # Extract skills used
    skills_match = re.search(r"^Skills:\s*(.+)$", audit_block, re.MULTILINE)
    skills_used: list[str] = []
    if skills_match:
        raw = skills_match.group(1).strip()
        if raw.lower() != "none":
            skills_used = [s.strip().lower().replace("_", "-") for s in raw.split(",") if s.strip()]

    # Extract task type — prefer explicit TaskType: line written by session_end,
    # fall back to size-based heuristic for old audit entries.
    task_type = "other"
    task_type_match = re.search(r"^TaskType:\s*(\w+)$", audit_block, re.MULTILINE)
    if task_type_match:
        task_type = task_type_match.group(1).strip()
    else:
        checkpoint_match = re.search(r"TaskCheckpoints:.*?\(([A-Z]+)\)", audit_block)
        if checkpoint_match:
            size = checkpoint_match.group(1)
            task_type = "new_endpoint" if size in ("L", "XL") else "other"

    matrix = _load_scope_matrix()

    # ── per-skill signal computation ──────────────────────────────────────────

    for skill in _TRACKED_SKILLS:
        if skill not in skills_used and skill not in surfaces:
            continue  # skill didn't fire this session — no signal

        surface = surfaces.get(skill, {})
        examined = set(surface.get("examined", []))
        not_examined_declared = set(surface.get("not_examined", []))

        # ── SURPLUS: developer pre-empted at DEEP ────────────────────────────
        depth = autonomy_depth.get(skill, "")
        if depth in ("DEEP", "ELITE"):
            signals.append({
                "session_n": session_n,
                "skill": skill,
                "signal_type": "SURPLUS",
                "dimension": f"autonomy_{depth.lower()}",
                "evidence": f"developer pre-empted {skill} at {depth} depth",
                "weight": POINT_WEIGHTS["SURPLUS"],
                "recorded_at": now,
            })
            signals.append({
                "session_n": session_n,
                "skill": skill,
                "signal_type": "PRE_EMPTED",
                "dimension": f"autonomy_{depth.lower()}",
                "evidence": f"developer pre-empted {skill} — knowledge transferred",
                "weight": POINT_WEIGHTS["PRE_EMPTED"],
                "recorded_at": now,
            })
            continue  # pre-emption overrides GAP/SCOPE_MISS for this skill this session

        # ── GAP and SCOPE_MISS: downstream finding attribution ────────────────
        if downstream_findings and examined:
            for finding in downstream_findings:
                category = finding["category"]
                if category in examined:
                    # Skill examined this domain but missed the finding
                    signals.append({
                        "session_n": session_n,
                        "skill": skill,
                        "signal_type": "GAP",
                        "dimension": category,
                        "evidence": f"{skill} examined {category} but downstream found {finding['severity']}",
                        "weight": POINT_WEIGHTS["GAP"],
                        "recorded_at": now,
                    })
                elif category not in not_examined_declared:
                    # Downstream found something in a domain skill never declared examining
                    mandatory = _mandatory_domains(skill, task_type, matrix)
                    is_mandatory = category in mandatory
                    signals.append({
                        "session_n": session_n,
                        "skill": skill,
                        "signal_type": "SCOPE_MISS",
                        "dimension": category,
                        "evidence": (
                            f"{skill} never declared examining {category} "
                            f"({'mandatory' if is_mandatory else 'conditional'} for {task_type}); "
                            f"downstream found {finding['severity']}"
                        ),
                        "weight": POINT_WEIGHTS["SCOPE_MISS"],
                        "recorded_at": now,
                    })

        # ── loop_correction: challenge accuracy signal ────────────────────────
        if skill == "challenge" and loop_correction:
            signals.append({
                "session_n": session_n,
                "skill": "challenge",
                "signal_type": "GAP",
                "dimension": "loop_correction",
                "evidence": "challenge verdict required post-hoc correction",
                "weight": POINT_WEIGHTS["GAP"],
                "recorded_at": now,
            })

        # ── VALIDATED retrospective: skill recommendation confirmed ──────────
        if retrospectives and skill in skills_used:
            validated_count = sum(1 for r in retrospectives if r["outcome"] == "VALIDATED")
            if validated_count > 0:
                signals.append({
                    "session_n": session_n,
                    "skill": skill,
                    "signal_type": "VALIDATED",
                    "dimension": "retrospective",
                    "evidence": f"{validated_count} retrospective(s) VALIDATED this session",
                    "weight": POINT_WEIGHTS["VALIDATED"],
                    "recorded_at": now,
                })

        # ── STABLE: skill ran, no deductions, no surplus ─────────────────────
        has_deduction = any(
            s["skill"] == skill and s["signal_type"] in ("GAP", "SCOPE_MISS", "SURPLUS")
            for s in signals
        )
        if not has_deduction and skill in skills_used:
            signals.append({
                "session_n": session_n,
                "skill": skill,
                "signal_type": "STABLE",
                "dimension": "overall",
                "evidence": "skill output survived session with no downstream deductions",
                "weight": POINT_WEIGHTS["STABLE"],
                "recorded_at": now,
            })

    return signals


# ── pattern detection ─────────────────────────────────────────────────────────

def detect_patterns(signals_file: Path = _SIGNALS_FILE, window: int = 10) -> list[dict]:
    """Detect improvement-ready patterns in skill-signals.jsonl.

    Returns list of patterns where same skill-dimension shows 3+ GAP or
    SCOPE_MISS signals in the last `window` sessions.

    Each pattern: {skill, signal_type, dimension, count, sessions, evidence_samples}
    """
    if not signals_file.exists():
        return []

    all_signals: list[dict] = []
    try:
        with signals_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    all_signals.append(json.loads(line))
    except Exception:
        return []

    # Get last `window` distinct session numbers
    session_ns = sorted({s["session_n"] for s in all_signals}, reverse=True)[:window]
    recent = [s for s in all_signals if s["session_n"] in session_ns]

    # Count by (skill, signal_type, dimension)
    counts: dict[tuple, list[dict]] = {}
    for sig in recent:
        if sig["signal_type"] not in ("GAP", "SCOPE_MISS", "SURPLUS"):
            continue
        key = (sig["skill"], sig["signal_type"], sig["dimension"])
        counts.setdefault(key, []).append(sig)

    patterns = []
    for (skill, signal_type, dimension), occurrences in counts.items():
        if len(occurrences) >= 3:
            patterns.append({
                "skill": skill,
                "signal_type": signal_type,
                "dimension": dimension,
                "count": len(occurrences),
                "sessions": [o["session_n"] for o in occurrences],
                "evidence_samples": [o["evidence"] for o in occurrences[:3]],
            })

    # Sort: SCOPE_MISS first (highest penalty), then GAP, then SURPLUS
    priority = {"SCOPE_MISS": 0, "GAP": 1, "SURPLUS": 2}
    patterns.sort(key=lambda p: (priority.get(p["signal_type"], 3), -p["count"]))

    return patterns


# ── point ledger ──────────────────────────────────────────────────────────────

def _load_points() -> dict[str, dict]:
    """Load skill point ledger. Initializes missing skills to starting budget."""
    if not _POINTS_FILE.exists():
        return {}
    try:
        return json.loads(_POINTS_FILE.read_text())
    except Exception:
        return {}


def _save_points(ledger: dict[str, dict]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _POINTS_FILE.write_text(json.dumps(ledger, indent=2))


def update_points(signals: list[dict]) -> dict[str, float]:
    """Apply signal weights to the skill point ledger.

    Returns {skill: new_points} for all skills touched this session.
    """
    ledger = _load_points()
    touched: dict[str, float] = {}

    for sig in signals:
        skill = sig["skill"]
        if skill not in ledger:
            ledger[skill] = {
                "points": _STARTING_POINTS,
                "deductions": [],
                "recoveries": [],
            }

        weight = sig.get("weight", 0.0)
        entry = {
            "session_n": sig["session_n"],
            "signal_type": sig["signal_type"],
            "dimension": sig["dimension"],
            "amount": abs(weight),
            "recorded_at": sig["recorded_at"],
        }

        if weight < 0:
            ledger[skill]["deductions"].append(entry)
            ledger[skill]["points"] = max(0.0, ledger[skill]["points"] + weight)
        elif weight > 0:
            ledger[skill]["recoveries"].append(entry)
            ledger[skill]["points"] = min(_STARTING_POINTS, ledger[skill]["points"] + weight)

        # Keep only last 50 entries per list to bound file size
        ledger[skill]["deductions"] = ledger[skill]["deductions"][-50:]
        ledger[skill]["recoveries"] = ledger[skill]["recoveries"][-50:]

        touched[skill] = ledger[skill]["points"]

    _save_points(ledger)
    return touched


def get_fork_candidates(points_file: Path = _POINTS_FILE) -> list[dict]:
    """Return skills at or below the fork threshold."""
    ledger = _load_points()
    candidates = []
    for skill, data in ledger.items():
        if data["points"] <= _FORK_THRESHOLD:
            candidates.append({
                "skill": skill,
                "points": data["points"],
                "recent_deductions": data["deductions"][-10:],
            })
    return sorted(candidates, key=lambda c: c["points"])


def get_skill_health_summary(points_file: Path = _POINTS_FILE) -> dict:
    """Return health summary for all tracked skills."""
    ledger = _load_points()
    summary = {}
    for skill in _TRACKED_SKILLS:
        data = ledger.get(skill, {"points": _STARTING_POINTS, "deductions": [], "recoveries": []})
        points = data["points"]
        if points >= 80:
            status = "healthy"
        elif points >= 60:
            status = "degrading"
        elif points >= _FORK_THRESHOLD:
            status = "at_risk"
        else:
            status = "fork_candidate"
        summary[skill] = {"points": points, "status": status}
    return summary


# ── session integration ───────────────────────────────────────────────────────

def record_session_signals(audit_block: str, session_n: int) -> dict:
    """Top-level function called from session_end(). Silent-fail.

    Computes signals, appends to jsonl, updates point ledger.
    Returns summary dict (informational only — never raises).
    """
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        signals = compute_signals_for_session(audit_block, session_n)
        if not signals:
            return {"signals_recorded": 0, "points_updated": {}}

        # Append to rolling jsonl
        with _SIGNALS_FILE.open("a") as f:
            for sig in signals:
                f.write(json.dumps(sig) + "\n")

        # Update point ledger
        touched = update_points(signals)

        # Check for fork candidates and patterns (informational — written to state, not surfaced)
        patterns = detect_patterns()
        improvement_queue = _STATE_DIR / "skill-improvement-queue.json"
        if patterns:
            improvement_queue.write_text(json.dumps({"patterns": patterns, "updated_at": datetime.now(UTC).isoformat()}, indent=2))

        fork_candidates = get_fork_candidates()
        if fork_candidates:
            fork_file = _STATE_DIR / "skill-fork-candidates.json"
            fork_file.write_text(json.dumps({"candidates": fork_candidates, "updated_at": datetime.now(UTC).isoformat()}, indent=2))

        # Phase 3a: auto-feed bandit reward for any active candidate competition.
        # Reward = sum of signal weights for each skill this session.
        # task_type extracted from audit block for context vector.
        _task_type_match = re.search(r"^TaskType:\s*(\w+)$", audit_block, re.MULTILINE)
        _session_task_type = _task_type_match.group(1).strip() if _task_type_match else "other"

        # Extract Dreyfus stage from CognitiveAssessment line for bandit context vector.
        _dev_stage = "COMPETENT"
        _cog_match = re.search(r"CognitiveAssessment:.*?Dreyfus[^|]*?:\s*(\w+)", audit_block, re.IGNORECASE)
        if _cog_match:
            _raw_stage = _cog_match.group(1).strip().upper()
            _valid = {"NOVICE", "ADVANCED_BEGINNER", "COMPETENT", "PROFICIENT", "EXPERT"}
            if _raw_stage in _valid:
                _dev_stage = _raw_stage

        _candidates = _load_candidates()
        for skill, entry in _candidates.items():
            if entry.get("status") != "competing":
                continue
            skill_signals_this_session = [s for s in signals if s["skill"] == skill]
            if not skill_signals_this_session:
                continue
            net_reward = sum(s["weight"] for s in skill_signals_this_session)
            # Determine which arm was selected this session (default: current arm 0)
            _arm_index = 0
            selections = entry.get("arm_selections", [])
            if selections and selections[-1].get("session_n") == session_n:
                _arm_index = selections[-1].get("arm", 0)
            record_arm_reward(
                skill_name=skill,
                arm_index=_arm_index,
                reward=net_reward,
                task_type=_session_task_type,
                developer_stage=_dev_stage,
                session_n=session_n,
            )

        # Phase 3b: auto-fork any skill that crossed the threshold this session
        fork_results = check_fork_threshold_and_maybe_fork(session_n)

        return {
            "signals_recorded": len(signals),
            "points_updated": touched,
            "patterns_ready": len(patterns),
            "fork_candidates": [c["skill"] for c in fork_candidates],
            "newly_forked": [r["candidate_id"] for r in fork_results if r.get("forked")],
        }
    except Exception:
        return {"signals_recorded": 0, "points_updated": {}, "error": "silent_fail"}


# ── Phase 2: proposal generation ─────────────────────────────────────────────

_SKILL_ROOT = Path("/claude/skills")
_IMPROVEMENT_QUEUE = _STATE_DIR / "skill-improvement-queue.json"
_APPLIED_PROPOSALS = _STATE_DIR / "applied-proposals.json"


def _load_skill_md(skill_name: str) -> str:
    """Load SKILL.md content for a skill. Returns empty string on failure."""
    skill_path = _SKILL_ROOT / skill_name / "SKILL.md"
    try:
        return skill_path.read_text()
    except Exception:
        return ""


def _load_signal_evidence(skill_name: str, dimension: str, window: int = 10) -> list[dict]:
    """Load recent signals for skill+dimension for use in proposal evidence."""
    if not _SIGNALS_FILE.exists():
        return []
    try:
        signals = []
        with _SIGNALS_FILE.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                if s["skill"] == skill_name and (not dimension or s["dimension"] == dimension):
                    if s["signal_type"] in ("GAP", "SCOPE_MISS", "SURPLUS"):
                        signals.append(s)
        # Return last 10, sorted by session_n
        return sorted(signals, key=lambda x: x["session_n"])[-window:]
    except Exception:
        return []


def _mdl_check(before_lines: int, after_lines: int, signal_type: str) -> dict:
    """Minimal Description Length gate: additions must be justified by severity."""
    added = max(0, after_lines - before_lines)
    removed = max(0, before_lines - after_lines)
    severity_budget = {"SCOPE_MISS": 18, "GAP": 12, "SURPLUS": 0}
    budget = severity_budget.get(signal_type, 12)
    passes = (removed + added == 0) or (removed > 0) or (added <= budget)
    return {
        "lines_added": added,
        "lines_removed": removed,
        "net": after_lines - before_lines,
        "passes": passes,
        "verdict": "PASS" if passes else f"FAIL — {added} lines added exceeds {budget}-line budget for {signal_type}",
    }


def generate_improvement_proposal(skill_name: str, dimension: str = "") -> dict:
    """Generate a 5-part evaluable skill improvement proposal.

    Reads improvement queue, loads SKILL.md, constructs the 5-part proposal format,
    queues it via add_proposal (requires human approval), and records it in
    applied-proposals.json tracking.

    Returns: {proposal_id, proposal_text, queued, pattern_used, no_pattern (bool)}
    """
    # Load improvement queue
    queue_data: dict = {}
    if _IMPROVEMENT_QUEUE.exists():
        try:
            queue_data = json.loads(_IMPROVEMENT_QUEUE.read_text())
        except Exception:
            pass

    patterns = queue_data.get("patterns", [])
    # Filter to skill and optionally dimension
    matching = [
        p for p in patterns
        if p["skill"] == skill_name and (not dimension or p["dimension"] == dimension)
    ]
    if not matching:
        return {"no_pattern": True, "skill": skill_name, "dimension": dimension}

    # Pick highest-priority pattern (already sorted SCOPE_MISS > GAP > SURPLUS)
    pattern = matching[0]
    signal_type = pattern["signal_type"]
    dim = pattern["dimension"]
    count = pattern["count"]
    sessions = pattern.get("sessions", [])[:3]
    evidence_samples = pattern.get("evidence_samples", [])[:3]

    # Load signal evidence with detail
    recent_signals = _load_signal_evidence(skill_name, dim)

    # Load current SKILL.md
    skill_md = _load_skill_md(skill_name)
    skill_md_lines = len(skill_md.splitlines()) if skill_md else 0

    # Estimate proposed change scope based on signal type
    if signal_type == "SCOPE_MISS":
        proposed_change = (
            f"Add '{dim}' to the examination surface declaration in the AUDIT phase. "
            f"Include it in the [EXAMINATION SURFACE] block output so downstream skills "
            f"can attribute findings correctly."
        )
        assumption = f"The '{dim}' domain is consistently relevant to the task types that triggered this signal."
        wrong_assumption = (
            f"If '{dim}' only arose in one-off task variants, adding it to the default surface "
            f"over-declares scope for routine tasks."
        )
        proposed_lines = skill_md_lines + 4
    elif signal_type == "GAP":
        proposed_change = (
            f"Strengthen the '{dim}' examination checklist: add a specific sub-check that "
            f"downstream findings indicate was missed. "
            f"Consult the evidence samples to identify the recurring failure pattern."
        )
        assumption = f"The downstream findings share a root cause in how '{dim}' is currently examined — not in task-specific edge cases."
        wrong_assumption = (
            f"If each GAP instance arose from a different root cause, adding a single checklist item "
            f"won't address future misses in '{dim}'."
        )
        proposed_lines = skill_md_lines + 6
    else:  # SURPLUS
        proposed_change = (
            f"Compress the '{dim}' ceremony: remove or condense scaffolding that the developer "
            f"consistently pre-empts at DEEP. The skill should acknowledge this transfer has happened "
            f"and abbreviate the dimension."
        )
        assumption = f"The developer's pre-emption of '{dim}' is stable, not session-specific."
        wrong_assumption = "If pre-emption was during an unusual run of similar tasks, compressing now loses coverage for future task variety."
        proposed_lines = max(0, skill_md_lines - 4)

    mdl = _mdl_check(skill_md_lines, proposed_lines, signal_type)

    # Points at stake
    weight = abs(POINT_WEIGHTS.get(signal_type, 4.0))
    current_points = _STARTING_POINTS  # default; will be read from ledger if available
    try:
        ledger = json.loads(_POINTS_FILE.read_text()) if _POINTS_FILE.exists() else {}
        current_points = ledger.get(skill_name, {}).get("points", _STARTING_POINTS)
    except Exception:
        pass

    # Build 5-part proposal text
    evidence_lines = "\n".join(
        f"  Session #{sig['session_n']}: {sig['evidence']}"
        for sig in recent_signals[:3]
    ) or "\n".join(
        f"  Session #{sn}: {ev}"
        for sn, ev in zip(sessions, evidence_samples)
    ) or "  (no detailed evidence available — check skill-signals.jsonl)"

    proposal_id = f"SKILL-SIGNAL-{skill_name.upper()}-{dim.upper().replace('_', '-')}"
    proposal_text = (
        f"[SKILL SIGNAL — {skill_name} / {dim}]\n"
        f"Sessions observed: {', '.join(f'#{n}' for n in sessions)} ({count} of last 10)\n"
        f"Signal type: {signal_type}\n"
        f"Current points: {current_points:.0f} / {_STARTING_POINTS:.0f}\n"
        f"Points at stake: −{weight:.0f} per session if unaddressed\n"
        f"\nWhat happened:\n{evidence_lines}\n"
        f"\nProposed change:\n  {skill_name} — {proposed_change}\n"
        f"\nAssumption:\n  {assumption}\n"
        f"\nIf assumption is wrong:\n  {wrong_assumption}\n"
        f"  → Reject if: the dimension appears in <20% of task types for this skill.\n"
        f"\nIf we do nothing:\n"
        f"  Points trajectory: {current_points:.0f} → {max(0, current_points - weight * 5):.0f} over next 5 sessions.\n"
        f"\nMDL check: {mdl['lines_added']} added, {mdl['lines_removed']} removed. "
        f"Net: {mdl['net']:+d} lines. Verdict: {mdl['verdict']}\n"
        f"\nApprove (A) / Reject (R) / Defer to session #{sessions[-1] + 5 if sessions else '?'} (D):"
    )

    # Queue via add_proposal
    queued = False
    queued_error = ""
    try:
        import sys as _sys
        _sys.path.insert(0, "/shared")
        from models import Proposal
        from health import add_proposal as _add_proposal_fn

        skill_md_path = str(_SKILL_ROOT / skill_name / "SKILL.md")
        proposal = Proposal(
            id=proposal_id,
            target=skill_md_path,
            change_description=f"{signal_type} pattern in '{dim}' for {skill_name} — {count} occurrences",
            reason=f"Signal detector found {count}× {signal_type} in '{dim}' over last 10 sessions. "
                   f"Points at stake: −{weight:.0f}/session.",
            before=f"Current {skill_name} SKILL.md ({skill_md_lines} lines)",
            after=proposed_change,
            status="PENDING",
            proposed_date=datetime.now(UTC).strftime("%Y-%m-%d"),
            change_type="SKILL_EDIT",
            target_section=dim,
            content=proposal_text,
            review_required=True,
        )
        _add_proposal_fn(proposal)
        queued = True
    except Exception as e:
        queued_error = str(e)

    # Record in applied-proposals tracking for falsifier monitor (Phase 4)
    tracking: dict = {}
    if _APPLIED_PROPOSALS.exists():
        try:
            tracking = json.loads(_APPLIED_PROPOSALS.read_text())
        except Exception:
            pass
    pending_key = f"pending:{proposal_id}"
    tracking[pending_key] = {
        "proposal_id": proposal_id,
        "skill": skill_name,
        "dimension": dim,
        "signal_type": signal_type,
        "status": "QUEUED",
        "queued_at": datetime.now(UTC).isoformat(),
        "falsifier_condition": (
            f"After applying this proposal, if '{dim}' GAP/SCOPE_MISS signals continue "
            f"at the same rate for 3+ sessions, the proposal failed."
        ),
        "falsifier_sessions_to_watch": 3,
        "sessions_since_applied": 0,
        "post_signals": [],
    }
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _APPLIED_PROPOSALS.write_text(json.dumps(tracking, indent=2))
    except Exception:
        pass

    return {
        "proposal_id": proposal_id,
        "proposal_text": proposal_text,
        "queued": queued,
        "queued_error": queued_error if not queued else "",
        "pattern_used": pattern,
        "mdl_check": mdl,
        "no_pattern": False,
    }


# ── Phase 4: falsifier monitor ────────────────────────────────────────────────

def check_falsifier_conditions(session_n: int) -> list[dict]:
    """Check applied/queued proposals for falsifier conditions firing.

    Called from session_start(). Returns list of alerts for proposals where
    the post-application signal rate has not improved after N sessions.

    Each alert: {proposal_id, skill, dimension, signal_type, verdict, sessions_watched}
    """
    if not _APPLIED_PROPOSALS.exists():
        return []

    try:
        tracking = json.loads(_APPLIED_PROPOSALS.read_text())
    except Exception:
        return []

    alerts = []
    updated = False

    for key, entry in list(tracking.items()):
        if entry.get("status") not in ("APPLIED",):
            continue  # only watch applied proposals, not queued/rejected

        sessions_to_watch = entry.get("falsifier_sessions_to_watch", 3)

        # Load post-application signals for this skill/dimension
        post_signals = _load_signal_evidence(entry["skill"], entry["dimension"])
        # Only count signals after application
        applied_session = entry.get("applied_session_n", 0)
        post = [s for s in post_signals if s["session_n"] > applied_session]

        entry["sessions_since_applied"] = session_n - applied_session
        entry["post_signals"] = [s["signal_type"] for s in post]
        updated = True

        if entry["sessions_since_applied"] < sessions_to_watch:
            continue  # not enough data yet

        # Falsifier fires if same signal type continues at ≥ same rate
        original_count = entry.get("original_pattern_count", 3)
        post_gap_count = sum(1 for s in post if s["signal_type"] in ("GAP", "SCOPE_MISS"))

        if post_gap_count >= original_count:
            alerts.append({
                "proposal_id": entry["proposal_id"],
                "skill": entry["skill"],
                "dimension": entry["dimension"],
                "signal_type": entry["signal_type"],
                "verdict": "FALSIFIED",
                "sessions_watched": entry["sessions_since_applied"],
                "post_gap_count": post_gap_count,
                "message": (
                    f"Proposal {entry['proposal_id']} FALSIFIED: "
                    f"'{entry['dimension']}' still showing {post_gap_count} "
                    f"{entry['signal_type']} signals after {entry['sessions_since_applied']} sessions. "
                    f"Consider reverting or escalating to a deeper skill redesign."
                ),
            })
            entry["status"] = "FALSIFIED"
        elif post_gap_count == 0 and entry["sessions_since_applied"] >= sessions_to_watch:
            entry["status"] = "CONFIRMED"

    if updated:
        try:
            _APPLIED_PROPOSALS.write_text(json.dumps(tracking, indent=2))
        except Exception:
            pass

    return alerts


def mark_proposal_applied(proposal_id: str, session_n: int) -> bool:
    """Mark a queued proposal as applied. Called after apply_proposal succeeds.

    Updates applied-proposals.json so the falsifier monitor can watch it.
    Returns True if the proposal was found and updated.
    """
    if not _APPLIED_PROPOSALS.exists():
        return False
    try:
        tracking = json.loads(_APPLIED_PROPOSALS.read_text())
    except Exception:
        return False

    # Could be stored under "pending:{id}" key
    pending_key = f"pending:{proposal_id}"
    entry = tracking.get(pending_key) or tracking.get(proposal_id)
    if not entry:
        return False

    entry["status"] = "APPLIED"
    entry["applied_session_n"] = session_n
    entry["original_pattern_count"] = entry.get("original_pattern_count", 3)
    # Re-key without "pending:" prefix
    tracking.pop(pending_key, None)
    tracking[proposal_id] = entry

    try:
        _APPLIED_PROPOSALS.write_text(json.dumps(tracking, indent=2))
        return True
    except Exception:
        return False


# ── Phase 3: candidate competition (LinUCB bandit) ────────────────────────────

_CANDIDATES_FILE = _STATE_DIR / "skill-candidates.json"
_ARCHIVE_DIR = _STATE_DIR / "skill-archives"

# LinUCB alpha: exploration-exploitation tradeoff. Higher = more exploration.
_LINUCB_ALPHA = 1.0

# Context features for LinUCB arm selection
_CONTEXT_FEATURES = ["task_type_encoded", "developer_stage_encoded"]
_TASK_TYPE_MAP = {
    "new_endpoint": 1, "schema_change": 2, "ui_component": 3,
    "bug_fix": 4, "refactor": 5, "llm_integration": 6, "background_job": 7, "other": 0,
}
_STAGE_MAP = {"NOVICE": 0, "ADVANCED_BEGINNER": 1, "COMPETENT": 2, "PROFICIENT": 3, "EXPERT": 4}


def _context_vector(task_type: str, developer_stage: str) -> list[float]:
    tt = _TASK_TYPE_MAP.get(task_type, 0) / 7.0
    stage = _STAGE_MAP.get(developer_stage, 2) / 4.0
    return [1.0, tt, stage]  # bias + 2 features


def _linucb_select(arm_stats: list[dict], context: list[float], alpha: float = _LINUCB_ALPHA) -> int:
    """LinUCB arm selection. Returns index of selected arm (0=current, 1=candidate).

    Each arm_stat: {theta: [float], A_inv: [[float]]} (ridge regression state).
    Falls back to arm 0 (current) on any error.
    """
    import math
    try:
        best_idx = 0
        best_ucb = -float("inf")
        d = len(context)
        for i, arm in enumerate(arm_stats):
            theta = arm.get("theta", [0.0] * d)
            A_inv = arm.get("A_inv", [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)])
            # UCB = x^T θ + alpha * sqrt(x^T A^{-1} x)
            mean = sum(context[j] * theta[j] for j in range(d))
            variance = sum(
                context[r] * A_inv[r][c] * context[c]
                for r in range(d) for c in range(d)
            )
            ucb = mean + alpha * math.sqrt(max(0.0, variance))
            if ucb > best_ucb:
                best_ucb = ucb
                best_idx = i
        return best_idx
    except Exception:
        return 0  # default to current version


def _linucb_update(arm_stat: dict, context: list[float], reward: float) -> dict:
    """Update LinUCB arm statistics with new (context, reward) observation."""
    try:
        d = len(context)
        A = arm_stat.get("A", [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)])

        # A += x x^T
        for r in range(d):
            for c in range(d):
                A[r][c] += context[r] * context[c]

        # b += r * x  (stored as b vector)
        b = arm_stat.get("b", [0.0] * d)
        for j in range(d):
            b[j] += reward * context[j]

        # θ = A^{-1} b  (3x3 inversion — small enough for direct computation)
        def inv3(m: list[list[float]]) -> list[list[float]]:
            det = (
                m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
            )
            if abs(det) < 1e-12:
                return [[1.0 if r == c else 0.0 for c in range(3)] for r in range(3)]
            inv = [[0.0] * 3 for _ in range(3)]
            inv[0][0] = (m[1][1] * m[2][2] - m[1][2] * m[2][1]) / det
            inv[0][1] = (m[0][2] * m[2][1] - m[0][1] * m[2][2]) / det
            inv[0][2] = (m[0][1] * m[1][2] - m[0][2] * m[1][1]) / det
            inv[1][0] = (m[1][2] * m[2][0] - m[1][0] * m[2][2]) / det
            inv[1][1] = (m[0][0] * m[2][2] - m[0][2] * m[2][0]) / det
            inv[1][2] = (m[0][2] * m[1][0] - m[0][0] * m[1][2]) / det
            inv[2][0] = (m[1][0] * m[2][1] - m[1][1] * m[2][0]) / det
            inv[2][1] = (m[0][1] * m[2][0] - m[0][0] * m[2][1]) / det
            inv[2][2] = (m[0][0] * m[1][1] - m[0][1] * m[1][0]) / det
            return inv

        A_inv = inv3(A) if d == 3 else [[1.0 if r == c else 0.0 for c in range(d)] for r in range(d)]
        new_theta = [sum(A_inv[r][c] * b[c] for c in range(d)) for r in range(d)]

        return {"theta": new_theta, "A": A, "A_inv": A_inv, "b": b}
    except Exception:
        return arm_stat  # return unchanged on error


def _load_candidates() -> dict:
    """Load skill candidate registry. Returns {} on failure."""
    if not _CANDIDATES_FILE.exists():
        return {}
    try:
        return json.loads(_CANDIDATES_FILE.read_text())
    except Exception:
        return {}


def _save_candidates(candidates: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _CANDIDATES_FILE.write_text(json.dumps(candidates, indent=2))


def fork_skill(skill_name: str, gap_history: list[dict], session_n: int) -> dict:
    """Archive the current skill version and register a candidate at 70 points.

    Called when a skill drops to or below the fork threshold (40 points).
    The candidate starts at 70 points and competes with the archived current version
    via LinUCB selection over the next 5 sessions.

    Returns: {forked: bool, candidate_id, archive_path}
    """
    candidates = _load_candidates()

    # Don't fork if a candidate already exists for this skill
    if skill_name in candidates:
        return {
            "forked": False,
            "reason": f"Candidate already exists for {skill_name}",
            "candidate_id": candidates[skill_name].get("candidate_id"),
        }

    # Archive current SKILL.md
    skill_md = _load_skill_md(skill_name)
    archive_path = ""
    if skill_md:
        try:
            _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            archive_file = _ARCHIVE_DIR / f"{skill_name}-{ts}.md"
            archive_file.write_text(skill_md)
            archive_path = str(archive_file)
        except Exception:
            pass

    candidate_id = f"{skill_name}-candidate-{session_n}"
    d = 3  # context vector dimension

    # Initialize LinUCB arm statistics for both arms
    def identity(size: int) -> list[list[float]]:
        return [[1.0 if r == c else 0.0 for c in range(size)] for r in range(size)]

    arm_template = {"theta": [0.0] * d, "A": identity(d), "A_inv": identity(d), "b": [0.0] * d}

    candidates[skill_name] = {
        "candidate_id": candidate_id,
        "skill": skill_name,
        "forked_at_session": session_n,
        "archive_path": archive_path,
        "candidate_points": 70.0,  # start candidate at 70, not 100
        "current_arm": "archived",  # "archived" = current SKILL.md before fork
        "candidate_arm": "candidate",  # generated from gap history — queued as proposal
        "sessions_competed": 0,
        "promote_after_sessions": 5,
        "arm_stats": [arm_template.copy(), arm_template.copy()],  # [current, candidate]
        "arm_selections": [],  # log: [{session_n, arm, reward}]
        "gap_history_summary": [g.get("evidence", "") for g in gap_history[:5]],
        "status": "competing",
        "created_at": datetime.now(UTC).isoformat(),
    }
    _save_candidates(candidates)

    return {
        "forked": True,
        "candidate_id": candidate_id,
        "archive_path": archive_path,
        "note": (
            f"{skill_name} forked at session #{session_n}. "
            f"Run generate_skill_improvement_proposal('{skill_name}') to produce the candidate version. "
            f"The candidate competes with the archived version for {5} sessions via LinUCB."
        ),
    }


def select_skill_arm(
    skill_name: str,
    task_type: str = "other",
    developer_stage: str = "COMPETENT",
) -> dict:
    """LinUCB arm selection: returns which skill version to use for this task.

    Returns: {arm: "current"|"candidate", candidate_id, reason}
    If no candidate exists, always returns "current".
    """
    candidates = _load_candidates()
    if skill_name not in candidates:
        return {"arm": "current", "reason": "no candidate"}

    entry = candidates[skill_name]
    if entry.get("status") != "competing":
        return {"arm": "current", "reason": f"competition {entry.get('status', 'unknown')}"}

    context = _context_vector(task_type, developer_stage)
    arm_stats = entry.get("arm_stats", [{}, {}])
    selected = _linucb_select(arm_stats, context)

    arm_name = "candidate" if selected == 1 else "current"
    return {
        "arm": arm_name,
        "candidate_id": entry["candidate_id"],
        "arm_index": selected,
        "reason": f"LinUCB selected arm {selected} for task_type={task_type}, stage={developer_stage}",
    }


def record_arm_reward(
    skill_name: str,
    arm_index: int,
    reward: float,
    task_type: str = "other",
    developer_stage: str = "COMPETENT",
    session_n: int = 0,
) -> dict:
    """Update LinUCB arm statistics after observing a reward signal.

    reward: positive = skill output survived; negative = downstream deduction.
    Called from update_points() when signals arrive for a skill with an active candidate.
    Returns: {updated, promoted, reverted}
    """
    candidates = _load_candidates()
    if skill_name not in candidates:
        return {"updated": False}

    entry = candidates[skill_name]
    if entry.get("status") != "competing":
        return {"updated": False}

    context = _context_vector(task_type, developer_stage)
    arm_stats = entry["arm_stats"]
    arm_stats[arm_index] = _linucb_update(arm_stats[arm_index], context, reward)
    entry["arm_stats"] = arm_stats
    entry["sessions_competed"] = entry.get("sessions_competed", 0) + 1
    entry["arm_selections"].append({
        "session_n": session_n,
        "arm": arm_index,
        "reward": reward,
    })

    result: dict = {"updated": True, "promoted": False, "reverted": False}

    # Promotion check: after promote_after_sessions, compare net reward trajectories
    if entry["sessions_competed"] >= entry["promote_after_sessions"]:
        arm0_rewards = [s["reward"] for s in entry["arm_selections"] if s["arm"] == 0]
        arm1_rewards = [s["reward"] for s in entry["arm_selections"] if s["arm"] == 1]
        net0 = sum(arm0_rewards) if arm0_rewards else 0.0
        net1 = sum(arm1_rewards) if arm1_rewards else 0.0

        if net1 > net0:
            # Candidate wins — promote
            entry["status"] = "promoted"
            entry["promotion_session"] = session_n
            result["promoted"] = True
            result["promotion_note"] = (
                f"{skill_name} candidate promoted at session #{session_n}. "
                f"Net reward: candidate={net1:.1f}, archived={net0:.1f}. "
                f"Apply the candidate proposal to make it the live version."
            )
        else:
            # Current (archived) wins — revert: candidate is dropped
            entry["status"] = "reverted"
            entry["reversion_session"] = session_n
            result["reverted"] = True
            result["reversion_note"] = (
                f"{skill_name} candidate reverted at session #{session_n}. "
                f"Net reward: archived={net0:.1f}, candidate={net1:.1f}. "
                f"The archived version outperformed — no action needed."
            )

    candidates[skill_name] = entry
    _save_candidates(candidates)
    return result


def check_fork_threshold_and_maybe_fork(session_n: int) -> list[dict]:
    """Check all skills against the fork threshold. Fork any that qualify.

    Called from record_session_signals() after update_points(). Returns list of
    fork results for skills that were newly forked this session.
    """
    ledger = _load_points()
    candidates = _load_candidates()
    results = []

    for skill, data in ledger.items():
        points = data.get("points", _STARTING_POINTS)
        # Only fork if below threshold AND no active candidate exists
        if points <= _FORK_THRESHOLD and skill not in candidates:
            gap_history = _load_signal_evidence(skill, "")
            result = fork_skill(skill, gap_history, session_n)
            results.append(result)

    return results


# ── domain-level audit signals ────────────────────────────────────────────────

_AUDIT_SIGNALS_FILE = _STATE_DIR / "audit-signals.jsonl"


def write_domain_signal(
    project_slug: str,
    session_n: int,
    skill: str,
    domain: str,
    severity: str,
    task_type: str = "",
) -> None:
    """Write a domain-level HIGH finding to audit-signals.jsonl (mid-session).

    Called after any AUDIT/ANALYZE phase produces ≥2 HIGH findings in a domain.
    Separate from skill-signals.jsonl — no double-count risk to org_score.
    Silent-fails so it never blocks the skill that calls it.
    """
    try:
        _AUDIT_SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "project": project_slug,
            "session": session_n,
            "skill": skill,
            "domain": domain,
            "severity": severity,
            "task_type": task_type,
        }
        with open(_AUDIT_SIGNALS_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def read_audit_patterns(
    project_slug: str,
    lookback_sessions: int = 5,
) -> list[dict]:
    """Return domains flagged HIGH in ≥40% of recent sessions for the project.

    Returns list of dicts: {domain, count, total, pct, skill, example_task_type}
    Called by session_start to surface recurring patterns before the developer writes code.
    Silent-fails to [] if file missing or malformed.
    """
    try:
        if not _AUDIT_SIGNALS_FILE.exists():
            return []

        lines = _AUDIT_SIGNALS_FILE.read_text().strip().splitlines()
        records = []
        for line in lines:
            try:
                r = json.loads(line)
                if r.get("project") == project_slug:
                    records.append(r)
            except Exception:
                continue

        if not records:
            return []

        # Get distinct sessions seen for this project (capped at lookback_sessions)
        sessions_seen = sorted({r["session"] for r in records}, reverse=True)
        recent_sessions = set(sessions_seen[:lookback_sessions])
        recent_records = [r for r in records if r["session"] in recent_sessions]
        total_sessions = len(recent_sessions)

        if total_sessions == 0:
            return []

        # Count per domain: how many distinct sessions had this domain flagged HIGH
        from collections import defaultdict
        domain_sessions: dict[str, set] = defaultdict(set)
        domain_skill: dict[str, str] = {}
        domain_task_type: dict[str, str] = {}

        for r in recent_records:
            if r.get("severity", "").upper() in ("HIGH", "CRITICAL"):
                domain = r["domain"]
                domain_sessions[domain].add(r["session"])
                domain_skill[domain] = r.get("skill", "")
                domain_task_type[domain] = r.get("task_type", "")

        threshold = 0.4  # 40% of recent sessions
        patterns = []
        for domain, sess_set in domain_sessions.items():
            count = len(sess_set)
            pct = count / total_sessions
            if pct >= threshold:
                patterns.append({
                    "domain": domain,
                    "count": count,
                    "total": total_sessions,
                    "pct": round(pct * 100),
                    "skill": domain_skill[domain],
                    "example_task_type": domain_task_type[domain],
                })

        return sorted(patterns, key=lambda x: -x["pct"])
    except Exception:
        return []
