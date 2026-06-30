from __future__ import annotations
import json
import subprocess
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import SessionState
from compaction import write_contracts

CLAUDE_ROOT = Path("/claude")
YOUK_ROOT = Path("/youk")
STATE_FILE = YOUK_ROOT / "state" / "session.json"

_CONTRACT_PHRASES = [
    "always ", "never ", "from now on", "remember to", "make sure you",
    "every time", "don't forget", "commit format", "test after", "before committing",
]


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"session_counter": 0, "last_project": "", "last_session": ""}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _slug(project_dir: str) -> str:
    return Path(project_dir).name or "unknown"


def _detect_project_type(project_dir: str) -> str:
    p = Path(project_dir)
    if not p.exists():
        return "unknown"

    if (p / "go.mod").exists():
        return "go"
    if (p / "Cargo.toml").exists():
        return "rust"

    has_python = any((p / f).exists() for f in ["requirements.txt", "pyproject.toml", "setup.py"])
    if has_python:
        for candidate in [p / "requirements.txt", p / "pyproject.toml"]:
            if candidate.exists():
                try:
                    content = candidate.read_text().lower()
                    if "psycopg" in content or "sqlalchemy" in content or "asyncpg" in content:
                        return "python_postgresql"
                except Exception:
                    pass
        return "python"

    if (p / "package.json").exists():
        try:
            pkg = json.loads((p / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in deps or "next" in deps:
                return "js_react"
        except Exception:
            pass
        return "js_node"

    return "unknown"


def _read_git_log(project_dir: str, n: int = 5) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", project_dir, "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _load_project_context(slug: str) -> str | None:
    ctx_file = YOUK_ROOT / "knowledge" / "projects" / slug / "context.md"
    if not ctx_file.exists():
        return None
    try:
        return ctx_file.read_text()
    except Exception:
        return None


def _write_project_context(slug: str, project_type: str, git_log: str, first_seen: str) -> None:
    ctx_dir = YOUK_ROOT / "knowledge" / "projects" / slug
    ctx_dir.mkdir(parents=True, exist_ok=True)
    ctx_file = ctx_dir / "context.md"

    # Preserve original first-seen date if context already exists
    existing_first_seen = first_seen
    if ctx_file.exists():
        for line in ctx_file.read_text().splitlines():
            if line.startswith("first-seen:"):
                existing_first_seen = line.split(":", 1)[1].strip()
                break

    ctx_file.write_text(
        f"# Project context: {slug}\n\n"
        f"project-type: {project_type}\n"
        f"first-seen: {existing_first_seen}\n"
        f"last-seen: {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
        f"## Recent commits\n\n"
        f"```\n{git_log or 'no git history'}\n```\n"
    )


def _load_contracts(slug: str) -> list[str]:
    contracts_file = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    if not contracts_file.exists():
        return []
    try:
        return [
            line.strip()
            for line in contracts_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    except Exception:
        return []


def _load_l2_context(project_dir: str) -> tuple[str, str]:
    """Returns (resume_point, context_health) from project's .claude/ dir."""
    p = Path(project_dir)
    claude_dir = p / ".claude"
    resume_point = ""
    context_health = "NONE"

    if not claude_dir.exists():
        return resume_point, context_health

    prd_status = claude_dir / "prd-status.md"
    if prd_status.exists():
        content = prd_status.read_text()
        for line in content.split("\n"):
            if "Resume from" in line or "resume from" in line:
                lines = content.split("\n")
                idx = lines.index(line)
                for next_line in lines[idx + 1:]:
                    if next_line.strip():
                        resume_point = next_line.strip()
                        break
                break
        context_health = "L3"

    for f in claude_dir.iterdir():
        if f.suffix == ".md" and "context" in f.name.lower():
            context_health = "L2+L3" if context_health == "L3" else "L2"
            break

    return resume_point, context_health


def _parse_last_session_flags(audit_dir: Path) -> tuple[bool, bool]:
    """Returns (close_cluster_missed, orchestrate_pending) from last session entry."""
    close_cluster_missed = False
    orchestrate_pending = False

    month = datetime.utcnow().strftime("%Y-%m")
    audit_file = audit_dir / f"{month}.md"
    if not audit_file.exists():
        return False, False

    try:
        content = audit_file.read_text()
        sessions = content.split("### Session —")
        if len(sessions) < 2:
            return False, False
        last = sessions[-1]

        for line in last.splitlines():
            if line.startswith("CloseCluster:") and "no" in line.lower():
                close_cluster_missed = True
            if line.startswith("Skills:") and "orchestrate" not in line.lower():
                # Only flag if session had meaningful skill usage (at least 2 skills)
                skills_line = line[len("Skills:"):].strip()
                if skills_line.count(",") >= 1:
                    orchestrate_pending = True
    except Exception:
        pass

    return close_cluster_missed, orchestrate_pending


def _generate_session_plan(
    slug: str,
    resume_point: str,
    contracts: list[str],
    pending_proposals: int,
    close_cluster_missed: bool,
    project_type: str,
) -> list[str]:
    """
    Generate a forward-looking session plan from structured context.
    Returns 3-5 bullet points: current priority, next task, what to defer.
    Built from files — not by summarising conversation — so it's always grounded.
    """
    plan: list[str] = []

    # 1. Current priority — what the resume point signals
    if resume_point and resume_point != "No prior context found — fresh session.":
        if resume_point.startswith("Last commit:"):
            plan.append(f"Continue from: {resume_point}")
        else:
            plan.append(f"Resume: {resume_point}")
    else:
        plan.append(f"New session on {slug} — establish context before coding")

    # 2. Pending proposals surface
    if pending_proposals > 0:
        plan.append(
            f"Review {pending_proposals} pending self-heal proposal(s) "
            f"before major changes (call get_proposals)"
        )

    # 3. Missed close-cluster from last session
    if close_cluster_missed:
        plan.append(
            "Last session ended without context-sync + learn — "
            "call session_end with explicit_contracts before new work piles up"
        )

    # 4. Project-type-specific nudge
    type_nudges = {
        "python_postgresql": "DB changes this session? Run nfr_check before touching schema.",
        "js_react": "UI changes? verify dark mode + error states (nfr_check → /done).",
        "python": "Adding new dependency? Flag for dependency check.",
    }
    nudge = type_nudges.get(project_type, "")
    if nudge:
        plan.append(nudge)

    # 5. Contract reminder if contracts exist (first one only — most load-bearing)
    if contracts:
        plan.append(f"Active contract: {contracts[0]}")

    return plan[:5]  # hard cap


def _count_pending_proposals() -> int:
    pending_file = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"
    if not pending_file.exists():
        return 0
    return pending_file.read_text().count("## PENDING-")


def start_session(project_dir: str) -> SessionState:
    state = _load_state()
    state["session_counter"] = state.get("session_counter", 0) + 1
    state["last_project"] = project_dir
    state["last_session"] = datetime.utcnow().isoformat()
    _save_state(state)

    slug = _slug(project_dir)
    project_type = _detect_project_type(project_dir)
    git_log = _read_git_log(project_dir)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    _write_project_context(slug, project_type, git_log, first_seen=today)

    l2_resume, context_health = _load_l2_context(project_dir)
    existing_ctx = _load_project_context(slug)
    if existing_ctx and context_health == "NONE":
        context_health = "L1"

    # Priority-ordered resume point: L3 > L2 > git log > fresh session
    if l2_resume:
        resume_point = l2_resume
    elif git_log:
        first_commit = git_log.splitlines()[0]
        resume_point = f"Last commit: {first_commit}"
    else:
        resume_point = "No prior context found — fresh session."

    contracts = _load_contracts(slug)
    audit_dir = CLAUDE_ROOT / "audit"
    close_cluster_missed, orchestrate_pending = _parse_last_session_flags(audit_dir)

    pending = _count_pending_proposals()
    counter = state["session_counter"]
    health_check_due = counter % 3 == 0

    session_plan = _generate_session_plan(
        slug=slug,
        resume_point=resume_point,
        contracts=contracts,
        pending_proposals=pending,
        close_cluster_missed=close_cluster_missed,
        project_type=project_type,
    )

    return SessionState(
        project=slug,
        resume_point=resume_point,
        context_health=context_health,
        pending_proposals_count=pending,
        session_counter=counter,
        health_check_due=health_check_due,
        project_type=project_type,
        contracts=contracts,
        close_cluster_missed=close_cluster_missed,
        orchestrate_pending=orchestrate_pending,
        session_plan=session_plan,
    )


def end_session(summary: str, commits_made: bool, explicit_contracts: list[str] | None = None) -> dict:
    """
    Write structured audit log entry, detect and save contract phrases.

    explicit_contracts: Contract lines to save directly (e.g. extracted from
    conversation by Claude before calling session_end). These take priority over
    the phrase-detected ones and are written verbatim to contracts.md.
    """
    from guardrails import check_knowledge_write
    check_knowledge_write(summary)

    detected_contracts = [
        phrase.strip()
        for phrase in _CONTRACT_PHRASES
        if phrase.lower() in summary.lower()
    ]

    audit_dir = CLAUDE_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    month = datetime.utcnow().strftime("%Y-%m")
    audit_file = audit_dir / f"{month}.md"

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    # Skills: and CloseCluster: lines are populated by the caller via the summary.
    # The structured fields below are defaults; the summary text is the source of truth.
    entry = (
        f"\n### Session — {timestamp}\n"
        f"{summary}\n"
        f"Commits: {'yes' if commits_made else 'no'}\n"
    )

    with open(audit_file, "a") as f:
        f.write(entry)

    # Write contracts to disk so they survive future sessions and compact_context can pin them
    current_state = _load_state()
    slug = _slug(current_state.get("last_project", ""))
    contracts_to_save = explicit_contracts or detected_contracts
    contracts_saved = write_contracts(slug, contracts_to_save) if slug and contracts_to_save else 0

    session_close_detected = any(
        marker in summary
        for marker in ["FLUSHED", "[MENTAL MODEL UPDATE", "context-sync end", "learn complete"]
    )

    return {
        "knowledge_extracted": summary.count("##"),
        "proposals_added": 0,
        "audit_written": True,
        "session_close_cluster_detected": session_close_detected,
        "contract_phrases_detected": detected_contracts,
        "contracts_saved": contracts_saved,
        "add_to_contracts_prompt": len(detected_contracts) > 0 and contracts_saved == 0,
    }
