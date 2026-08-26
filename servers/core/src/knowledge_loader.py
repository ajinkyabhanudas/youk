"""knowledge_loader — load project context files and L2 knowledge from .claude/ dirs.

Extracted from session.py. Pure file I/O — no subprocess, no API calls.
Imported by session.py; callers need no changes.
"""
from __future__ import annotations

import json
import re

from state_paths import resolve_project_path as _resolve_project_path


def _load_l2_context(project_dir: str) -> tuple[str, str]:
    """Return (resume_point, context_health) from project's .claude/ dir."""
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
    """Scan the project directory for standard context files.

    Reads — but caps aggressively to avoid overloading initial context:
    - CLAUDE.md (root) — full, max 1200 chars (project system instructions)
    - README.md — first description paragraph only (max 400 chars)
    - docs/ — filenames only, no content (surface availability, not dump content)
    - .claude/CLAUDE.md — project-local youk instructions (max 1200 chars)

    Returns a dict with keys: claude_md, readme_snippet, docs_available, context_level, tooling
    """
    p = _resolve_project_path(project_dir)
    result: dict = {
        "claude_md": "",
        "readme_snippet": "",
        "docs_available": [],
        "context_level": "L1",
    }

    for candidate in [p / "CLAUDE.md", p / ".claude" / "CLAUDE.md"]:
        if candidate.exists():
            try:
                text = candidate.read_text()[:1200]
                result["claude_md"] = text
                result["context_level"] = "L5"
            except Exception:
                pass
            break

    readme = p / "README.md"
    if readme.exists():
        try:
            lines = readme.read_text().splitlines()
            snippet_lines = []
            for ln in lines[:80]:
                stripped = ln.strip()
                if not stripped or stripped == "---":
                    if snippet_lines:
                        break
                    continue
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

    docs_dir = p / "docs"
    if docs_dir.exists():
        try:
            spec_keywords = {"spec", "prd", "arch", "design", "requirements", "rfc", "adr"}
            result["docs_available"] = [
                f.name for f in sorted(docs_dir.iterdir())
                if f.suffix in {".md", ".txt", ".rst"}
                and any(kw in f.name.lower() for kw in spec_keywords)
            ][:8]
        except Exception:
            pass

    tooling: dict = {
        "make_targets": [],
        "npm_scripts": [],
        "ci_providers": [],
        "pre_commit": False,
        "test_configs": [],
        "containers": [],
        "ai_context": [],
    }

    makefile = p / "Makefile"
    if makefile.exists():
        try:
            lines = makefile.read_text().splitlines()
            for line in lines:
                m = re.match(r"^([a-zA-Z_-]+):.*?##\s*(.+)", line)
                if m:
                    tooling["make_targets"].append(f"make {m.group(1)}: {m.group(2).strip()[:60]}")
                    continue
                m2 = re.match(r"^(test|build|run|dev|deploy|lint|install|clean|start|check)\s*:", line)
                if m2 and f"make {m2.group(1)}" not in " ".join(tooling["make_targets"]):
                    tooling["make_targets"].append(f"make {m2.group(1)}")
            tooling["make_targets"] = tooling["make_targets"][:12]
        except Exception:
            pass

    pkg_json = p / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})
            tooling["npm_scripts"] = [f"npm run {k}" for k in list(scripts)[:10]]
        except Exception:
            pass

    for ci_path, ci_name in [
        (".github/workflows", "github-actions"),
        (".circleci", "circleci"),
        (".gitlab-ci.yml", "gitlab-ci"),
        ("Jenkinsfile", "jenkins"),
        (".buildkite", "buildkite"),
    ]:
        if (p / ci_path).exists():
            tooling["ci_providers"].append(ci_name)

    if (p / ".pre-commit-config.yaml").exists():
        tooling["pre_commit"] = True

    for test_file in [
        "pytest.ini", "pyproject.toml", "setup.cfg",
        "jest.config.js", "jest.config.ts", "vitest.config.ts",
        ".rspec", "karma.conf.js",
    ]:
        if (p / test_file).exists():
            tooling["test_configs"].append(test_file)

    for container_file in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"]:
        if (p / container_file).exists():
            tooling["containers"].append(container_file)

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
