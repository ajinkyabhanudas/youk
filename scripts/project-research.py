#!/usr/bin/env python3
"""
youk project research — runs weekly per project, writes findings to
knowledge/projects/{slug}/research-inbox/YYYY-MM-DD-research.md

Reads project type from knowledge/projects/{slug}/context.md, calls the
Anthropic API to surface recent best-practice developments for that stack,
and writes structured findings that session_start surfaces at next open.

Usage:
  python3 scripts/project-research.py [--slug SLUG] [--youk-dir PATH]

Scheduled by install.sh via launchd (macOS) or cron (Linux).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# Source-map: project_type → curated context about recent developments
# The model uses its training knowledge, supplemented by these prompts.
_SOURCE_MAP: dict[str, str] = {
    "js_react": (
        "Focus on: React and Next.js ecosystem (React 19, Server Components, App Router patterns), "
        "TypeScript strict mode improvements, Tailwind v4, Vite 6, testing with Vitest and Playwright, "
        "accessibility patterns (WCAG 2.2), performance (Core Web Vitals, bundle analysis), "
        "state management (Zustand, Jotai vs Redux patterns in 2025-2026)."
    ),
    "js_node": (
        "Focus on: Node.js 22+ features (native fetch, native test runner, --watch mode), "
        "ESM migration patterns, Bun as alternative runtime, Hono vs Express vs Fastify, "
        "OpenAPI tooling (Zod + TypeScript), JWT security patterns, rate limiting best practices."
    ),
    "python": (
        "Focus on: Python 3.12-3.13 features (f-string improvements, JIT in 3.13), "
        "uv as package manager replacement for pip/poetry, Ruff for linting and formatting, "
        "FastAPI + Pydantic v2 patterns, async patterns with asyncio, "
        "type annotation best practices, pytest 8+ features."
    ),
    "python_postgresql": (
        "Focus on: SQLAlchemy 2.x async patterns, Alembic migration best practices, "
        "PostgreSQL 16-17 features (logical replication, pg_vector for embeddings), "
        "connection pooling (PgBouncer vs asyncpg pools), query optimization, "
        "psycopg3 async patterns, database testing with pytest-postgresql."
    ),
    "go": (
        "Focus on: Go 1.22-1.23 features (range-over-int, improved toolchain), "
        "slog for structured logging, pgx v5 patterns, wire vs manual DI, "
        "Go fuzzing patterns, goroutine leak detection, Chi vs Gin vs stdlib http/mux, "
        "context propagation best practices, generics usage patterns."
    ),
    "rust": (
        "Focus on: Rust 2024 edition, async Rust with Tokio 1.x, "
        "axum web framework patterns, serde 2.0 improvements, "
        "cargo workspace patterns, error handling with thiserror/anyhow, "
        "clippy lint evolution, unsafe code auditing, WASM targets."
    ),
    "unknown": (
        "Focus on: general software engineering practices applicable across stacks — "
        "12-factor app principles, observability (OpenTelemetry), "
        "CI/CD best practices (GitHub Actions, trunk-based development), "
        "code review patterns, technical debt management, "
        "API design (REST vs GraphQL vs gRPC decision points)."
    ),
}


def _resolve_api_key(youk_dir: Path) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    fallback = youk_dir.parent / ".anthropic" / "api_key"
    if fallback.exists():
        return fallback.read_text().strip()
    return ""


def _load_project_type(youk_dir: Path, slug: str) -> str:
    ctx_file = youk_dir / "knowledge" / "projects" / slug / "context.md"
    if not ctx_file.exists():
        return "unknown"
    for line in ctx_file.read_text().splitlines():
        if line.startswith("project-type:"):
            pt = line.split(":", 1)[1].strip()
            return pt.replace("(bootstrap)", "").strip() or "unknown"
    return "unknown"


def _list_all_slugs(youk_dir: Path) -> list[str]:
    projects_dir = youk_dir / "knowledge" / "projects"
    if not projects_dir.exists():
        return []
    return [
        d.name for d in sorted(projects_dir.iterdir())
        if d.is_dir() and (d / "context.md").exists()
    ]


def run_research(slug: str, youk_dir: Path) -> bool:
    api_key = _resolve_api_key(youk_dir)
    if not api_key:
        print(f"[{slug}] ANTHROPIC_API_KEY not available — skipping", file=sys.stderr)
        return False

    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed — run: pip install anthropic", file=sys.stderr)
        return False

    project_type = _load_project_type(youk_dir, slug)
    context = _SOURCE_MAP.get(project_type, _SOURCE_MAP["unknown"])

    client = anthropic.Anthropic(api_key=api_key)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    prompt = (
        f"You are a senior engineer briefing a developer on what's new and important in their stack.\n\n"
        f"Project stack: {project_type}\n"
        f"Areas to cover: {context}\n\n"
        f"Generate a concise research briefing for week of {today}. Format:\n\n"
        f"## [Pattern or Concept Name]\n"
        f"One paragraph (3-5 sentences) covering what changed, why it matters, and a concrete "
        f"action the developer should consider. Focus on things that are new, changed, or "
        f"commonly misused in 2025-2026. Skip things that are stable and well-known.\n\n"
        f"Generate 3-5 patterns. Be specific — no generic advice. Each pattern should be "
        f"something a developer could act on in their next session."
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.content[0].text.strip()
    except Exception as e:
        print(f"[{slug}] API call failed: {e}", file=sys.stderr)
        return False

    inbox_dir = youk_dir / "knowledge" / "projects" / slug / "research-inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    out_file = inbox_dir / f"{today}-research.md"
    out_file.write_text(
        f"# Project Research — {slug} — {today}\n\n"
        f"Stack: {project_type}\n\n"
        f"---\n\n"
        f"{content}\n"
    )

    print(f"[{slug}] Written: {out_file}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="youk project research — weekly stack briefing")
    parser.add_argument("--slug", help="Project slug (default: all known projects)")
    parser.add_argument("--youk-dir", default=str(Path.home() / ".claude" / "youk"),
                        help="Path to youk directory")
    args = parser.parse_args()

    youk_dir = Path(args.youk_dir)
    slugs = [args.slug] if args.slug else _list_all_slugs(youk_dir)

    if not slugs:
        print("No projects found in knowledge/projects/ — run a session first", file=sys.stderr)
        sys.exit(1)

    success = 0
    for slug in slugs:
        if run_research(slug, youk_dir):
            success += 1

    print(f"\nDone: {success}/{len(slugs)} projects updated")


if __name__ == "__main__":
    main()
