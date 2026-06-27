from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class TaskSize(str, Enum):
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class RuleType(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class ViolationType(str, Enum):
    BLOCK = "BLOCK"
    NUDGE = "NUDGE"
    SURFACE = "SURFACE"


@dataclass
class SoftRuleWarning:
    rule_id: str
    name: str
    message: str
    violation_type: ViolationType


@dataclass
class RoutingDecision:
    task: str
    size: TaskSize
    ceremony: str
    skills: list[str]
    nfr_mode: str
    warnings: list[SoftRuleWarning] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "size": self.size.value,
            "ceremony": self.ceremony,
            "skills": self.skills,
            "nfr_mode": self.nfr_mode,
            "warnings": [
                {"rule_id": w.rule_id, "name": w.name, "message": w.message}
                for w in self.warnings
            ],
        }


@dataclass
class SessionState:
    project: str
    resume_point: str
    context_health: str
    pending_proposals_count: int
    session_counter: int
    health_check_due: bool = False

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "resume_point": self.resume_point,
            "context_health": self.context_health,
            "pending_proposals_count": self.pending_proposals_count,
            "session_counter": self.session_counter,
            "health_check_due": self.health_check_due,
        }


@dataclass
class NFRBlock:
    task: str
    size: TaskSize
    mode: str
    decisions: list[str]
    connections: list[str]
    raw_output: str

    def to_markdown(self) -> str:
        lines = [f"[NFR — {self.mode.upper()}]", f"Task: {self.task}", ""]
        if self.decisions:
            lines.append("Decisions:")
            for d in self.decisions:
                lines.append(f"  - {d}")
        if self.connections:
            lines.append("\nConnections:")
            for c in self.connections:
                lines.append(f"  - {c}")
        return "\n".join(lines)


@dataclass
class CommitQualityResult:
    score: int
    violations: list[str]
    suggested_rewrite: Optional[str]
    blocked: bool = False
    block_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "violations": self.violations,
            "suggested_rewrite": self.suggested_rewrite,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


@dataclass
class Proposal:
    id: str
    target: str
    change_description: str
    reason: str
    before: str
    after: str
    status: str
    proposed_date: str

    def to_markdown(self) -> str:
        return f"""## {self.id} — {self.proposed_date}
**Target:** {self.target}
**Change:** {self.change_description}
**Reason:** {self.reason}
**Before:** {self.before}
**After:** {self.after}
**Status:** {self.status}
"""


@dataclass
class HealthReport:
    org_score: float
    sessions_analyzed: int
    findings: list[str]
    proposals: list[Proposal]

    def to_markdown(self) -> str:
        lines = [
            f"# youk Health Report",
            f"**Org Score:** {self.org_score}/10",
            f"**Sessions Analyzed:** {self.sessions_analyzed}",
            "",
            "## Findings",
        ]
        for f in self.findings:
            lines.append(f"- {f}")
        lines.append(f"\n## Proposals ({len(self.proposals)} new)")
        for p in self.proposals:
            lines.append(p.to_markdown())
        return "\n".join(lines)


@dataclass
class SessionEndResult:
    knowledge_extracted: int
    proposals_added: int
    audit_written: bool
    session_close_cluster_detected: bool

    def to_dict(self) -> dict:
        return {
            "knowledge_extracted": self.knowledge_extracted,
            "proposals_added": self.proposals_added,
            "audit_written": self.audit_written,
            "session_close_cluster_detected": self.session_close_cluster_detected,
        }
