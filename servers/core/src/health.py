from __future__ import annotations
import re
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import HealthReport, Proposal

CLAUDE_ROOT = Path("/claude")
YOUK_ROOT = Path("/youk")
AUDIT_DIR = CLAUDE_ROOT / "audit"
PROPOSALS_FILE = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"


def _read_recent_audit_logs(days: int = 30) -> list[str]:
    if not AUDIT_DIR.exists():
        return []
    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = []
    for f in sorted(AUDIT_DIR.glob("*.md")):
        try:
            # Parse YYYY-MM from filename
            parts = f.stem.split("-")
            if len(parts) == 2:
                file_date = datetime(int(parts[0]), int(parts[1]), 1)
                if file_date >= cutoff.replace(day=1):
                    entries.append(f.read_text())
        except (ValueError, IndexError):
            continue
    return entries


def _score_org(audit_texts: list[str]) -> float:
    if not audit_texts:
        return 5.0

    full_text = "\n".join(audit_texts)
    session_count = full_text.count("### Session —")

    if session_count == 0:
        return 5.0

    # Positive signals
    close_cluster = full_text.count("context-sync end") + full_text.count("FLUSHED")
    skill_invocations = len(re.findall(r"skill[s]? invoked", full_text, re.IGNORECASE))

    # Score: baseline 5, +1 per 50% session-close coverage, +1 for skill tracking
    close_rate = close_cluster / max(session_count, 1)
    score = 5.0 + (close_rate * 2.0) + (1.0 if skill_invocations > 0 else 0.0)
    return min(round(score, 1), 10.0)


def _generate_findings(audit_texts: list[str], score: float) -> list[str]:
    findings = []
    if not audit_texts:
        findings.append("No audit logs found — this is the first health check.")
        return findings

    full_text = "\n".join(audit_texts)
    session_count = full_text.count("### Session —")
    close_count = full_text.count("context-sync end") + full_text.count("FLUSHED")

    if session_count > 0:
        skip_rate = 1 - (close_count / session_count)
        if skip_rate > 0.5:
            findings.append(
                f"Session-close cluster skipped {skip_rate:.0%} of sessions "
                f"({close_count}/{session_count} completed). Stop hook should address this."
            )

    if score < 6.0:
        findings.append(
            "Org score below 6.0 — review which skills are being skipped and why."
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

        target = _extract_field(block, "Target")
        change = _extract_field(block, "Change")
        reason = _extract_field(block, "Reason")
        before = _extract_field(block, "Before")
        after = _extract_field(block, "After")
        status = _extract_field(block, "Status")

        proposals.append(Proposal(
            id=proposal_id,
            target=target,
            change_description=change,
            reason=reason,
            before=before,
            after=after,
            status=status,
            proposed_date=date,
        ))
    return proposals


def _extract_field(text: str, field_name: str) -> str:
    pattern = rf"\*\*{field_name}:\*\*\s*(.+)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


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


def add_proposal(proposal: Proposal) -> None:
    """Append a new proposal to PENDING.md. Never auto-applies."""
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not PROPOSALS_FILE.exists():
        PROPOSALS_FILE.write_text("# youk Self-Heal Proposals\n\nPending founder review.\n\n")

    with open(PROPOSALS_FILE, "a") as f:
        f.write("\n" + proposal.to_markdown())


def apply_proposal(proposal_id: str, confirmed: bool) -> dict:
    """Apply an approved proposal. confirmed=True is the hard-rule gate."""
    if not confirmed:
        raise ValueError(
            "Hard rule: no-auto-apply-proposals. "
            "Pass confirmed=True only when the founder has explicitly approved this proposal."
        )

    proposals = _load_pending_proposals()
    target = None
    for p in proposals:
        if p.id == proposal_id:
            target = p
            break

    if not target:
        return {"applied": False, "reason": f"Proposal {proposal_id} not found in PENDING.md"}

    # For now, apply_proposal marks the entry as APPLIED in PENDING.md
    # Full file-write logic is implemented per-target-type in Phase 2
    content = PROPOSALS_FILE.read_text()
    content = content.replace(
        f"**Status:** {target.status}",
        f"**Status:** APPLIED — {datetime.utcnow().strftime('%Y-%m-%d')}",
    )
    PROPOSALS_FILE.write_text(content)

    return {
        "applied": True,
        "target_file": target.target,
        "change_summary": target.change_description,
    }
