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


class KnowledgeTier(str, Enum):
    CONTRACT = "contract"       # behavioral instruction — preserve verbatim, always load
    DECISION = "decision"       # architectural choice — preserve facts + rationale
    EXPLORATION = "exploration" # depth discussion — compress to 1-2 sentence summary
    CLARIFICATION = "clarification"  # one-shot Q&A — don't persist


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
    token_budget: int = 0

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "size": self.size.value,
            "ceremony": self.ceremony,
            "skills": self.skills,
            "nfr_mode": self.nfr_mode,
            "token_budget": self.token_budget,
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
    # behavioral flags (read from last audit log entry at session_start)
    orchestrate_pending: bool = False
    close_cluster_missed: bool = False
    # project context (detected from project_dir)
    project_type: str = "unknown"
    # knowledge loading summary
    context_loaded: dict = field(default_factory=dict)
    # contracts loaded for this session
    contracts: list[str] = field(default_factory=list)
    # MCP server recommendations for detected project type
    mcp_recommendations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "resume_point": self.resume_point,
            "context_health": self.context_health,
            "pending_proposals_count": self.pending_proposals_count,
            "session_counter": self.session_counter,
            "health_check_due": self.health_check_due,
            "orchestrate_pending": self.orchestrate_pending,
            "close_cluster_missed": self.close_cluster_missed,
            "project_type": self.project_type,
            "context_loaded": self.context_loaded,
            "contracts": self.contracts,
            "mcp_recommendations": self.mcp_recommendations,
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
    suggested_skill: Optional[str] = None  # set to "humanize" when score < 70

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "violations": self.violations,
            "suggested_rewrite": self.suggested_rewrite,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "suggested_skill": self.suggested_skill,
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
    # fields required for apply_proposal to know WHAT and WHERE to write
    change_type: str = ""     # "SKILL_EDIT" | "CONFIG_EDIT" | "REFERENCE_ADD" | "FILE_CREATE"
    target_section: str = ""  # heading or key within the target file
    content: str = ""         # the new content to write

    def to_markdown(self) -> str:
        lines = [
            f"## {self.id} — {self.proposed_date}",
            f"**Target:** {self.target}",
            f"**Change:** {self.change_description}",
            f"**Reason:** {self.reason}",
            f"**Before:** {self.before}",
            f"**After:** {self.after}",
            f"**Status:** {self.status}",
        ]
        if self.change_type:
            lines.append(f"**ChangeType:** {self.change_type}")
        if self.target_section:
            lines.append(f"**TargetSection:** {self.target_section}")
        if self.content:
            lines.append(f"**Content:**\n```\n{self.content}\n```")
        lines.append("")
        return "\n".join(lines)


@dataclass
class KnowledgeEntry:
    id: str
    content: str
    tier: KnowledgeTier
    transfer_type: str = "local"         # "local" | "domain" | "global"
    domain_tags: list[str] = field(default_factory=list)
    project_type_tags: list[str] = field(default_factory=list)
    confidence: float = 0.7
    source_projects: list[str] = field(default_factory=list)
    correction_count: int = 0
    last_referenced: str = ""            # ISO date
    status: str = "active"              # "active" | "dormant" | "archived"


@dataclass
class HealthReport:
    org_score: float
    sessions_analyzed: int
    findings: list[str]
    proposals: list[Proposal]

    def to_markdown(self) -> str:
        lines = [
            "# youk Health Report",
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
