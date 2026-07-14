from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import SessionState
from compaction import write_contracts, build_brief as _build_brief
from tokens import read_and_clear as _read_and_clear_tokens

CLAUDE_ROOT = Path("/claude")
YOUK_ROOT = Path("/youk")
HOST_HOME = Path("/host-home")   # $HOME mounted :ro when install.sh adds -v $HOME:/host-home:ro
STATE_FILE = YOUK_ROOT / "state" / "session.json"

_CONTRACT_PHRASES = [
    "always ", "never ", "from now on", "remember to", "make sure you",
    "every time", "don't forget", "commit format", "test after", "before committing",
    # Implicit corrections — softer phrases that indicate a behavioral contract
    "don't do that", "wrong approach", "instead of doing", "do it this way",
    "stop doing", "use this instead", "the right way is",
]

import re as _re

_GENERALIZABLE_PHRASES = [
    "always ", "never ", "prefer ", "before every", "after every",
    "use ", " instead of ", "make sure ", "keep ", "ensure ",
]
_PROJECT_SPECIFIC_MARKERS = [
    "/src/", "/tests/", ".py", ".ts", ".js", ".go", ".rs",
    "this project", "in our", "our codebase", "our repo",
]

# Broader patterns: label-prefixed contracts and imperative phrases not caught by
# simple substring matching. These express methodology but don't start with the
# trigger words in _GENERALIZABLE_PHRASES.
_GENERALIZABLE_PATTERNS = [
    _re.compile(r"^[a-z][a-z _-]+:\s+.{20,}", _re.IGNORECASE),   # "commit format: ..."
    _re.compile(r"\b(every project|any project|all projects)\b", _re.IGNORECASE),
    _re.compile(r"\b(before every|after every|on every)\b", _re.IGNORECASE),
    _re.compile(
        r"^(check|run|read|verify|avoid|scan|document|test|flag|require|write|record|capture)\b",
        _re.IGNORECASE,
    ),
]


def _is_generalizable(contract: str) -> bool:
    """True if contract expresses a cross-project methodology, not a project-specific path."""
    lower = contract.lower()
    has_specific = any(marker in contract for marker in _PROJECT_SPECIFIC_MARKERS)
    if has_specific:
        return False
    has_method = any(phrase in lower for phrase in _GENERALIZABLE_PHRASES)
    if has_method:
        return True
    return any(p.search(contract) for p in _GENERALIZABLE_PATTERNS)


def _promote_generalizable_to_global(contracts: list[str]) -> dict:
    """Promote generalizable contracts to knowledge/global/contracts.md with line-level dedup."""
    global_file = YOUK_ROOT / "knowledge" / "global" / "contracts.md"
    if not global_file.parent.exists():
        return {"promoted": 0, "candidates": contracts}
    existing_lines: set[str] = set()
    if global_file.exists():
        for line in global_file.read_text().splitlines():
            normalized = line.strip().lstrip("- ").removeprefix("[auto-promoted] ").lower()
            if normalized:
                existing_lines.add(normalized)
    promoted = []
    for c in contracts:
        if c.strip().lower() not in existing_lines:
            promoted.append(c)
    if promoted:
        with open(global_file, "a") as f:
            for c in promoted:
                f.write(f"- [auto-promoted] {c}\n")
    return {"promoted": len(promoted), "candidates": contracts}


def _scan_research_inbox(slug: str = "") -> list[str]:
    """Scan global and project-specific research inboxes for recent findings.
    Returns pattern names extracted from ## headings, newest first."""
    cutoff = datetime.utcnow().timestamp() - (14 * 24 * 3600)
    patterns: list[str] = []

    inboxes = [YOUK_ROOT / "knowledge" / "research-inbox"]
    if slug:
        project_inbox = YOUK_ROOT / "knowledge" / "projects" / slug / "research-inbox"
        if project_inbox.exists():
            inboxes.insert(0, project_inbox)  # project findings surface first

    for inbox in inboxes:
        if not inbox.exists():
            continue
        try:
            for f in sorted(inbox.iterdir(), reverse=True):
                if f.suffix != ".md" or f.name in (".gitkeep", "README.md"):
                    continue
                if f.stat().st_mtime < cutoff:
                    continue
                for line in f.read_text().splitlines():
                    stripped = line.strip()
                    if stripped.startswith("## ") and "Research Scan" not in stripped:
                        patterns.append(stripped[3:].strip())
        except Exception:
            pass

    seen: set[str] = set()
    deduped = [p for p in patterns if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]
    return deduped[:8]


def _last_token_overhead() -> tuple[int | None, int | None]:
    """Read the most recent Tokens: N/B (P%) line from the current month's audit.
    Returns (pct, budget) or (None, None) if no token data yet."""
    audit_dir = CLAUDE_ROOT / "audit"
    month = datetime.utcnow().strftime("%Y-%m")
    audit_file = audit_dir / f"{month}.md"
    if not audit_file.exists():
        return None, None
    try:
        for line in reversed(audit_file.read_text().splitlines()):
            m = re.search(r"Tokens:\s*\d+/(\d+)\s*\((\d+)%\)", line)
            if m:
                return int(m.group(2)), int(m.group(1))  # (pct, budget)
    except Exception:
        pass
    return None, None


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


def _find_stale_decisions(slug: str, threshold_days: int = 90) -> list[tuple[str, int]]:
    """Return (heading, age_days) for decisions.md entries older than threshold_days.
    Only returns entries with a parseable date in the heading (## YYYY-MM-DD: ...)."""
    import re as _re2
    decisions_file = YOUK_ROOT / "knowledge" / "projects" / slug / "decisions.md"
    if not decisions_file.exists():
        return []
    stale: list[tuple[str, int]] = []
    date_pattern = _re2.compile(r"^##\s+(\d{4}-\d{2}-\d{2})[:\s]+(.*)")
    now = datetime.utcnow()
    try:
        for line in decisions_file.read_text().splitlines():
            m = date_pattern.match(line)
            if not m:
                continue
            try:
                decision_date = datetime.strptime(m.group(1), "%Y-%m-%d")
                age_days = (now - decision_date).days
                if age_days >= threshold_days:
                    stale.append((m.group(2).strip(), age_days))
            except ValueError:
                continue
    except Exception:
        return []
    # Sort oldest first — most urgent to review
    return sorted(stale, key=lambda x: x[1], reverse=True)


def _load_session_plan_items(slug: str) -> list[str]:
    """Return the current session plan items from state/session-plan.json."""
    plan_file = YOUK_ROOT / "state" / "session-plan.json"
    if not plan_file.exists():
        return []
    try:
        data = json.loads(plan_file.read_text())
        if data.get("slug") and data["slug"] != slug:
            return []
        return [p for p in data.get("plan", []) if p and not p.startswith("⚠")]
    except Exception:
        return []


def _slug(project_dir: str) -> str:
    """Return a filesystem-safe slug for project_dir.

    Uses basename alone when it's unique across known projects. Appends a 6-char
    path hash when another project with the same basename already exists under a
    different path — avoids silently mixing knowledge stores for "api", "backend", etc.
    """
    import hashlib
    name = Path(project_dir).name or "unknown"
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if not projects_dir.exists():
        return name

    # Check if an existing slug directory was registered to a different host path
    slug_dir = projects_dir / name
    marker = slug_dir / "project-path.txt"
    if marker.exists():
        registered = marker.read_text().strip()
        # Normalise: strip trailing slash, compare basename-only as fallback
        if registered and registered != project_dir and Path(registered).name != name:
            short_hash = hashlib.sha1(project_dir.encode()).hexdigest()[:6]
            return f"{name}-{short_hash}"
    return name


def _resolve_project_path(host_path: str) -> Path:
    """Translate a host-absolute project path to a path accessible inside this container.

    The container has fixed mount points:
      /youk  = host YOUK_DIR  (e.g. ~/.claude/youk)
      /claude = host CLAUDE_DIR (e.g. ~/.claude)

    Two fallback mechanisms (tried in order):
    1. state/path-map.env — written by install.sh; maps YOUK_HOST_DIR and CLAUDE_HOST_DIR
    2. /host-home         — host $HOME mounted :ro (requires updated install.sh re-run)
    """
    p = Path(host_path)
    if p.exists():
        return p  # already accessible (local dev, or running outside Docker)

    # Mechanism 1: path-map.env written by install.sh
    path_map_file = YOUK_ROOT / "state" / "path-map.env"
    if path_map_file.exists():
        try:
            mapping: dict[str, str] = {}
            for line in path_map_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    mapping[key.strip()] = val.strip()

            youk_host = mapping.get("YOUK_HOST_DIR", "")
            claude_host = mapping.get("CLAUDE_HOST_DIR", "")

            if youk_host and host_path.startswith(youk_host):
                relative = host_path[len(youk_host):].lstrip("/")
                candidate = YOUK_ROOT / relative if relative else YOUK_ROOT
                if candidate.exists():
                    return candidate

            if claude_host and host_path.startswith(claude_host):
                relative = host_path[len(claude_host):].lstrip("/")
                candidate = CLAUDE_ROOT / relative if relative else CLAUDE_ROOT
                if candidate.exists():
                    return candidate
        except Exception:
            pass

    # Mechanism 2: /host-home mount (added by install.sh -v $HOME:/host-home:ro)
    if HOST_HOME.exists():
        for prefix in ("/Users/", "/home/"):
            if host_path.startswith(prefix):
                rest = host_path[len(prefix):]
                rest_parts = Path(rest).parts  # ("username", "subdir", ...)
                if len(rest_parts) > 1:
                    relative = Path(*rest_parts[1:])  # strip the username segment
                    candidate = HOST_HOME / relative
                    if candidate.exists():
                        return candidate

    return p  # return as-is; callers check .exists() and degrade gracefully


def _detect_project_type(project_dir: str) -> str:
    p = _resolve_project_path(project_dir)
    if not p.exists():
        return "unknown"

    if (p / "go.mod").exists():
        return "go"
    if (p / "Cargo.toml").exists():
        return "rust"

    def _check_python(base: Path) -> str | None:
        if not any((base / f).exists() for f in ["requirements.txt", "pyproject.toml", "setup.py"]):
            return None
        for candidate in [base / "requirements.txt", base / "pyproject.toml"]:
            if candidate.exists():
                try:
                    content = candidate.read_text().lower()
                    if "psycopg" in content or "sqlalchemy" in content or "asyncpg" in content:
                        return "python_postgresql"
                except Exception:
                    pass
        return "python"

    py_type = _check_python(p)
    if py_type:
        return py_type

    has_docker_orchestration = (
        (p / "Makefile").exists()
        and any(
            (p / f).exists()
            for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]
        )
    )

    for sub in ["servers", "src", "app", "backend", "api"]:
        sub_path = p / sub
        if sub_path.is_dir():
            py_type = _check_python(sub_path)
            if py_type:
                return "python/docker" if has_docker_orchestration else py_type
            for nested in sorted(sub_path.iterdir()):
                if nested.is_dir():
                    py_type = _check_python(nested)
                    if py_type:
                        return "python/docker" if has_docker_orchestration else py_type

    for df in sorted(p.glob("**/Dockerfile"))[:10]:
        try:
            if "FROM python:" in df.read_text():
                return "python"
        except Exception:
            pass

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


# Maps project purpose → list of skills expected for that project type.
# Used by health._check_project_type_coverage to surface missing coverage.
# Keep this in sync with _PROJECT_TYPE_EXPECTED_SKILLS in health.py.
PROJECT_PURPOSE_EXPECTED_SKILLS: dict[str, list[dict]] = {
    "ai_engineering_system": [
        {"name": "install-experience", "purpose": "Simulate install and first-run for a new developer"},
        {"name": "namespace-safety", "purpose": "Detect collision risks in skills, MCP servers, config keys"},
    ],
    "mcp_server": [
        {"name": "install-experience", "purpose": "Review the install flow for a developer new to this tool"},
        {"name": "namespace-safety", "purpose": "Check for naming conflicts in MCP tools and skills"},
    ],
    "installable_cli": [
        {"name": "install-experience", "purpose": "Review the install flow and first-run experience"},
    ],
    "docker_multi_service": [
        {"name": "docker-ops", "purpose": "Troubleshoot container issues, volume mounts, service networking"},
    ],
}

_PURPOSE_DESCRIPTIONS: dict[str, str] = {
    "ai_engineering_system": "AI engineering system with skill infrastructure",
    "mcp_server": "MCP server exposing tools to Claude Code",
    "installable_cli": "CLI tool with an installer",
    "docker_multi_service": "Multi-service Docker application",
    "general": "General software project",
}


def _detect_project_purpose(project_dir: str) -> str:
    """
    Detect the purpose/domain of the project beyond just its stack/language.
    Returns a key from PROJECT_PURPOSE_EXPECTED_SKILLS or 'general'.
    Used to surface skill coverage gaps for the specific project type.
    """
    p = _resolve_project_path(project_dir)
    if not p.exists():
        return "general"

    # AI engineering system: has a skills/ directory containing SKILL.md files
    skills_dir = p / "skills"
    if skills_dir.is_dir() and any(skills_dir.glob("*/SKILL.md")):
        return "ai_engineering_system"

    # MCP server tool: has server.py files that import the MCP framework
    for server_file in sorted(p.glob("**/server.py"))[:10]:
        try:
            content = server_file.read_text()
            if "fastmcp" in content or "from mcp" in content or "mcp.server" in content:
                return "mcp_server"
        except Exception:
            pass

    # Multi-service Docker: multiple Dockerfile files in subdirectories
    dockerfiles = [f for f in p.glob("*/Dockerfile")] + [f for f in p.glob("*/*/Dockerfile")]
    if len(set(str(f) for f in dockerfiles)) > 1:
        return "docker_multi_service"

    # Installable CLI: has an install.sh script
    if (p / "scripts" / "install.sh").exists() or (p / "install.sh").exists():
        return "installable_cli"

    return "general"


def _detect_stack_context(project_dir: str) -> dict:
    """
    Detect stack, framework, and domain from project files.
    Pure file I/O — zero tokens, zero API calls.

    Returns: {stack, framework, domain} — any field may be None if undetected.
    """
    p = _resolve_project_path(project_dir)
    if not p.exists():
        return {"stack": None, "framework": None, "domain": None}

    stack: str | None = None
    framework: str | None = None
    domain: str | None = None

    # --- Stack detection ---
    if (p / "go.mod").exists():
        stack = "go"
    elif (p / "Cargo.toml").exists():
        stack = "rust"
    else:
        # Collect all requirements/dependency files, checking nested dirs too
        req_files: list[Path] = []
        for fname in ["requirements.txt", "pyproject.toml", "setup.py"]:
            candidates = [p / fname] + [
                p / sub / fname
                for sub in ["servers", "src", "app", "backend", "api"]
            ]
            req_files.extend(c for c in candidates if c.exists())

        if req_files:
            stack = "python"
            all_deps = ""
            for f in req_files[:6]:
                try:
                    all_deps += f.read_text().lower()
                except Exception:
                    pass

            # Framework detection (Python)
            if "django" in all_deps:
                framework = "django"
            elif "fastapi" in all_deps:
                framework = "fastapi"
            elif "flask" in all_deps:
                framework = "flask"
            elif "tornado" in all_deps:
                framework = "tornado"

            # Domain detection (Python deps)
            if any(k in all_deps for k in ("stripe", "billing", "subscription", "paddle", "chargebee")):
                domain = "saas"
            elif any(k in all_deps for k in ("sklearn", "torch", "tensorflow", "pandas", "numpy", "xgboost")):
                domain = "data"
            elif any(k in all_deps for k in ("boto3", "kubernetes", "terraform", "pulumi", "ansible")):
                domain = "infra"

        elif (p / "package.json").exists():
            stack = "javascript"
            try:
                pkg = json.loads((p / "package.json").read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    framework = "nextjs"
                elif "react" in deps:
                    framework = "react"
                elif "vue" in deps:
                    framework = "vue"
                elif "svelte" in deps:
                    framework = "svelte"
                if "typescript" in deps:
                    stack = "typescript"
                if any(k in deps for k in ("stripe", "@stripe/stripe-js")):
                    domain = "saas"
            except Exception:
                pass

    return {"stack": stack, "framework": framework, "domain": domain}


def _read_git_log(project_dir: str, n: int = 5) -> str:
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _read_git_log_since_days(project_dir: str, days: int) -> tuple[int, list[str]]:
    """Return (commit_count, [subject_lines]) for commits in the last `days` days.
    Used to give returning developers a factual "what changed while you were gone" summary."""
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "log", "--oneline", f"--since={days} days ago"],
            capture_output=True, text=True, timeout=5
        )
        lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
        subjects = [ln.split(" ", 1)[1] if " " in ln else ln for ln in lines[:5]]
        return len(lines), subjects
    except Exception:
        return 0, []


def _count_commits_since(project_dir: str, since_hash: str) -> int:
    """Count commits in project_dir that came after since_hash."""
    resolved = str(_resolve_project_path(project_dir))
    try:
        result = subprocess.run(
            ["git", "-C", resolved, "rev-list", "--count", f"{since_hash}..HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    except Exception:
        return 0


def _load_project_context(slug: str) -> str | None:
    ctx_file = YOUK_ROOT / "knowledge" / "projects" / slug / "context.md"
    if not ctx_file.exists():
        return None
    try:
        return ctx_file.read_text()
    except Exception:
        return None


def _write_project_context(slug: str, project_type: str, git_log: str, first_seen: str, project_dir: str = "") -> None:
    ctx_dir = YOUK_ROOT / "knowledge" / "projects" / slug
    ctx_dir.mkdir(parents=True, exist_ok=True)
    ctx_file = ctx_dir / "context.md"

    # Write path marker on first creation so _slug() can detect collisions later
    marker = ctx_dir / "project-path.txt"
    if not marker.exists() and project_dir:
        marker.write_text(project_dir)

    # Preserve first-seen date and resume-from point across rewrites
    existing_first_seen = first_seen
    existing_resume = ""
    if ctx_file.exists():
        for line in ctx_file.read_text().splitlines():
            if line.startswith("first-seen:"):
                existing_first_seen = line.split(":", 1)[1].strip()
            elif line.startswith("resume-from:"):
                existing_resume = line  # preserve verbatim

    resume_line = f"{existing_resume}\n" if existing_resume else ""
    ctx_file.write_text(
        f"# Project context: {slug}\n\n"
        f"project-type: {project_type}\n"
        f"first-seen: {existing_first_seen}\n"
        f"last-seen: {datetime.utcnow().strftime('%Y-%m-%d')}\n"
        f"{resume_line}"
        f"\n## Recent commits\n\n"
        f"```\n{git_log or 'no git history'}\n```\n"
    )


def _update_resume_point(slug: str, resume_text: str) -> None:
    """Write the resume point for the next session into external context.md."""
    ctx_file = YOUK_ROOT / "knowledge" / "projects" / slug / "context.md"
    if not ctx_file.exists():
        return
    try:
        lines = [ln for ln in ctx_file.read_text().splitlines() if not ln.startswith("resume-from:")]
        lines.append(f"resume-from: {resume_text[:200]}")
        ctx_file.write_text("\n".join(lines) + "\n")
    except Exception:
        pass


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


def _load_global_contracts(cap: int = 50) -> list[str]:
    """Load user's cross-project global behavioral contracts (knowledge/global/contracts.md).
    These apply to every project — loaded before project-specific contracts at session start.
    Capped at `cap` most recently confirmed entries to bound session context cost."""
    global_file = YOUK_ROOT / "knowledge" / "global" / "contracts.md"
    if not global_file.exists():
        return []
    try:
        lines = [
            line.strip()
            for line in global_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        return lines[-cap:]  # most recently added = most recently confirmed
    except Exception:
        return []


def _load_l2_context(project_dir: str) -> tuple[str, str]:
    """Returns (resume_point, context_health) from project's .claude/ dir."""
    p = _resolve_project_path(project_dir)
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


def _scan_project_context_files(project_dir: str) -> dict:
    """
    Scan the project directory for standard context files that can inform
    session_start without requiring any youk-specific setup in the project repo.

    Reads — but caps aggressively to avoid overloading initial context:
    - CLAUDE.md (root) — full, max 1200 chars (project system instructions)
    - README.md — first description paragraph only (max 400 chars)
    - docs/ — filenames only, no content (surface availability, not dump content)
    - .claude/CLAUDE.md — project-local youk instructions (max 1200 chars)

    Returns a dict with keys: claude_md, readme_snippet, docs_available, context_level
    """
    p = _resolve_project_path(project_dir)
    result: dict = {
        "claude_md": "",
        "readme_snippet": "",
        "docs_available": [],
        "context_level": "L1",  # upgraded as each source is found
    }

    # Root CLAUDE.md — highest priority, project system instructions
    for candidate in [p / "CLAUDE.md", p / ".claude" / "CLAUDE.md"]:
        if candidate.exists():
            try:
                text = candidate.read_text()[:1200]
                result["claude_md"] = text
                result["context_level"] = "L5"
            except Exception:
                pass
            break

    # README.md — first prose paragraph (skip HTML, badges, dividers)
    readme = p / "README.md"
    if readme.exists():
        try:
            lines = readme.read_text().splitlines()
            snippet_lines = []
            for ln in lines[:80]:
                stripped = ln.strip()
                if not stripped or stripped == "---":
                    if snippet_lines:
                        break  # end of first prose paragraph
                    continue
                # skip HTML blocks, badges, and markdown headers/image tags
                if (stripped.startswith("<")
                        or stripped.startswith("[![")
                        or stripped.startswith("![")
                        or stripped.startswith("#")
                        or stripped.startswith("|")
                        or stripped.startswith(">")):
                    if snippet_lines:
                        break
                    continue
                snippet_lines.append(stripped)
                if len(" ".join(snippet_lines)) > 400:
                    break
            if snippet_lines:
                result["readme_snippet"] = " ".join(snippet_lines)[:400]
                if result["context_level"] == "L1":
                    result["context_level"] = "L4"
        except Exception:
            pass

    # readme_snippet is extracted heuristically above. No API fallback — all skill
    # execution is in_session (Claude Code answers, not the container). Zero double-billing.

    # docs/ directory — scan for spec/PRD/architecture files (names only)
    docs_dir = p / "docs"
    if docs_dir.exists():
        try:
            spec_keywords = {"spec", "prd", "arch", "design", "requirements", "rfc", "adr"}
            result["docs_available"] = [
                f.name for f in sorted(docs_dir.iterdir())
                if f.suffix in {".md", ".txt", ".rst"}
                and any(kw in f.name.lower() for kw in spec_keywords)
            ][:8]  # cap at 8 filenames
        except Exception:
            pass

    # Tooling detection — surface existing project mechanisms so youk adapts to the
    # project's workflow rather than assuming generic commands or standards.
    tooling: dict = {
        "make_targets": [],   # Makefile target names + inline comments
        "npm_scripts": [],    # package.json script names
        "ci_providers": [],   # detected CI/CD providers
        "pre_commit": False,  # .pre-commit-config.yaml present
        "test_configs": [],   # detected test runner config files
        "containers": [],     # Dockerfile / docker-compose files
        "ai_context": [],     # AI instruction files from other tools (Cursor, Aider, etc.)
    }

    # Makefile — parse targets with ## comments; also detect bare common targets
    makefile = p / "Makefile"
    if makefile.exists():
        try:
            lines = makefile.read_text().splitlines()
            for line in lines:
                # Commented targets: "target: ## description"
                m = re.match(r"^([a-zA-Z_-]+):.*?##\s*(.+)", line)
                if m:
                    tooling["make_targets"].append(f"make {m.group(1)}: {m.group(2).strip()[:60]}")
                    continue
                # Bare common targets without comments
                m2 = re.match(r"^(test|build|run|dev|deploy|lint|install|clean|start|check)\s*:", line)
                if m2 and f"make {m2.group(1)}" not in " ".join(tooling["make_targets"]):
                    tooling["make_targets"].append(f"make {m2.group(1)}")
            tooling["make_targets"] = tooling["make_targets"][:12]
        except Exception:
            pass

    # package.json scripts
    pkg_json = p / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            tooling["npm_scripts"] = [f"npm run {k}" for k in list(scripts)[:10]]
        except Exception:
            pass

    # CI providers
    for ci_path, ci_name in [
        (".github/workflows", "github-actions"),
        (".circleci", "circleci"),
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        (".buildkite", "buildkite"),
    ]:
        if (p / ci_path).exists():
            tooling["ci_providers"].append(ci_name)

    # Pre-commit hooks
    if (p / ".pre-commit-config.yaml").exists():
        tooling["pre_commit"] = True

    # Test runner config files
    for test_file in [
        "pytest.ini", "pyproject.toml", "setup.cfg",
        "jest.config.js", "jest.config.ts", "vitest.config.ts",
        ".rspec", "karma.conf.js",
    ]:
        if (p / test_file).exists():
            tooling["test_configs"].append(test_file)

    # Container setup
    for container_file in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
        if (p / container_file).exists():
            tooling["containers"].append(container_file)

    # AI instruction files from other tools — read a snippet so Claude can check for
    # conflicts or complementary conventions with youk's own CLAUDE.md.
    for ai_file in ["AGENTS.md", ".cursorrules", ".aider.conf.yml", "copilot-instructions.md"]:
        candidate = p / ai_file
        if candidate.exists():
            try:
                snippet = candidate.read_text()[:300].strip()
                tooling["ai_context"].append({"file": ai_file, "snippet": snippet[:250]})
            except Exception:
                tooling["ai_context"].append({"file": ai_file, "snippet": ""})

    result["tooling"] = tooling
    return result


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


def _parse_skills_line(line: str) -> list[str]:
    """Parse a 'Skills: ...' audit line into a list of skill name tokens."""
    raw = line[len("Skills:"):].strip()
    if not raw or raw.lower() == "none":
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _has_capability_skill(skills: list[str]) -> bool:
    return any(s.lower().replace("-", "_") in _CAPABILITY_SKILLS or s.lower() in _CAPABILITY_SKILLS for s in skills)


def _compute_skill_invocation_rate(audit_dir: Path) -> tuple[int | None, int]:
    """
    Returns (rate_pct, consecutive_skips).
    rate_pct: % of sessions with at least one capability skill invoked (None if no sessions).
    consecutive_skips: how many of the most-recent sessions have zero capability skills.
    """
    try:
        texts = [f.read_text() for f in sorted(audit_dir.glob("*.md")) if f.is_file()]
        if not texts:
            return None, 0
        full = "\n".join(texts)
        entries = full.split("### Session —")[1:]  # skip preamble
        if not entries:
            return None, 0

        hit = []  # True if session had a capability skill
        for entry in entries:
            skills_found: list[str] = []
            for line in entry.splitlines():
                if line.startswith("Skills:"):
                    skills_found = _parse_skills_line(line)
                    break
            hit.append(_has_capability_skill(skills_found))

        total = len(hit)
        rate_pct = int(sum(hit) / total * 100) if total else None

        # Count trailing skips (most recent sessions with no capability skill)
        consecutive_skips = 0
        for had_skill in reversed(hit):
            if had_skill:
                break
            consecutive_skips += 1

        return rate_pct, consecutive_skips
    except Exception:
        return None, 0


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


def _compute_dashboard_summary(audit_dir: Path, pending_proposals: int, slug: str = "") -> str:
    """One-line trend hint for the session card footer. Returns '' on any failure."""
    try:
        texts = [f.read_text() for f in sorted(audit_dir.glob("*.md")) if f.is_file()]
        if not texts:
            return ""
        full = "\n".join(texts)

        session_count = len(re.findall(r"^### Session —", full, re.MULTILINE))
        skill_rate_pct, _ = _compute_skill_invocation_rate(audit_dir)

        # Read org_score history from improvement-metrics.json — the authoritative source.
        # Audit text never contains "Org score: X/10" so regex-scanning audit always returns [].
        metrics_file = YOUK_ROOT / "state" / "improvement-metrics.json"
        last_score = ""
        velocity_str = ""
        spark = ""
        try:
            import json as _j
            if metrics_file.exists():
                entries = _j.loads(metrics_file.read_text()).get("entries", [])
                scores = [e["org_score"] for e in entries if "org_score" in e]
                if scores:
                    last_score = f"org: {scores[-1]}/10"
                    if len(scores) >= 2:
                        _S = " ▁▂▃▄▅▆▇█"
                        n = len(_S) - 1
                        spark = "".join(_S[round(v / 10 * n)] for v in scores[-5:])
                        delta = round(scores[-1] - scores[-2], 1)
                        if delta > 0:
                            velocity_str = f"▲{delta}"
                        elif delta < 0:
                            velocity_str = f"▼{abs(delta)}"
        except Exception:
            pass

        # Per-project score: surfaced alongside system-wide score when available.
        project_score_str = ""
        if slug:
            try:
                data = _j.loads(metrics_file.read_text()) if metrics_file.exists() else {}
                proj = data.get("projects", {}).get(slug, {})
                if proj.get("org_score") is not None:
                    project_score_str = f"{slug}: {proj['org_score']}/10"
            except Exception:
                pass

        # Recompute /done rate directly from audit — not the stale metrics snapshot.
        close_rate_str = ""
        if session_count:
            done_count = len(re.findall(r"^CloseCluster: yes", full, re.MULTILINE))
            close_rate_str = f"/done: {int(done_count / session_count * 100)}%"

        parts: list[str] = []
        score_part = last_score
        if velocity_str:
            score_part += f" {velocity_str}"
        if spark:
            score_part += f" {spark}"
        if score_part:
            parts.append(score_part)
        if project_score_str:
            parts.append(project_score_str)
        if session_count:
            parts.append(f"{session_count} session{'s' if session_count != 1 else ''}")
        if skill_rate_pct is not None:
            parts.append(f"skills: {skill_rate_pct}%")
        if pending_proposals:
            parts.append(f"{pending_proposals} proposal{'s' if pending_proposals != 1 else ''} pending")
        if close_rate_str:
            parts.append(close_rate_str)
        return "  ·  ".join(parts)
    except Exception:
        return ""


def _bootstrap_cold_start(project_dir: str, slug: str, tooling: dict) -> list[str]:
    """
    Run when context_level == L1, project_type == unknown, no prior context.
    Returns a list of detected signal strings. Writes a minimal context.md.
    Zero API calls — pure file inspection.
    """
    p = _resolve_project_path(project_dir)
    signals: list[str] = []

    # Language markers
    lang_markers = {
        "Python": ["requirements.txt", "pyproject.toml", "setup.py", "*.py"],
        "JavaScript/TypeScript": ["package.json", "tsconfig.json"],
        "Go": ["go.mod"],
        "Rust": ["Cargo.toml"],
        "Ruby": ["Gemfile"],
        "Java": ["pom.xml", "build.gradle"],
        "C/C++": ["CMakeLists.txt", "Makefile"],
    }
    for lang, markers in lang_markers.items():
        if any(list(p.glob(m)) for m in markers if "*" in m) or any((p / m).exists() for m in markers if "*" not in m):
            signals.append(lang)
            break  # first match wins

    # Key directories
    for dirname, label in [
        ("tests", "has tests/"), ("test", "has test/"), ("src", "has src/"),
        ("docs", "has docs/"), ("scripts", "has scripts/"), ("api", "has api/"),
    ]:
        if (p / dirname).is_dir():
            signals.append(label)

    # Infrastructure
    for fname, label in [
        ("Dockerfile", "Docker"), ("docker-compose.yml", "Docker Compose"),
        ("docker-compose.yaml", "Docker Compose"), (".github/workflows", "GitHub Actions CI"),
        (".env.example", ".env.example"), ("Makefile", "Makefile"),
    ]:
        target = p / fname
        if (target.is_dir() if fname.endswith("workflows") else target.exists()):
            signals.append(label)

    # Makefile targets already detected via tooling
    make_targets = tooling.get("make_targets", [])
    if make_targets:
        signals.append(f"Makefile ({len(make_targets)} targets)")

    if not signals:
        return []

    # Write a bootstrap context.md so future sessions have something to resume from
    ctx_dir = YOUK_ROOT / "knowledge" / "projects" / slug
    ctx_dir.mkdir(parents=True, exist_ok=True)
    ctx_file = ctx_dir / "context.md"
    if not ctx_file.exists():
        ctx_file.write_text(
            f"# Project context: {slug}\n\n"
            f"project-type: unknown (bootstrap)\n"
            f"first-seen: {datetime.utcnow().strftime('%Y-%m-%d')}\n"
            f"last-seen: {datetime.utcnow().strftime('%Y-%m-%d')}\n"
            f"bootstrap-signals: {', '.join(signals)}\n"
            f"resume-from: First session — detected {', '.join(signals[:3])}\n"
        )

    return signals


def _find_cross_project_contract(current_slug: str, current_contracts: list[str]) -> tuple[str, str] | None:
    """
    Scan other projects' contracts.md files for behavioural agreements not yet in
    the current project. Returns (source_slug, contract_text) for the first match,
    or None.

    Only fires when current project has <3 contracts (new project still forming habits).
    Capped at 1 suggestion per session to avoid noise.
    """
    if len(current_contracts) >= 3:
        return None
    projects_dir = YOUK_ROOT / "knowledge" / "projects"
    if not projects_dir.exists():
        return None

    # Words to exclude from similarity check (too common to be meaningful)
    _STOP = frozenset({"always", "never", "make", "sure", "that", "this", "have", "with", "from", "before", "after", "each", "every"})

    def _words(text: str) -> set[str]:
        return {w.lower() for w in text.split() if len(w) > 3 and w.lower() not in _STOP}

    current_words = {w for c in current_contracts for w in _words(c)}

    try:
        for proj_dir in sorted(projects_dir.iterdir()):
            if not proj_dir.is_dir() or proj_dir.name == current_slug:
                continue
            cf = proj_dir / "contracts.md"
            if not cf.exists():
                continue
            for line in cf.read_text().splitlines():
                line = line.strip()
                if not line.startswith("- "):
                    continue
                contract = line[2:].strip()
                if not contract or len(contract) < 20:
                    continue
                # Skip if already covered by current contracts: ≥50% of meaningful
                # words from this contract appear in current-project contracts
                contract_words = _words(contract)
                overlap = len(contract_words & current_words)
                if contract_words and overlap >= max(1, len(contract_words) // 2):
                    continue
                return (proj_dir.name, contract)
    except Exception:
        pass
    return None


def _generate_session_plan(
    slug: str,
    resume_point: str,
    contracts: list[str],
    pending_proposals: int,
    close_cluster_missed: bool,
    project_type: str,
    doc_gaps: list[str] | None = None,
    docs_available: list[str] | None = None,
    has_project_claude_md: bool = False,
    tooling: dict | None = None,
    session_counter: int = 0,
    bootstrap_signals: list[str] | None = None,
    days_since_last: int | None = None,
    new_commits: int = 0,
) -> list[str]:
    """
    Generate a forward-looking session plan from structured context.
    Returns 3-5 bullet points: current priority, next task, what to defer.
    Built from files — not by summarising conversation — so it's always grounded.
    """
    plan: list[str] = []

    # 1. Current priority — what the resume point signals
    is_cold_start = resume_point in ("No prior context found — fresh session.", "") or not resume_point
    is_new_install = session_counter <= 1
    is_stale_resume = (days_since_last is not None and days_since_last >= 14 and new_commits > 10)

    if is_cold_start:
        # True first session — no knowledge anywhere
        signals_str = ", ".join((bootstrap_signals or [])[:4]) or project_type
        plan.append(
            f"First session on {slug}"
            + (f" — detected {signals_str}" if signals_str and signals_str != "unknown" else "")
            + ". Start with /build. When you stop, type /done — that's what makes session 2 different from today."
        )
        # Dedicated onboarding item — tells the user the one thing that matters most
        plan.append(
            "When you finish today: type /done. It takes 30 seconds and is the only thing "
            "that separates a session youk remembers from one it forgets. Session 2 opens "
            "with your working agreements and resume point already loaded."
        )
    elif is_new_install and contracts:
        # New install on a project with existing history (dev joining mid-project)
        plan.append(
            f"Joining {slug} — {len(contracts)} contract(s) loaded from prior sessions. "
            f"Resume: {resume_point[:120]}"
        )
    elif resume_point.startswith("Last commit:"):
        plan.append(f"Continue from: {resume_point}")
    else:
        clean = resume_point.removeprefix("Resume: ")
        if is_stale_resume:
            plan.append(f"Resume [{days_since_last}d stale — {new_commits} commits since — verify before picking up]: {clean}")
        else:
            plan.append(f"Resume: {clean}")

    # 2. Pending proposals surface
    if pending_proposals > 0:
        if session_counter <= 3:
            # Plain English for new users — no jargon
            plan.append(
                f"{pending_proposals} suggested improvement(s) queued — "
                f"type /health to review them"
            )
        else:
            plan.append(
                f"Review {pending_proposals} pending self-heal proposal(s) "
                f"before major changes (call get_proposals)"
            )

    # 3. Missed close-cluster from last session
    if close_cluster_missed:
        if session_counter <= 3:
            plan.append(
                "Last session wasn't saved. Type /done before closing "
                "so I remember what you were working on."
            )
        else:
            plan.append(
                "Last session wasn't saved (impacts org score). "
                "Run /done at the end of this session so your work compounds."
            )

    # 4. Project-type-specific nudge — use detected commands when available
    t = tooling or {}
    make_targets = t.get("make_targets", [])
    npm_scripts = t.get("npm_scripts", [])
    test_cmd = next(
        (cmd for cmd in make_targets if "test" in cmd.lower()),
        next((cmd for cmd in npm_scripts if "test" in cmd.lower()), None),
    )
    type_nudges = {
        "python_postgresql": f"DB changes? Run nfr_check before touching schema. Verify: {test_cmd or 'run tests'}.",
        "js_react": f"UI changes? verify dark mode + error states (nfr_check → /done). Test: {test_cmd or 'run tests'}.",
        "python": "Adding new dependency? Flag for dependency check.",
    }
    nudge = type_nudges.get(project_type, "")
    if nudge:
        plan.append(nudge)

    # 4b. Stack bootstrap signal — fires when: known stack, stack template exists in
    # knowledge/stacks/, and user-profile.md either doesn't exist or doesn't mention
    # this stack. Prompts /learn to seed the knowledge graph for this stack.
    _stack_key_map = {
        "python_postgresql": "python_postgresql",
        "python": "python",
        "js_react": "typescript_react",
        "node": "node",
    }
    _stack_key = _stack_key_map.get(project_type)
    if _stack_key and is_cold_start:
        _stack_template = YOUK_ROOT / "knowledge" / "stacks" / f"{_stack_key}.md"
        _user_profile = YOUK_ROOT / "knowledge" / "user-profile.md"
        _profile_text = _user_profile.read_text() if _user_profile.exists() else ""
        _stack_in_profile = _stack_key.replace("_", " ") in _profile_text.lower() or project_type in _profile_text.lower()
        if _stack_template.exists() and not _stack_in_profile:
            plan.append(
                f"New stack ({project_type}) — run /learn after this session to seed your "
                f"knowledge graph with {_stack_key} concepts and analogies."
            )

    # 5. Pre-commit hooks — surface once so Claude knows commits go through them
    if t.get("pre_commit"):
        plan.append("Pre-commit hooks active — commits run checks automatically before staging")

    # 6. Other AI instruction files — surface for conflict awareness
    ai_ctx = t.get("ai_context", [])
    if ai_ctx:
        names = ", ".join(entry["file"] for entry in ai_ctx if isinstance(entry, dict))
        plan.append(f"Other AI context found: {names} — check for conflicts with youk contracts")

    # 7. Contract reminder if contracts exist (first one only — most load-bearing)
    if contracts:
        plan.append(f"Active contract: {contracts[0]}")

    # 8. Available spec/design docs (first session only hint — low priority)
    if docs_available and not resume_point.startswith("Resume:"):
        plan.append(f"Specs available: {', '.join(docs_available[:3])}")

    # 9. Doc-freshness gaps (up to 2 — surface before any new work starts)
    for gap in (doc_gaps or [])[:2]:
        plan.append(f"Doc sync: {gap}")

    return plan[:7]  # hard cap


def _check_doc_freshness() -> list[str]:
    """
    Two-part check called at session_start:
    1. Read docs/doc-map.yaml — flag any @mcp.tool() absent from the doc-map.
    2. Read concepts: block from doc-map — flag authority files newer than derived.
    Returns a combined list of gap strings (capped at 2 concept warnings).
    """
    doc_map_file = YOUK_ROOT / "docs" / "doc-map.yaml"
    if not doc_map_file.exists():
        return []

    undocumented: list[str] = []

    # Part 1: undocumented MCP tools
    try:
        import re
        import yaml  # already a dep (health.py uses it)
        doc_map = yaml.safe_load(doc_map_file.read_text()) or {}
        mcp_tools = doc_map.get("mcp_tools", {})
        mapped_tools: set[str] = set()
        for server_tools in mcp_tools.values():
            for entry in (server_tools or []):
                if isinstance(entry, dict) and "tool" in entry:
                    mapped_tools.add(entry["tool"])

        for server_file in [
            YOUK_ROOT / "servers" / "core" / "src" / "server.py",
            YOUK_ROOT / "servers" / "code" / "src" / "server.py",
        ]:
            if not server_file.exists():
                continue
            source = server_file.read_text()
            decorated = set(re.findall(
                r'@mcp\.tool\(\)\s+def (\w+)\s*\(', source, re.DOTALL
            ))
            for name in sorted(decorated - mapped_tools):
                undocumented.append(
                    f"tool '{name}' missing from docs/doc-map.yaml — "
                    "add it (and update README.md + docs/claude-md-template.md if needed)"
                )
    except Exception:
        pass

    # Part 2: concept coherence — authority file newer than derived files
    try:
        from doc_graph import (
            load_concept_graph,
            check_concept_staleness,
            format_staleness_warnings,
        )
        concepts = load_concept_graph(YOUK_ROOT)
        stale = check_concept_staleness(concepts, YOUK_ROOT, CLAUDE_ROOT)
        undocumented.extend(format_staleness_warnings(stale, cap=2))
    except Exception:
        pass

    return undocumented


def _routing_ran_last_session(current_slug: str) -> tuple[bool, str]:
    """
    Returns (ran, task_label) — True when route_task was called during this session.
    Uses state/route-task-ran.json written by server.py's route_task wrapper.
    Supports both legacy single-object format and new array format.
    """
    flag_file = YOUK_ROOT / "state" / "route-task-ran.json"
    if not flag_file.exists():
        return False, ""
    try:
        import json as _json
        raw = _json.loads(flag_file.read_text())
        entries = raw if isinstance(raw, list) else [raw]
        for entry in entries:
            if entry.get("slug") == current_slug:
                return True, entry.get("task", "")
    except Exception:
        pass
    return False, ""


def _read_forge_run() -> dict | None:
    """
    Return the skill-forge run summary from state/skill-forge-run.json, or None.
    Written by the skill-forge loop; surfaced in session_delta so a proactive forge
    run is always visible in the audit (distinct from reactive self_heal).
    """
    forge_file = YOUK_ROOT / "state" / "skill-forge-run.json"
    if not forge_file.exists():
        return None
    try:
        import json as _json
        return _json.loads(forge_file.read_text())
    except Exception:
        return None


def _count_pending_proposals() -> int:
    pending_file = YOUK_ROOT / "knowledge" / "proposals" / "PENDING.md"
    if not pending_file.exists():
        return 0
    content = pending_file.read_text()
    count = 0

    # Format 1: auto-generated PENDING-* blocks (from self_heal / session_end)
    _DONE_STATUSES = ("APPLIED", "SUPERSEDED", "CLOSED")
    for block in content.split("## PENDING-")[1:]:
        status_line = next(
            (ln for ln in block.splitlines() if "**Status:**" in ln),
            "",
        )
        if not any(s in status_line for s in _DONE_STATUSES):
            count += 1

    # Format 2: named ### PROPOSAL blocks (from simulate-experience / gate-check audits)
    # Each "### PROPOSAL" heading is one proposal; skip those marked SUPERSEDED inline.
    import re as _re
    positions = [m.start() for m in _re.finditer(r"^### PROPOSAL\b", content, _re.MULTILINE)]
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(content)
        block = content[start:end]
        if not any(s in block for s in _DONE_STATUSES):
            count += 1

    return count


def _merge_stale_checkpoint() -> None:
    """
    Recover audit entries for sessions that ended without /done.
    Checks two recovery sources (most-complete wins per session):

    1. session-open.json — written at every session_start, cleared at session_end.
       Covers ALL sessions, even those that never called compact_context.

    2. session-checkpoint.json — written by compact_context. Cleared at session_end
       and superseded by session-open.json (compact always clears session-open).

    Both files are deleted after being merged. Age guard: skip files < 5 min old
    (same-session race: session_start just wrote the file for THIS session).
    """
    audit_dir = CLAUDE_ROOT / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    for fname, label in [
        ("session-open.json", "tab-close"),
        ("session-checkpoint.json", "compact-checkpoint"),
    ]:
        stale_file = YOUK_ROOT / "state" / fname
        if not stale_file.exists():
            continue
        try:
            cp = json.loads(stale_file.read_text())
            cp_timestamp = cp.get("timestamp", "")
            cp_slug = cp.get("slug", "unknown")
            cp_plan = cp.get("plan_items", [])
            cp_resume = cp.get("resume_candidate", "")

            if cp_timestamp:
                cp_dt = datetime.strptime(cp_timestamp, "%Y-%m-%dT%H:%M:%SZ")
                age_minutes = (datetime.utcnow() - cp_dt).total_seconds() / 60
                if age_minutes > 5:
                    month = cp_timestamp[:7]
                    audit_file = audit_dir / f"{month}.md"
                    plan_text = "\n".join(f"- {item}" for item in cp_plan[:3]) if cp_plan else ""
                    entry = (
                        f"\n### Session — {cp_timestamp} ({label})\n"
                        f"Project: {cp_slug}\n"
                        f"Session ended without /done.\n"
                        f"{plan_text}\n"
                        f"Skills: none\n"
                        f"CloseCluster: no\n"
                        f"Commits: unknown\n"
                    )
                    with open(audit_file, "a") as f:
                        f.write(entry)
                    # If the checkpoint recorded a resume candidate (written by compact_context),
                    # persist it so next session has a meaningful resume point even on tab-close.
                    if cp_resume and cp_slug and cp_slug != "unknown":
                        _update_resume_point(cp_slug, f"Last working on: {cp_resume}")
        except Exception:
            pass  # never block session_start for recovery errors
        finally:
            try:
                stale_file.unlink()
            except Exception:
                pass


def start_session(project_dir: str) -> SessionState:
    # Recover stale checkpoint from a previous session that ended without /done.
    # This runs before any other work so the audit entry is written even if
    # session_start itself fails partway through.
    _merge_stale_checkpoint()

    state = _load_state()
    state["session_counter"] = state.get("session_counter", 0) + 1
    state["last_project"] = project_dir
    state["last_session"] = datetime.utcnow().isoformat()
    stack_ctx = _detect_stack_context(project_dir)
    state["stack"] = stack_ctx["stack"]
    state["framework"] = stack_ctx["framework"]
    state["domain"] = stack_ctx["domain"]
    state["project_purpose"] = _detect_project_purpose(project_dir)
    _save_state(state)

    slug = _slug(project_dir)
    project_type = _detect_project_type(project_dir)
    git_log = _read_git_log(project_dir)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Read last-seen BEFORE writing (write will update it to today)
    days_since_last: int | None = None
    _pre_ctx = _load_project_context(slug)
    if _pre_ctx:
        for _line in _pre_ctx.splitlines():
            if _line.startswith("last-seen:"):
                try:
                    _last_date = datetime.strptime(_line.split(":", 1)[1].strip(), "%Y-%m-%d")
                    days_since_last = (datetime.utcnow() - _last_date).days
                except Exception:
                    pass
                break

    _write_project_context(slug, project_type, git_log, first_seen=today, project_dir=project_dir)

    l2_resume, context_health = _load_l2_context(project_dir)
    existing_ctx = _load_project_context(slug)

    # Scan the project directory for standard context files (README, CLAUDE.md, docs/).
    # Capped reads — description snippets only, not full file dumps.
    project_scan = _scan_project_context_files(project_dir)

    # Merge context_health: in-project .claude/ files take precedence over scan-level
    if context_health == "NONE" and project_scan["context_level"] != "L1":
        context_health = project_scan["context_level"]

    # If no in-project context, check youk's external context.md for a resume point.
    # This is the zero-footprint path: no files needed in the project repo.
    if not l2_resume and existing_ctx:
        for line in existing_ctx.splitlines():
            if line.startswith("resume-from:"):
                l2_resume = line[len("resume-from:"):].strip()
                if l2_resume:
                    if context_health == "NONE":
                        context_health = "L1"
                break

    if existing_ctx and context_health == "NONE":
        context_health = "L1"

    # Cold-start bootstrap: when context is truly empty, run heuristic scan and
    # write a minimal context.md so the next session has something to resume from.
    # Zero API cost — pure file inspection.
    bootstrap_signals: list[str] = []
    if context_health in ("NONE", "L1") and project_type == "unknown" and not l2_resume:
        bootstrap_signals = _bootstrap_cold_start(project_dir, slug, project_scan.get("tooling", {}))
        if bootstrap_signals:
            context_health = "L1-bootstrap"

    # Priority-ordered resume point: L3 > L2 > external context.md > README snippet > bootstrap > git log
    if l2_resume:
        resume_point = l2_resume
    elif project_scan["readme_snippet"]:
        resume_point = f"Project: {project_scan['readme_snippet'][:120]}"
    elif bootstrap_signals:
        resume_point = f"First session — detected {', '.join(bootstrap_signals[:4])}"
    elif git_log:
        first_commit = git_log.splitlines()[0]
        resume_point = f"Last commit: {first_commit}"
    else:
        resume_point = "No prior context found — fresh session."

    global_contracts = _load_global_contracts()
    project_contracts = _load_contracts(slug)
    contracts = global_contracts + project_contracts  # global first, project overrides

    # Snapshot for session_end delta: how many contracts + domain concepts exist RIGHT NOW
    # so session_end can compute what grew during this session.
    _domain_dir = YOUK_ROOT / "knowledge" / "domain"
    state["session_start_contracts"] = len(contracts)
    state["session_start_domain_concepts"] = (
        sum(1 for f in _domain_dir.glob("*.md") if f.name != "gaps.md")
        if _domain_dir.exists() else 0
    )
    _save_state(state)

    audit_dir = CLAUDE_ROOT / "audit"
    close_cluster_missed, orchestrate_pending = _parse_last_session_flags(audit_dir)

    pending = _count_pending_proposals()
    counter = state["session_counter"]
    health_check_due = counter % 3 == 0
    dashboard_summary = _compute_dashboard_summary(audit_dir, pending, slug=slug)

    doc_gaps = _check_doc_freshness()

    new_commits = len([ln for ln in git_log.splitlines() if ln.strip()]) if git_log else 0

    session_plan = _generate_session_plan(
        slug=slug,
        resume_point=resume_point,
        contracts=contracts,
        pending_proposals=pending,
        close_cluster_missed=close_cluster_missed,
        project_type=project_type,
        doc_gaps=doc_gaps,
        docs_available=project_scan["docs_available"],
        has_project_claude_md=bool(project_scan["claude_md"]),
        tooling=project_scan.get("tooling"),
        session_counter=counter,
        bootstrap_signals=bootstrap_signals,
        days_since_last=days_since_last,
        new_commits=new_commits,
    )

    # Staleness awareness — surface when returning after a significant gap.
    # For gaps ≥30 days, fetch commits-since-gap from git so the plan answers
    # "what changed while you were gone" with real data, not just a count.
    if days_since_last is not None and days_since_last >= 7:
        if days_since_last >= 30:
            gap_commit_count, gap_subjects = _read_git_log_since_days(project_dir, days_since_last)
        else:
            # Short gap: use the already-loaded git_log (last 5 commits)
            recent_lines = git_log.splitlines()[:3] if git_log else []
            gap_subjects = [ln.split(" ", 1)[1] if " " in ln else ln for ln in recent_lines]
            gap_commit_count = new_commits
        subjects_str = " / ".join(s.strip() for s in gap_subjects if s.strip())
        commits_note = (
            f" — {gap_commit_count} commit(s) since you left. Recent: {subjects_str}"
            if subjects_str else f" — {gap_commit_count} commit(s) since last session"
        )
        session_plan.append(f"Returning after {days_since_last} days{commits_note}")
        if days_since_last >= 7 and contracts:
            session_plan.insert(0,
                f"Returning after {days_since_last} days — {len(contracts)} saved rule(s) may be stale. "
                f"Say 'show my contracts' to review them before we start."
            )
    elif close_cluster_missed and days_since_last != 0:
        # Retrospective recovery: previous session closed without /done.
        # Fire regardless of commit count — exploration and planning sessions that
        # produced no commits are still worth capturing via /learn.
        # Guard: days_since_last != 0 prevents false trigger on same-day re-opens.
        recent_subjects = []
        for ln in git_log.splitlines()[:3]:
            subject = ln.split(" ", 1)[1].strip() if " " in ln else ln.strip()
            if subject:
                recent_subjects.append(subject)
        if new_commits > 0:
            commits_summary = f" — {new_commits} commit(s)" + (
                f": {' / '.join(recent_subjects)}" if recent_subjects else ""
            )
        else:
            commits_summary = " (no commits — patterns still worth capturing)"
        session_plan.insert(0,
            f"⚠ Last session closed without /done{commits_summary}. "
            "Run /learn now to extract patterns before starting new work."
        )

    # Routing recovery: detect M+ work that started without route_task.
    # Reads route-task-ran.json (written by server.py) to check if routing fired.
    # If last session had M+ active task but route_task never ran, surface recovery item.
    # Guard: only fire on returning sessions (days_since_last != 0) to avoid false triggers.
    if days_since_last != 0:
        routing_ran, routed_task = _routing_ran_last_session(slug)
        if not routing_ran:
            # Check if there was meaningful M+ work last session (new commits is a proxy).
            # Skip if no commits — routing miss in exploration sessions isn't actionable.
            if new_commits > 0:
                session_plan.insert(0,
                    "⚠ Last session: routing was skipped. "
                    "Running /build now to catch any missed direction gates and NFR checks."
                )

    # 3B2 — Skill-skip warning: capability skills unused for 3+ consecutive sessions
    _, consecutive_skill_skips = _compute_skill_invocation_rate(audit_dir)
    if consecutive_skill_skips >= 3:
        session_plan.append(
            f"⚠ No capability skill invoked in last {consecutive_skill_skips} sessions — "
            "compounding has stalled. Today: use /build for code tasks, /review before commits, "
            "/done at end (includes /learn). Skills are what make sessions compound."
        )

    # 3C — Surface research-inbox findings (global + project-specific)
    research_patterns = _scan_research_inbox(slug=slug)
    if research_patterns:
        count = len(research_patterns)
        names = ", ".join(research_patterns[:3])
        suffix = f" (+{count - 3} more)" if count > 3 else ""
        session_plan.append(
            f"{count} research finding(s) in knowledge/research-inbox/ — "
            f"{names}{suffix}. Run '/research stack propose' to queue as proposals."
        )
    else:
        # Suggest stack briefing when inbox is empty or stale (>14 days)
        project_inbox = YOUK_ROOT / "knowledge" / "projects" / slug / "research-inbox"
        inbox_stale = True
        if project_inbox.exists():
            cutoff = datetime.utcnow().timestamp() - (14 * 24 * 3600)
            inbox_stale = not any(
                f.suffix == ".md" and f.stat().st_mtime > cutoff
                for f in project_inbox.iterdir()
                if f.name not in (".gitkeep", "README.md")
            )
        if inbox_stale:
            session_plan.append(
                "No recent stack briefing — run '/research stack' to generate "
                "actionable findings for your stack (no API key required)."
            )

    # 3D — Token budget used last session (budget utilization, not youk overhead ratio)
    budget_pct, _budget_limit = _last_token_overhead()
    if budget_pct is not None:
        if budget_pct > 90:
            session_plan.append(
                f"⚠ Last session used {budget_pct}% of token budget — "
                "consider splitting large tasks or using /close earlier"
            )
        else:
            session_plan.append(
                f"Last session: {budget_pct}% of token budget used"
            )

    # Cross-project contract transfer: surface 1 contract from another project when
    # current project is new (< 3 contracts). Transfer is opt-in — developer says
    # 'save this contract' to adopt it. Never auto-saves.
    xp = _find_cross_project_contract(slug, contracts)
    if xp:
        src_slug, xp_contract = xp
        session_plan.append(
            f"From {src_slug}: '{xp_contract}' — "
            "say 'save this contract' to adopt for this project."
        )

    # Survey staleness: surface if no survey exists or it's >20 commits behind HEAD
    survey_file = YOUK_ROOT / "knowledge" / "projects" / slug / "survey.md"
    survey_stale_note = ""
    survey_commit_hash = state.get("survey_commit_hash", "")
    if not survey_file.exists():
        survey_stale_note = "No codebase survey yet — run /survey to map this project (12-question map: stack, architecture, modules, entry points, integrations)"
    elif survey_commit_hash:
        commits_since = _count_commits_since(project_dir, survey_commit_hash)
        if commits_since > 20:
            survey_stale_note = f"Codebase survey is {commits_since} commits old — run /survey to refresh"
    # Only surface survey note when it's genuinely actionable:
    # - first 3 sessions (new user should survey early)
    # - returning after ≥14 days (codebase may have drifted)
    # - survey truly missing (not just stale)
    _survey_is_missing = not survey_file.exists()
    _survey_is_actionable = (
        counter <= 3
        or (days_since_last is not None and days_since_last >= 14)
        or _survey_is_missing
    )
    if survey_stale_note and _survey_is_actionable:
        session_plan.append(survey_stale_note)

    # Decision staleness: flag decisions.md entries older than 90 days without recent reference.
    # Stale decisions are load-bearing architectural choices that may no longer reflect reality.
    stale_decisions = _find_stale_decisions(slug)
    if stale_decisions:
        for decision_heading, age_days in stale_decisions[:1]:  # one at a time — not a flood
            session_plan.append(
                f"Stale decision ({age_days}d old): '{decision_heading[:60]}' — "
                "review in decisions.md and confirm it still holds, or supersede it."
            )

    # Persist session plan so compact_context can include it in briefs
    plan_file = YOUK_ROOT / "state" / "session-plan.json"
    try:
        import json as _json
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(_json.dumps({
            "plan": session_plan,
            "slug": slug,
            "generated_at": datetime.utcnow().isoformat(),
        }, indent=2))
    except Exception:
        pass  # non-critical — compact_context degrades gracefully without it

    # Build compact brief inline so Claude can paste it verbatim in the first response.
    # This anchors contracts before any context pressure, eliminating the need for a
    # separate compact_context call at session open (saves 1 MCP round-trip per session).
    # Correct sequencing: session-plan.json was just written above, so build_brief reads
    # fresh data.
    try:
        brief = _build_brief(project_dir).get("brief", "")
    except Exception:
        brief = ""

    # Write a session stub to the audit dir immediately at session open.
    # This breadcrumb survives even if the developer tabs out without calling /done —
    # audit logs will show INCOMPLETE rather than a silent gap.
    # Breadcrumb written at session_start (not just first task_checkpoint) so ALL sessions
    # leave a record, not just sessions that reach their first commit.
    _write_session_stub(slug, counter)

    # Write session-open.json AFTER build_brief — build_brief deletes this file
    # (because compact_context supersedes it), so we must write it last.
    open_file = YOUK_ROOT / "state" / "session-open.json"
    try:
        open_file.write_text(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "slug": slug,
            "plan_items": session_plan[:3],
        }, indent=2))
    except Exception:
        pass

    # Adaptive ceremony: compute nfr_check autonomy rate from recent audit.
    # When rate ≥ 0.4, nfr_check runs in validate mode (coverage check only, no prompting).
    # This is the compounding signal made visible: ceremony reduces as developer grows.
    _nfr_autonomy_rate = 0.0
    _nfr_autonomy_mode = "standard"
    try:
        from health import _parse_audit_sessions, _compute_skill_autonomy_rate, _read_recent_audit_logs
        _recent_texts = _read_recent_audit_logs(days=90)
        _recent_sessions = _parse_audit_sessions(_recent_texts)
        _nfr_autonomy_rate = _compute_skill_autonomy_rate(_recent_sessions, "nfr_check")
        _nfr_autonomy_mode = "validate" if _nfr_autonomy_rate >= 0.4 else "standard"
    except Exception:
        pass  # degrade gracefully — standard mode is always safe

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
        project_context_files={
            "claude_md_found": bool(project_scan["claude_md"]),
            "readme_snippet": project_scan["readme_snippet"],
            "docs_available": project_scan["docs_available"],
            "context_level": project_scan["context_level"],
            "tooling": project_scan.get("tooling", {}),
        },
        dashboard_summary=dashboard_summary,
        brief=brief,
        nfr_autonomy_mode=_nfr_autonomy_mode,
        developer_autonomy_rate=round(_nfr_autonomy_rate, 2),
    )


def _write_session_stub(slug: str, session_counter: int) -> None:
    """Write a minimal per-project audit stub on first task_checkpoint.

    Serves as a breadcrumb: if the developer tabs out without /done, the audit
    dir shows a stub entry with date + status INCOMPLETE rather than a silent gap.
    session_end does NOT overwrite this — both coexist. The stub signals "session
    started, task_checkpoint fired, but loop was not closed."
    Only writes once per calendar day to avoid noise on repeated checkpoints.
    """
    if not slug:
        return
    audit_dir = YOUK_ROOT / "knowledge" / "projects" / slug / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    stub_file = audit_dir / f"{today}-session-stub.txt"
    if stub_file.exists():
        return
    try:
        stub_file.write_text(
            f"Session #{session_counter} stub — {today}\n"
            f"Status: INCOMPLETE (tab-close or crash — /done not called)\n"
            f"Contracts: see contracts.md (saved as you go, survive tab-close)\n"
            f"Org score: N/A — session not closed\n"
            f"close_cluster: no\n"
        )
    except Exception:
        pass


def update_convergence_state(
    current_state: dict,
    angle: str,
    status: str,
    pressure_source: str = "model",
    unknown_unknown: str | None = None,
) -> dict:
    """
    Update the convergence state for a single angle.

    angle: one of structural | operational | experiential | adversarial | temporal | outcome | semantic
    status: "converged" | "diverged" | "unknown"
    pressure_source: "user" | "model" — only user-generated pressure that didn't move
                     the answer counts as a convergence signal. Model-generated = noise.
    unknown_unknown: if the angle cannot be resolved without external collision, describe it here.

    Returns the updated convergence_state dict.
    """
    _ANGLES = {"structural", "operational", "experiential", "adversarial", "temporal", "outcome", "semantic"}
    cs = dict(current_state) if current_state else {
        a: "unknown" for a in _ANGLES
    }
    cs.setdefault("unknown_unknowns", [])
    cs.setdefault("last_external_pressure", None)
    cs.setdefault("angles_converged", 0)

    if angle not in _ANGLES:
        return cs

    # Only credit convergence when pressure came from the user — not the model.
    if status == "converged" and pressure_source != "user":
        status = "unknown"

    cs[angle] = status
    if unknown_unknown and unknown_unknown not in cs["unknown_unknowns"]:
        cs["unknown_unknowns"].append(unknown_unknown)

    if pressure_source == "user":
        cs["last_external_pressure"] = angle

    converged_count = sum(1 for a in _ANGLES if cs.get(a) == "converged")
    cs["angles_converged"] = converged_count
    unknown_count = sum(1 for a in _ANGLES if cs.get(a) in ("unknown", "diverged"))
    cs["distance_from_optimum"] = f"{unknown_count}/7 not yet converged"

    return cs


def task_checkpoint(
    project_dir: str,
    task_label: str,
    size: str = "M",
    session_learnings: dict | None = None,
) -> dict:
    """
    Write a mid-session checkpoint when a task completes.

    XS/S: rebuilds context brief only (same as compact_context — zero audit overhead).
    M+: compact + appends one line to state/task-checkpoints.jsonl so session_end
    can roll up a structured task history in the final audit entry.

    session_learnings: optional observations from the current sub-task, e.g.
      {"contract_unsaved": "always use async", "skill_gap": "nfr_check skipped",
       "route_correction": "S→M override"}
    When the same gap_type appears 2+ times across checkpoints, returns
    pattern_trigger so Claude can act immediately (mid-session adaptation).

    Returns: brief (paste verbatim), checkpoint_written, pattern_trigger (if any).
    """
    # Write session stub on first checkpoint so tab-close leaves a breadcrumb
    current_state = _load_state()
    _slug_val = _slug(current_state.get("last_project", project_dir))
    _counter = current_state.get("session_counter", 0)
    _write_session_stub(_slug_val, _counter)

    brief_result = _build_brief(project_dir)
    checkpoint_written = False
    pattern_trigger: list[str] = []

    if size.upper() not in ("XS", "S"):
        cp = {
            "timestamp": datetime.utcnow().isoformat(),
            "task": task_label[:200],
            "size": size.upper(),
        }
        if session_learnings:
            cp["learnings"] = {k: str(v)[:200] for k, v in session_learnings.items()}

        cp_file = YOUK_ROOT / "state" / "task-checkpoints.jsonl"
        try:
            cp_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cp_file, "a") as f:
                f.write(json.dumps(cp) + "\n")
            checkpoint_written = True
        except Exception:
            pass

        # Pattern accumulator: count gap types across all checkpoints this session.
        # When the same gap type appears 2+ times, surface it as a pattern_trigger
        # so Claude can act immediately (mid-session adaptation) without waiting for /done.
        if checkpoint_written:
            try:
                all_lines = [
                    json.loads(ln)
                    for ln in cp_file.read_text().splitlines()
                    if ln.strip()
                ]
                gap_counts: dict[str, int] = {}
                for entry in all_lines:
                    for gap_type in entry.get("learnings", {}):
                        gap_counts[gap_type] = gap_counts.get(gap_type, 0) + 1
                pattern_trigger = [
                    f"{gap_type} (seen {count}x this session)"
                    for gap_type, count in gap_counts.items()
                    if count >= 2
                ]
            except Exception:
                pass

    # Write mid-session resume point so tomorrow's card shows last known task
    # even if the developer closed the tab without /done.
    if _slug_val and size.upper() not in ("XS", "S"):
        _update_resume_point(_slug_val, f"In progress: {task_label[:180]}")

    # Routing breadcrumb gate: for M+ tasks, verify route_task was called before work started.
    # If the breadcrumb is absent, routing was bypassed — surface it so the model can correct now.
    routing_missed = False
    if size.upper() not in ("XS", "S"):
        breadcrumb_file = YOUK_ROOT / "state" / "routing-breadcrumb.json"
        if breadcrumb_file.exists():
            try:
                breadcrumb_file.unlink()  # consume: one breadcrumb per task
            except Exception:
                pass
        else:
            routing_missed = True

    result = {
        "brief": brief_result.get("brief", ""),
        "checkpoint_written": checkpoint_written,
        "instruction": "Paste the 'brief' verbatim in your response to anchor context.",
    }
    if routing_missed:
        result["routing_missed"] = True
        result["routing_action"] = (
            "route_task was not called before this M+ task. "
            "Call route_task now and run the returned skill chain (challenge → nfr_check → dev_loop) "
            "before continuing. This session will not compound without it."
        )
    if pattern_trigger:
        result["pattern_trigger"] = pattern_trigger
        result["pattern_action"] = (
            "Recurring pattern detected — act now per mid-session adaptation rules: "
            "assess_skill → add_proposal → apply_proposal(confirmed=True) for SKILL_EDIT gaps. "
            "Do not defer to /done."
        )

    # Goal re-evaluation: check whether the completed task satisfies the session goal.
    # If goal_met=False and goal_gap is non-empty, CLAUDE.md's loop instruction fires:
    # derive the next task toward the stated goal and continue — do not stop.
    goal_check = _check_session_goal(task_label)
    if goal_check:
        result["goal_check"] = goal_check

    # Surface convergence state so the model can track distance from optimum.
    # The model reads this and updates angles via update_convergence_state() as
    # external pressure arrives. Included in every M+ checkpoint return.
    if size.upper() not in ("XS", "S"):
        cs_file = YOUK_ROOT / "state" / "convergence-state.json"
        try:
            if cs_file.exists():
                result["convergence_state"] = json.loads(cs_file.read_text())
            else:
                result["convergence_state"] = {
                    "structural": "unknown", "operational": "unknown",
                    "experiential": "unknown", "adversarial": "unknown",
                    "temporal": "unknown", "outcome": "unknown", "semantic": "unknown",
                    "unknown_unknowns": [], "last_external_pressure": None,
                    "angles_converged": 0, "distance_from_optimum": "7/7 not yet converged",
                }
        except Exception:
            pass

    return result


def write_session_goal(
    raw_input: str,
    success_criteria: str,
    observable_outcome: str = "",
) -> None:
    """
    Persist a session goal to state/session-goal.json.

    Called by optimize_intent in server.py after it confirms the goal is
    non-ambiguous and the success_criteria is concrete. Extracted here so
    tests can verify goal persistence without importing the MCP-dependent server.
    """
    goal_file = YOUK_ROOT / "state" / "session-goal.json"
    import datetime as _dt

    goal_file.parent.mkdir(parents=True, exist_ok=True)
    goal_file.write_text(json.dumps({
        "stated_goal": raw_input,
        "success_criteria": success_criteria,
        "observable_outcome": observable_outcome,
        "written_at": _dt.datetime.utcnow().isoformat(),
        "goal_met": False,
    }))
    # Reset coverage accumulator — stale coverage from a prior goal or project
    # would cause premature goal_met=True on the new goal.
    coverage_file = goal_file.parent / "session-goal-coverage.json"
    try:
        coverage_file.write_text(json.dumps({"covered": []}))
    except Exception:
        pass


def _check_session_goal(completed_task: str) -> dict | None:
    """
    Read state/session-goal.json and evaluate whether completed_task satisfies it.

    Returns None if no goal file exists (goal-tracking not active).
    Returns {goal_met: bool, stated_goal: str, success_criteria: str, goal_gap: str}
    where goal_gap is empty when goal_met=True.
    """
    goal_file = YOUK_ROOT / "state" / "session-goal.json"
    if not goal_file.exists():
        return None

    try:
        goal_data = json.loads(goal_file.read_text())
    except Exception:
        return None

    if goal_data.get("goal_met"):
        return {
            "goal_met": True,
            "stated_goal": goal_data.get("stated_goal", ""),
            "success_criteria": goal_data.get("success_criteria", ""),
            "goal_gap": "",
        }

    stated_goal = goal_data.get("stated_goal", "")
    success_criteria = goal_data.get("success_criteria", "")
    observable_outcome = goal_data.get("observable_outcome", "")

    # Heuristic: if the task label references a key term from success_criteria or
    # observable_outcome, mark as partially satisfied but not done.
    # The loop continues until all criteria terms are addressed by a checkpoint.
    criteria_words = set(
        w.lower()
        for w in (success_criteria + " " + observable_outcome).split()
        if len(w) > 4
    )
    task_words = set(w.lower() for w in completed_task.split())
    overlap = criteria_words & task_words

    # Accumulate covered criteria across checkpoints in a separate state file
    coverage_file = YOUK_ROOT / "state" / "session-goal-coverage.json"
    covered: set[str] = set()
    try:
        if coverage_file.exists():
            covered = set(json.loads(coverage_file.read_text()).get("covered", []))
    except Exception:
        pass

    covered |= overlap
    try:
        coverage_file.write_text(json.dumps({"covered": list(covered)}))
    except Exception:
        pass

    # Goal is met when covered words represent ≥60% of criteria words,
    # or when the task explicitly states goal completion.
    completion_signals = {"complete", "done", "finished", "shipped", "merged", "deployed"}
    explicit_done = bool(completion_signals & task_words) and bool(overlap)

    coverage_ratio = len(covered) / len(criteria_words) if criteria_words else 1.0
    goal_met = explicit_done or coverage_ratio >= 0.6

    if goal_met:
        # Persist the goal_met flag so future checkpoints don't re-evaluate
        try:
            goal_data["goal_met"] = True
            goal_file.write_text(json.dumps(goal_data))
        except Exception:
            pass
        return {
            "goal_met": True,
            "stated_goal": stated_goal,
            "success_criteria": success_criteria,
            "goal_gap": "",
        }

    goal_gap = (
        f"Goal not yet satisfied. Criteria: '{success_criteria}'. "
        f"Covered so far: {', '.join(sorted(covered)) or 'none'}. "
        f"Derive the next task that moves closer to this outcome."
    )
    return {
        "goal_met": False,
        "stated_goal": stated_goal,
        "success_criteria": success_criteria,
        "goal_gap": goal_gap,
    }


def _compute_session_delta(
    contracts_saved: int,
    global_promoted: int,
    skills_used: list[str] | None,
    slug: str,
) -> dict:
    """Compute what grew this session vs. what existed at session_start."""
    state = _load_state()
    start_domain = state.get("session_start_domain_concepts", 0)

    domain_dir = YOUK_ROOT / "knowledge" / "domain"
    current_domain = (
        sum(1 for f in domain_dir.glob("*.md") if f.name != "gaps.md")
        if domain_dir.exists() else 0
    )
    domain_added = max(0, current_domain - start_domain)
    capability_count = sum(1 for s in (skills_used or []) if s in _CAPABILITY_SKILLS)

    forge = _read_forge_run()
    forge_created = len(forge.get("skills_created", [])) if forge else 0
    forge_sharpened = len(forge.get("skills_sharpened", [])) if forge else 0
    forge_active = forge_created > 0 or forge_sharpened > 0

    if forge_active:
        verdict = f"COMPOUNDING — skill-forge created {forge_created}, sharpened {forge_sharpened} skill(s)"
    elif contracts_saved > 0 or domain_added > 0:
        verdict = "COMPOUNDING — knowledge base grew this session"
    elif capability_count >= 1:
        verdict = "PARTIAL — skills fired but no new knowledge captured"
    else:
        verdict = "STATIC — no new knowledge, no capability skills"

    delta = {
        "contracts_added": contracts_saved,
        "contracts_total": len(_load_contracts(slug)),
        "domain_concepts_added": domain_added,
        "domain_concepts_total": current_domain,
        "global_contracts_promoted": global_promoted,
        "capability_skills_count": capability_count,
        "verdict": verdict,
    }
    if forge:
        delta["forge_skills_created"] = forge_created
        delta["forge_skills_sharpened"] = forge_sharpened
        delta["forge_converged"] = forge.get("converged", False)
    return delta


def end_session(
    summary: str,
    commits_made: bool,
    explicit_contracts: list[str] | None = None,
    skills_used: list[str] | None = None,
    close_cluster: bool = False,
    skill_gaps: dict[str, list[str]] | None = None,
    mid_session_adaptations_applied: int = 0,
    findings: dict | None = None,
    finding_categories: list[str] | None = None,
    nfr_gaps: list[str] | None = None,
    direction_reversal: bool = False,
    developer_caught: list[str] | None = None,
) -> dict:
    """
    Write structured audit log entry, detect and save contract phrases.

    explicit_contracts: Contract lines to save directly (e.g. extracted from
    conversation by Claude before calling session_end). These take priority over
    the phrase-detected ones and are written verbatim to contracts.md.

    findings: dict with keys CRITICAL, HIGH, MEDIUM, LOW (int counts) from
    code-review or security-review. Written as Findings: N (CRITICAL=X, HIGH=Y) line.

    finding_categories: list of finding category labels (e.g. ["auth", "idempotency"]).
    Written as FindingCategories: auth,idempotency line. Parsed by health.py for
    recurring pattern detection.

    nfr_gaps: list of NFR gap categories flagged pre-build by nfr-check.
    Written as NFRGap: {category} lines.

    direction_reversal: True when challenge skill rejected the initial direction.
    Written as DirectionReversal: yes line. Feeds prevented_cost_score.

    developer_caught: list of skill names where the developer's prompt already
    answered the questions before the skill ran (e.g. ["nfr_check", "challenge"]).
    Written as DeveloperCaught: {skill1},{skill2} line. Parsed by health.py to
    compute developer_autonomy_rate — the signal that the compounding loop is working.
    """
    # 3B — Auto-draft summary when developer passes empty string or "done"
    # Reads the session plan written by session_start so the audit entry is useful
    # even without a full summary. Structural fix for the 0% close-cluster rate.
    if not summary or summary.strip().lower() in ("done", ""):
        plan_file = YOUK_ROOT / "state" / "session-plan.json"
        try:
            plan_data = json.loads(plan_file.read_text())
            plan_items = plan_data.get("plan", [])
            plan_slug = plan_data.get("slug", "unknown")
            if plan_items:
                summary = (
                    f"## Session on {plan_slug}\n\n"
                    + "\n".join(f"- {item}" for item in plan_items[:5])
                    + "\n\n(Auto-drafted from session plan.)"
                )
            else:
                summary = "Session completed."
        except Exception:
            summary = "Session completed."

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
    skills_line = ", ".join(skills_used) if skills_used else "none"
    close_line = "yes" if close_cluster else "no"
    gap_lines = ""
    if skill_gaps:
        for skill_name, gaps in skill_gaps.items():
            for gap in gaps:
                gap_lines += f"SkillGap: {skill_name} — {gap}\n"
    adaptations_line = f"MidSessionAdaptations: {mid_session_adaptations_applied}\n" if mid_session_adaptations_applied > 0 else ""

    # Outcome quality fields — written when capability review skills ran with findings
    findings_line = ""
    if findings:
        total = sum(findings.values())
        parts = [f"{k}={v}" for k, v in findings.items() if v > 0]
        findings_line = f"Findings: {total} ({', '.join(parts)})\n" if parts else f"Findings: {total}\n"
    finding_categories_line = ""
    if finding_categories:
        finding_categories_line = f"FindingCategories: {','.join(finding_categories)}\n"
    nfr_gap_lines = ""
    if nfr_gaps:
        nfr_gap_lines = "".join(f"NFRGap: {gap}\n" for gap in nfr_gaps)
    direction_reversal_line = "DirectionReversal: yes\n" if direction_reversal else ""
    # FramingCorrect: yes when the goal translation was correct (no direction reversal).
    # Parsed by health._parse_audit_sessions() to compute framing_accuracy_rate in org_score.
    framing_correct_line = f"FramingCorrect: {'no' if direction_reversal else 'yes'}\n"
    # DeveloperCaught: skills the developer pre-empted by answering questions unprompted.
    # Rising count across sessions = the compounding loop is working — developer internalised the pattern.
    developer_caught_line = ""
    if developer_caught:
        developer_caught_line = f"DeveloperCaught: {','.join(developer_caught)}\n"

    token_data = _read_and_clear_tokens()
    total_tokens = token_data["total_input"] + token_data["total_output"]
    budget = token_data.get("token_budget", 0)
    if total_tokens > 0 and budget > 0:
        pct = round(total_tokens / budget * 100)
        tokens_line = f"Tokens: {total_tokens}/{budget} ({pct}%)\n"
    elif total_tokens > 0:
        tokens_line = f"Tokens: {total_tokens} (no budget set)\n"
    else:
        tokens_line = ""

    entry = (
        f"\n### Session — {timestamp}\n"
        f"Project: {_slug(_load_state().get('last_project', ''))}\n"
        f"{summary}\n"
        f"Skills: {skills_line}\n"
        f"CloseCluster: {close_line}\n"
        f"Commits: {'yes' if commits_made else 'no'}\n"
        f"{tokens_line}"
        f"{adaptations_line}"
        f"{gap_lines}"
        f"{findings_line}"
        f"{finding_categories_line}"
        f"{nfr_gap_lines}"
        f"{direction_reversal_line}"
        f"{framing_correct_line}"
        f"{developer_caught_line}"
    )

    with open(audit_file, "a") as f:
        f.write(entry)

    # Roll up mid-session task checkpoints (written by task_checkpoint tool).
    # Appended as a single structured line so self_heal can parse task history.
    cp_file = YOUK_ROOT / "state" / "task-checkpoints.jsonl"
    if cp_file.exists():
        try:
            cp_lines = [json.loads(ln) for ln in cp_file.read_text().splitlines() if ln.strip()]
            if cp_lines:
                task_summary = "; ".join(
                    f"{cp.get('task', '?')[:50]} ({cp.get('size', '?')})"
                    for cp in cp_lines[:5]
                )
                with open(audit_file, "a") as f:
                    f.write(f"TaskCheckpoints: {len(cp_lines)} — {task_summary}\n")
        except Exception:
            pass
        try:
            cp_file.unlink()
        except Exception:
            pass

    # Write convergence state to audit — distance from optimum at session close.
    # Reality writeback: if convergence-state.json exists, log angles_converged
    # and any unknown_unknowns so self_heal can track cross-session drift.
    cs_file = YOUK_ROOT / "state" / "convergence-state.json"
    if cs_file.exists():
        try:
            cs = json.loads(cs_file.read_text())
            angles_converged = cs.get("angles_converged", 0)
            distance = cs.get("distance_from_optimum", "unknown")
            unknown_unknowns = cs.get("unknown_unknowns", [])
            uu_line = f"UnknownUnknowns: {'; '.join(unknown_unknowns)}\n" if unknown_unknowns else ""
            with open(audit_file, "a") as f:
                f.write(f"ConvergenceAtClose: {angles_converged}/7 angles — {distance}\n")
                if uu_line:
                    f.write(uu_line)
            # Reset convergence state for next session — angles earned this session
            # don't carry over; next session starts from unknown and earns convergence fresh.
            cs_file.unlink()
        except Exception:
            pass

    # Clear both recovery files — session_end is the authoritative audit entry.
    # If these aren't cleared, next session_start would write duplicate entries.
    for _recovery_file in [
        YOUK_ROOT / "state" / "session-checkpoint.json",
        YOUK_ROOT / "state" / "session-open.json",
    ]:
        if _recovery_file.exists():
            try:
                _recovery_file.unlink()
            except Exception:
                pass

    # Write contracts to disk so they survive future sessions and compact_context can pin them
    current_state = _load_state()
    slug = _slug(current_state.get("last_project", ""))
    contracts_to_save = explicit_contracts or detected_contracts
    _wc = write_contracts(slug, contracts_to_save) if slug and contracts_to_save else {"added": 0, "conflicts": []}
    contracts_saved = _wc["added"]

    # Append ContractsSaved to the audit entry now that we know the count.
    # This must happen after write_contracts() — the entry was already written above
    # without this field because contracts hadn't been computed yet.
    with open(audit_file, "a") as f:
        f.write(f"ContractsSaved: {contracts_saved}\n")

    # Write the resume point for the next session into external context.md (zero footprint).
    # Extract: first non-empty line after a ## heading, or first non-empty line of summary.
    # Cross-project bleed guard: use the slug from session-open.json (written at session_start)
    # rather than last_project. If a session was opened in project A but did work described as
    # project B, last_project still points to A — but summary content would contaminate A's
    # resume-from with B's work description. session-open.json is authoritative for "what
    # project this session was opened as."
    resume_slug = slug
    try:
        open_file = YOUK_ROOT / "state" / "session-open.json"
        if open_file.exists():
            open_data = json.loads(open_file.read_text())
            open_slug = open_data.get("slug", "")
            if open_slug and open_slug != slug:
                resume_slug = open_slug
    except Exception:
        pass

    if resume_slug:
        resume_text = ""
        lines = summary.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("##"):
                for next_line in lines[i + 1:]:
                    if next_line.strip():
                        resume_text = next_line.strip()
                        break
                if resume_text:
                    break
        if not resume_text:
            resume_text = next((ln.strip() for ln in lines if ln.strip()), "")
        if resume_text:
            _update_resume_point(resume_slug, resume_text)

    session_close_detected = any(
        marker in summary
        for marker in ["FLUSHED", "[MENTAL MODEL UPDATE", "context-sync end", "learn complete"]
    )

    # 3A — Promote generalizable contracts directly to knowledge/global/contracts.md.
    # Project-specific contracts already went to contracts.md above.
    # Generalizable ones (no file paths, expresses a methodology) go straight to global —
    # prefixed [auto-promoted] so the developer can review and clean up later.
    global_contracts_promoted = 0
    all_contracts_for_xp = explicit_contracts or detected_contracts
    if all_contracts_for_xp and slug:
        try:
            generalizable = [c for c in all_contracts_for_xp if _is_generalizable(c)]
            if generalizable:
                result = _promote_generalizable_to_global(generalizable)
                global_contracts_promoted = result.get("promoted", 0)
        except Exception:
            pass

    # 3B — Cross-project pattern scan at session close.
    # Surfaces contracts appearing in 2+ projects so the developer can promote them globally.
    # Runs here (not only on /health) so patterns are caught at the moment of reflection.
    emerging_global_patterns: list[dict] = []
    try:
        from health import _detect_cross_project_patterns
        candidates = _detect_cross_project_patterns(min_projects=2)
        if candidates:
            emerging_global_patterns = candidates[:3]
    except Exception:
        pass

    # M+ skill gate: if close_cluster requested but no capability skill was used,
    # surface a warning so Claude can invoke one retroactively before the loop closes.
    skill_gate_warning = ""
    if close_cluster and not _has_capability_skill(skills_used or []):
        skill_gate_warning = (
            "No capability skill invoked this session. "
            "Invoke one retroactively (code-review at minimum) or pass "
            "skill_gaps={'skill': ['reason']} to document the miss."
        )

    # /learn enforcement — /learn is non-optional at /done.
    # Separate key so the capability-skill gate and the /learn gate are independently checkable.
    learn_ran = "learn" in (skills_used or [])
    learn_gate_warning = ""
    if close_cluster and not learn_ran:
        learn_gate_warning = (
            "/learn has not run this session. "
            "/learn extracts patterns into knowledge/domain/ — it is what makes today compound "
            "into tomorrow's starting point. Run /learn before considering this session closed, "
            "or pass skills_used=['learn'] if it ran implicitly."
        )

    session_delta = _compute_session_delta(
        contracts_saved=contracts_saved,
        global_promoted=global_contracts_promoted,
        skills_used=skills_used,
        slug=slug,
    )

    # Session autopsy: surface "what did you plan but not finish?" when real work happened.
    # Only ask when there were skills or commits — avoids nagging on exploration sessions.
    autopsy_question = ""
    if close_cluster and (commits_made or _has_capability_skill(skills_used or [])):
        plan_items = _load_session_plan_items(slug)
        autopsy_question = (
            "Before closing: anything you planned for this session that didn't happen? "
            "(One line — it becomes item 1 in next session's plan.)"
            + (f" Session plan had {len(plan_items)} items." if plan_items else "")
        )

    return {
        "knowledge_extracted": summary.count("##"),
        "global_contracts_promoted": global_contracts_promoted,
        "audit_written": True,
        "session_close_cluster_detected": session_close_detected,
        "contract_phrases_detected": detected_contracts,
        "contracts_saved": contracts_saved,
        "add_to_contracts_prompt": len(detected_contracts) > 0 and contracts_saved == 0,
        "session_delta": session_delta,
        "compounding_verdict": session_delta["verdict"],
        **({"skill_gate_warning": skill_gate_warning} if skill_gate_warning else {}),
        **({"learn_gate_warning": learn_gate_warning} if learn_gate_warning else {}),
        **({"session_autopsy_question": autopsy_question} if autopsy_question else {}),
        **({"emerging_global_patterns": emerging_global_patterns,
            "global_pattern_note": (
                f"{len(emerging_global_patterns)} contract(s) found across 2+ projects — "
                "call promote_to_global_contracts() to elevate to global intelligence."
            )} if emerging_global_patterns else {}),
    }
