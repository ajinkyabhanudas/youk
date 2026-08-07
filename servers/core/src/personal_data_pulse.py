"""Personal-data pulse — does any committed file leak a specific person's identifier?

The blind spot this closes: youk's per-developer isolation depends on personal data staying
local (gitignored). But a developer's name, colleagues' names, or emails can drift into
COMMITTED skill files, docstrings, and examples, and then every install ships them. This
happened: a release-readiness check found ~39 personal-name references across 13 committed
files. Nothing caught it automatically; it was found by hand at the release gate.

Design (after a challenge pass that rejected the first draft):
- ZERO CONFIG. The names to guard are auto-seeded from what git already knows — the commit
  author (git config user.name), the plugin.json author, the SKILL-REGISTRY owner line. The
  developer most at risk (unaware their name is leaking) never has to configure anything. An
  optional config/personal-names.txt (gitignored) can add colleague names git can't infer.
- Catches KNOWN IDENTIFIERS: the auto-seeded names plus any email address. It does NOT claim
  to catch all PII (an unlisted colleague, an org name) — that boundary is stated honestly, not
  oversold. It is a floor, not a guarantee.
- Prevention over detection: the primary use is a PRE-COMMIT gate that BLOCKS a leak from
  entering history (see scan_for_precommit). The session_start vital is the backstop for
  anything already committed.

What it never scans: gitignored local files (knowledge/global, knowledge/imported, state) —
personal by design. Only what would ship to another install.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

YOUK_ROOT = Path("/youk")

_SHIPPED_GLOBS = (
    "skills/**/*.md", "docs/**/*.md", "servers/**/*.py",
    "plugin/**/*.py", "plugin/**/*.json", "*.md",
)
_SKIP_DIRS = ("knowledge", "state", ".git", "tests", "__pycache__", "node_modules")

# Lines where an identifier is legitimate attribution, not a leak.
_ATTRIBUTION_ALLOW = ('"author":', "Owner:", "Co-Authored-By:", "author =", "authors =")

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _seed_names(youk_root: Path) -> list[str]:
    """Auto-seed the guard list from what git/config already knows — zero config required."""
    names: set[str] = set()

    # git commit author — the person most at risk of leaking their own name.
    try:
        out = subprocess.run(
            ["git", "config", "user.name"], cwd=str(youk_root),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            names.add(out.stdout.strip())
    except Exception:
        pass

    # plugin author + registry owner (already committed, so we read the value to guard against
    # it appearing ELSEWHERE — the allow-list keeps the attribution lines themselves clean).
    for rel in ("plugin/.claude-plugin/plugin.json", "skills/SKILL-REGISTRY.md"):
        f = youk_root / rel
        if f.exists():
            try:
                text = f.read_text()
                m = re.search(r'"author":\s*"([^"]+)"', text) or re.search(r"Owner:\s*([^.\n]+)", text)
                if m:
                    names.add(m.group(1).strip())
            except Exception:
                pass

    # Optional extra names git can't infer (colleagues). Gitignored, absent on fresh install.
    extra = youk_root / "config" / "personal-names.txt"
    if extra.exists():
        try:
            names.update(
                ln.strip() for ln in extra.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")
            )
        except Exception:
            pass

    return sorted(names)


def _shipped_files(youk_root: Path) -> list[Path]:
    seen: set[Path] = set()
    for pat in _SHIPPED_GLOBS:
        for p in youk_root.glob(pat):
            if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts):
                seen.add(p)
    return sorted(seen)


def check_personal_data(youk_root: Path = YOUK_ROOT, files: list[Path] | None = None) -> dict:
    """Scan shipped files for auto-seeded names or emails, outside the attribution allow-list.

    files: restrict the scan (used by the pre-commit gate to scan only staged files).
    Returns {"names_checked": [names], "leaks": [{file, line_no, kind, hit, text}], "clean": bool}.
    Boundary (stated, not oversold): catches the auto-seeded names + any email. Does NOT catch
    every PII class (unlisted colleagues, org names). Clean here means "no known identifier
    ships," not "no personal data ships."
    """
    names = _seed_names(youk_root)
    name_pats = [(n, re.compile(rf"\b{re.escape(n)}\b")) for n in names]
    targets = files if files is not None else _shipped_files(youk_root)

    leaks: list[dict] = []
    for path in targets:
        if not path.exists() or any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            lines = path.read_text(errors="ignore").splitlines()
        except Exception:
            continue
        rel = str(path.relative_to(youk_root)) if path.is_absolute() else str(path)
        for i, line in enumerate(lines, 1):
            if any(a in line for a in _ATTRIBUTION_ALLOW):
                continue
            for name, pat in name_pats:
                if pat.search(line):
                    leaks.append({"file": rel, "line_no": i, "kind": "name",
                                  "hit": name, "text": line.strip()[:100]})
            m = _EMAIL.search(line)
            if m and "noreply@anthropic.com" not in line:  # commit-trailer email is fine
                leaks.append({"file": rel, "line_no": i, "kind": "email",
                              "hit": m.group(0), "text": line.strip()[:100]})

    return {"names_checked": names, "leaks": leaks, "clean": not leaks}


def scan_for_precommit(youk_root: Path = YOUK_ROOT) -> dict:
    """Pre-commit gate: scan STAGED shipped files only. This is the prevention half — it blocks
    the leak from entering history, not just reports it after. Returns the same shape as
    check_personal_data with an added "blocked" bool the hook acts on."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(youk_root), capture_output=True, text=True, timeout=10,
        )
        staged = [youk_root / f for f in out.stdout.splitlines() if f.strip()]
    except Exception:
        staged = []
    # only shipped files matter
    shipped = set(_shipped_files(youk_root))
    to_scan = [p for p in staged if p in shipped]
    result = check_personal_data(youk_root, files=to_scan)
    result["blocked"] = not result["clean"]
    return result


def format_leak_warnings(result: dict, cap: int = 5) -> list[str]:
    """Session-start lines for personal-data leaks in committed files (the backstop)."""
    if result.get("clean"):
        return []
    leaks = result["leaks"]
    files = sorted({leak["file"] for leak in leaks})
    lines = [
        f"⚠ PERSONAL DATA: {len(leaks)} known-identifier leak(s) in {len(files)} COMMITTED "
        f"file(s) — these ship to every install:"
    ]
    for leak in leaks[:cap]:
        lines.append(f"    · {leak['file']}:{leak['line_no']} — {leak['kind']} '{leak['hit']}'")
    if len(leaks) > cap:
        lines.append(f"    · …and {len(leaks) - cap} more. Genericize before release.")
    return lines
