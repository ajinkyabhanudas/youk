#!/usr/bin/env python3
"""What youk puts in front of the model before any work starts, in tokens.

Always-on text costs on every session and, per the AGENTS.md study, raises cost 20%+ for
little gain. It only grows unless something measures it, so this measures it and a test
makes growth fail.

Sources (all repo-controlled, so CI can check them):
  claude_md_template   docs/claude-md-template.md, what the installer puts in CLAUDE.md
  agents_md            AGENTS.md
  skill_descriptions   the `description` of every skills/*/SKILL.md (what the host lists)
Informational, not ratcheted:
  mcp_tool_docstrings  every @mcp.tool docstring (deferred on hosts that defer tool schemas)
  skill_bodies         the SKILL.md bodies, loaded only when a skill fires

Token counts are chars / 4, which is within about 15% for English prose. The number is for
trend and comparison, not billing.

    python3 scripts/footprint.py                 print the table
    python3 scripts/footprint.py --live          also measure ~/.claude/CLAUDE.md
    python3 scripts/footprint.py --check         exit 1 if any ratcheted source grew
    python3 scripts/footprint.py --write-baseline  lower the baseline after a reduction
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "bench" / "footprint-baseline.json"
CHARS_PER_TOKEN = 4

# Sources a change can grow. The total is their sum.
RATCHETED = ("claude_md_template", "agents_md", "skill_descriptions")


def tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        found = re.search(r"^description:\s*(.+)$", match.group(1), re.MULTILINE)
        return {"description": found.group(1)} if found else {}


def skill_descriptions(skills_dir: Path) -> dict[str, int]:
    """Characters of each skill's description, by skill name."""
    sizes: dict[str, int] = {}
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        description = _frontmatter(path.read_text(encoding="utf-8")).get("description", "")
        sizes[path.parent.name] = len(" ".join(str(description).split()))
    return sizes


def skill_body_chars(skills_dir: Path) -> int:
    return sum(len(p.read_text(encoding="utf-8")) for p in skills_dir.glob("*/SKILL.md"))


def mcp_docstring_chars(servers_dir: Path) -> tuple[int, int]:
    """(tool count, docstring characters) over every @mcp.tool function."""
    count = chars = 0
    for server in servers_dir.glob("*/src/server.py"):
        tree = ast.parse(server.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            decorated = any(
                "mcp.tool" in ast.unparse(d) for d in node.decorator_list
            )
            if decorated:
                count += 1
                chars += len(ast.get_docstring(node) or "")
    return count, chars


def _file_chars(path: Path) -> int:
    return len(path.read_text(encoding="utf-8")) if path.exists() else 0


def measure(repo: Path = REPO, live: bool = False) -> dict:
    skills = repo / "skills"
    descriptions = skill_descriptions(skills)
    tool_count, tool_chars = mcp_docstring_chars(repo / "servers")
    sources = {
        "claude_md_template": _file_chars(repo / "docs" / "claude-md-template.md"),
        "agents_md": _file_chars(repo / "AGENTS.md"),
        "skill_descriptions": sum(descriptions.values()),
    }
    result = {
        "method": f"chars/{CHARS_PER_TOKEN}, approx +/-15%",
        "sources": {k: tokens(v) for k, v in sources.items()},
        "informational": {
            "mcp_tool_docstrings": tokens(tool_chars),
            "skill_bodies": tokens(skill_body_chars(skills)),
        },
        "skills": {"count": len(descriptions), "largest_descriptions": dict(
            sorted(((k, tokens(v)) for k, v in descriptions.items()),
                   key=lambda kv: -kv[1])[:5])},
        "mcp_tools": tool_count,
    }
    if live:
        result["informational"]["global_claude_md"] = tokens(
            _file_chars(Path.home() / ".claude" / "CLAUDE.md"))
    result["total_tokens"] = sum(result["sources"][k] for k in RATCHETED)
    return result


def check(current: dict, baseline: dict) -> list[str]:
    """Problems, empty when no ratcheted source grew."""
    problems = []
    for key in RATCHETED:
        now, was = current["sources"].get(key, 0), baseline["sources"].get(key, 0)
        if now > was:
            problems.append(f"{key} grew from {was} to {now} tokens")
    return problems


def _print(report: dict) -> None:
    print(f"Always-on footprint ({report['method']})")
    for key, value in report["sources"].items():
        print(f"  {key:22} {value:>6}")
    print(f"  {'TOTAL (ratcheted)':22} {report['total_tokens']:>6}")
    print("Informational (not always loaded)")
    for key, value in report["informational"].items():
        print(f"  {key:22} {value:>6}")
    print(f"Skills: {report['skills']['count']}, MCP tools: {report['mcp_tools']}")
    print("Largest skill descriptions:",
          ", ".join(f"{k} {v}" for k, v in report["skills"]["largest_descriptions"].items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    report = measure(live=args.live)
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {report['total_tokens']} tokens")
        return 0
    _print(report)
    if args.check:
        problems = check(report, json.loads(BASELINE.read_text(encoding="utf-8")))
        for problem in problems:
            print("FAIL:", problem)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
