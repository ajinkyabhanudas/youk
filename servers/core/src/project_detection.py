"""project_detection — detect project type, purpose, and stack from the filesystem.

Extracted from session.py. All functions are pure file I/O — zero tokens, zero API calls.
Imported by session.py; re-exported so existing callers (health.py) need no changes.
"""
from __future__ import annotations

import json
from pathlib import Path

from state_paths import resolve_project_path as _resolve_project_path


# Maps project purpose -> list of skills expected for that project type.
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


def _detect_project_purpose(project_dir: str) -> str:
    """Detect the purpose/domain of the project beyond just its stack/language.

    Returns a key from PROJECT_PURPOSE_EXPECTED_SKILLS or 'general'.
    Used to surface skill coverage gaps for the specific project type.
    """
    p = _resolve_project_path(project_dir)
    if not p.exists():
        return "general"

    skills_dir = p / "skills"
    if skills_dir.is_dir() and any(skills_dir.glob("*/SKILL.md")):
        return "ai_engineering_system"

    for server_file in sorted(p.glob("**/server.py"))[:10]:
        try:
            content = server_file.read_text()
            if "fastmcp" in content or "from mcp" in content or "mcp.server" in content:
                return "mcp_server"
        except Exception:
            pass

    dockerfiles = [f for f in p.glob("*/Dockerfile")] + [f for f in p.glob("*/*/Dockerfile")]
    if len(set(str(f) for f in dockerfiles)) > 1:
        return "docker_multi_service"

    if (p / "scripts" / "install.sh").exists() or (p / "install.sh").exists():
        return "installable_cli"

    return "general"


def _detect_stack_context(project_dir: str) -> dict:
    """Detect stack, framework, and domain from project files.

    Pure file I/O — zero tokens, zero API calls.
    Returns: {stack, framework, domain} — any field may be None if undetected.
    """
    p = _resolve_project_path(project_dir)
    if not p.exists():
        return {"stack": None, "framework": None, "domain": None}

    stack: str | None = None
    framework: str | None = None
    domain: str | None = None

    if (p / "go.mod").exists():
        stack = "go"
    elif (p / "Cargo.toml").exists():
        stack = "rust"
    else:
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

            if "django" in all_deps:
                framework = "django"
            elif "fastapi" in all_deps:
                framework = "fastapi"
            elif "flask" in all_deps:
                framework = "flask"
            elif "tornado" in all_deps:
                framework = "tornado"

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
