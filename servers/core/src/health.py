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
        s["skills"] = [sk.strip() for sk in skills_match.group(1).split(",")] if skills_match else []
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
    return sessions


def _score_org(audit_texts: list[str]) -> float:
    if not audit_texts:
        return 5.0

    sessions = _parse_audit_sessions(audit_texts)
    if not sessions:
        return 5.0

    total = len(sessions)
    close_count = sum(1 for s in sessions if s["close_cluster"])
    tracked_count = sum(1 for s in sessions if s["skills"])

    close_rate = close_count / total
    tracked_rate = tracked_count / total

    # Token efficiency: sessions consistently >2× budget lose 1 point
    token_sessions = [s for s in sessions if s["tokens_ratio"] is not None]
    over_budget_count = sum(1 for s in token_sessions if s["tokens_ratio"] > 2.0)
    token_penalty = -1.0 if len(token_sessions) >= 2 and over_budget_count / max(len(token_sessions), 1) > 0.5 else 0.0

    score = 5.0 + (close_rate * 2.0) + (tracked_rate * 1.0) + token_penalty
    return min(round(score, 1), 10.0)


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
    skip_rate = 1 - (close_count / total)

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
        for candidate in ["code-review", "verify", "nfr-check"]:
            if skill_counts.get(candidate, 0) == 0:
                findings.append(f"Skill '{candidate}' not recorded in any of {total} sessions.")

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

    candidates = []
    for skill, occurrences in by_skill.items():
        count = len(occurrences)
        projects = {slug for slug, _ in occurrences if slug}
        if count >= 3:
            candidates.append({
                "skill": skill,
                "occurrence_count": count,
                "distinct_projects": len(projects),
                "sample_gaps": list({gap for _, gap in occurrences})[:3],
                "promotion_target": "cross-project.md" if len(projects) >= 2 else f"skills/{skill}/SKILL.md",
                "change_type": "FILE_CREATE" if len(projects) >= 2 else "SKILL_EDIT",
            })
    return sorted(candidates, key=lambda x: -x["occurrence_count"])


def _queue_promotion_proposals(candidates: list[dict]) -> int:
    """Auto-queue proposals for promotion candidates. Returns count queued."""
    from datetime import datetime
    queued = 0
    for c in candidates:
        proposal = Proposal(
            id=f"PENDING-PROMO-{c['skill'].upper()}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            target=c["promotion_target"],
            change_description=f"Promote recurring gap pattern: {c['skill']} ({c['occurrence_count']} occurrences across {c['distinct_projects']} project(s))",
            reason=(
                f"SkillGap '{c['skill']}' appeared {c['occurrence_count']} times in audit logs. "
                f"Sample gaps: {'; '.join(c['sample_gaps'])}. "
                "Review and expand the skill or add to cross-project.md."
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


def run_health_check_with_skill_signals() -> dict:
    """
    Extended health check that also returns skill gap signals for evolution
    and queues promotion proposals for skills with 3+ recurring gap occurrences.
    """
    report = run_health_check()
    audit_texts = _read_recent_audit_logs(days=60)
    skill_gap_signals = _parse_skill_gap_signals(audit_texts)

    # Auto-queue proposals for skills that have crossed the promotion threshold
    promotion_candidates = _analyze_promotion_candidates(audit_texts)
    promotion_queued = _queue_promotion_proposals(promotion_candidates) if promotion_candidates else 0

    base = {
        "org_score": report.org_score,
        "sessions_analyzed": report.sessions_analyzed,
        "findings": report.findings,
        "proposals": [p.to_dict() for p in report.proposals],
        "proposals_count": len(report.proposals),
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

    return base


def add_proposal(proposal: Proposal) -> None:
    """Append a new proposal to PENDING.md. Never auto-applies."""
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not PROPOSALS_FILE.exists():
        PROPOSALS_FILE.write_text("# youk Self-Heal Proposals\n\nPending founder review.\n\n")

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

    return {
        "applied": False,
        "error": f"Unknown change_type '{ct}'. Set a valid change_type on the proposal.",
    }


def apply_proposal(proposal_id: str, confirmed: bool) -> dict:
    """
    Two-step proposal application.
    confirmed=False → returns diff preview, nothing written.
    confirmed=True  → executes write per change_type, marks APPLIED in PENDING.md.
    """
    proposals = _load_pending_proposals()
    target = next((p for p in proposals if p.id == proposal_id), None)
    if not target:
        return {"applied": False, "error": f"Proposal {proposal_id} not found in PENDING.md"}

    if not confirmed:
        preview = _compute_diff_preview(target)
        return {
            "preview": preview,
            "blocked": False,
            "message": "Preview only — nothing written. Pass confirmed=True to apply.",
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
