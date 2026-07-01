from __future__ import annotations
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import SessionState
from compaction import write_contracts
from tokens import read_and_clear as _read_and_clear_tokens

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
    p = Path(project_dir)
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

    # API fallback: if README exists but crude extraction yielded nothing useful,
    # use a one-shot Claude call to extract a project description sentence.
    # Uses the user's API credits intentionally — better than returning nothing.
    if readme.exists() and not result["readme_snippet"]:
        try:
            import os
            import anthropic as _anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                key_file = Path("/claude/.anthropic/api_key")
                if key_file.exists():
                    api_key = key_file.read_text().strip()
            if api_key:
                _c = _anthropic.Anthropic(api_key=api_key)
                readme_head = readme.read_text()[:2000]
                msg = _c.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=80,
                    messages=[{
                        "role": "user",
                        "content": (
                            f"In one sentence (max 120 chars), what does this project do?\n\n{readme_head}"
                        ),
                    }],
                )
                snippet = msg.content[0].text.strip()
                if snippet:
                    result["readme_snippet"] = snippet[:200]
                    if result["context_level"] == "L1":
                        result["context_level"] = "L4"
        except Exception:
            pass

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
    doc_gaps: list[str] | None = None,
    docs_available: list[str] | None = None,
    has_project_claude_md: bool = False,
    tooling: dict | None = None,
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
    Read docs/doc-map.yaml. Extract public MCP tool names from both server.py files.
    Return list of undocumented tools — in server.py but absent from the doc-map.
    Called at session_start so gaps surface in session_plan before any work begins.
    """
    doc_map_file = YOUK_ROOT / "docs" / "doc-map.yaml"
    if not doc_map_file.exists():
        return []
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

        undocumented = []
        for server_file in [
            YOUK_ROOT / "servers" / "core" / "src" / "server.py",
            YOUK_ROOT / "servers" / "code" / "src" / "server.py",
        ]:
            if not server_file.exists():
                continue
            source = server_file.read_text()
            # collect names of @mcp.tool()-decorated functions
            decorated = set(re.findall(
                r'@mcp\.tool\(\)\s+def (\w+)\s*\(', source, re.DOTALL
            ))
            for name in sorted(decorated - mapped_tools):
                undocumented.append(
                    f"tool '{name}' missing from docs/doc-map.yaml — "
                    "add it (and update README.md + docs/claude-md-template.md if needed)"
                )
        return undocumented
    except Exception:
        return []


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

    # Priority-ordered resume point: L3 > L2 > external context.md > README snippet > git log
    if l2_resume:
        resume_point = l2_resume
    elif project_scan["readme_snippet"]:
        resume_point = f"Project: {project_scan['readme_snippet'][:120]}"
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

    doc_gaps = _check_doc_freshness()

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
    )


def end_session(
    summary: str,
    commits_made: bool,
    explicit_contracts: list[str] | None = None,
    skills_used: list[str] | None = None,
    close_cluster: bool = False,
    skill_gaps: dict[str, list[str]] | None = None,
) -> dict:
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
    skills_line = ", ".join(skills_used) if skills_used else "none"
    close_line = "yes" if close_cluster else "no"
    gap_lines = ""
    if skill_gaps:
        for skill_name, gaps in skill_gaps.items():
            for gap in gaps:
                gap_lines += f"SkillGap: {skill_name} — {gap}\n"

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
        f"{summary}\n"
        f"Skills: {skills_line}\n"
        f"CloseCluster: {close_line}\n"
        f"Commits: {'yes' if commits_made else 'no'}\n"
        f"{tokens_line}"
        f"{gap_lines}"
    )

    with open(audit_file, "a") as f:
        f.write(entry)

    # Write contracts to disk so they survive future sessions and compact_context can pin them
    current_state = _load_state()
    slug = _slug(current_state.get("last_project", ""))
    contracts_to_save = explicit_contracts or detected_contracts
    contracts_saved = write_contracts(slug, contracts_to_save) if slug and contracts_to_save else 0

    # Write the resume point for the next session into external context.md (zero footprint).
    # Extract: first non-empty line after a ## heading, or first non-empty line of summary.
    if slug:
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
            _update_resume_point(slug, resume_text)

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
