"""
Cross-session failure pattern detector.

Scans the monthly audit .md files in ~/.claude/audit/ for recurring
FindingCategories entries. When a domain appears in >= threshold sessions
within the lookback window, returns an alert so start_session can surface
it proactively — before the developer starts a 4th attempt in a domain
that has had HIGH findings 3 sessions in a row.

Zero API calls. Pure regex. Fail-silent throughout.
"""
from __future__ import annotations
import re
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from schemas import FailurePatternAlert

_SESSION_BOUNDARY = re.compile(r"^### Session", re.MULTILINE)
_PROJECT_LINE = re.compile(r"^Project:\s*(.+)$", re.MULTILINE)
_CATEGORIES_LINE = re.compile(r"^FindingCategories:\s*(.+)$", re.MULTILINE)

_DEFAULT_AUDIT_DIR = Path("/claude") / "audit"


def _read_audit_files(audit_dir: Path) -> list[str]:
    """Return file contents of all YYYY-MM.md audit files, newest first."""
    if not audit_dir.exists():
        return []
    files = sorted(
        (f for f in audit_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].md")),
        reverse=True,
    )
    contents = []
    for f in files:
        try:
            contents.append(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
    return contents


def _split_into_sessions(content: str) -> list[str]:
    """Split a monthly audit file into per-session blocks."""
    parts = _SESSION_BOUNDARY.split(content)
    # First part is preamble before any session header — skip it.
    return [p for p in parts[1:] if p.strip()]


def _extract_project(block: str) -> str:
    m = _PROJECT_LINE.search(block)
    return m.group(1).strip() if m else ""


def _extract_categories(block: str) -> list[str]:
    m = _CATEGORIES_LINE.search(block)
    if not m:
        return []
    raw = m.group(1)
    return [c.strip() for c in raw.split(",") if c.strip()]


def scan_failure_patterns(
    audit_dir: Path | None = None,
    slug: str = "",
    lookback_sessions: int = 5,
    threshold: int = 3,
) -> list[FailurePatternAlert]:
    """
    Scan audit .md files for recurring FindingCategories entries.

    audit_dir: directory containing YYYY-MM.md files. Defaults to ~/.claude/audit/.
    slug: if non-empty, only count sessions where Project: matches this slug.
    lookback_sessions: how many recent sessions to consider (per-project if slug given).
    threshold: minimum session count to trigger an alert.

    Returns list of FailurePatternAlert, one per domain that meets the threshold.
    Returns [] on any error or when no patterns are found.
    """
    target_dir = audit_dir or _DEFAULT_AUDIT_DIR
    try:
        contents = _read_audit_files(target_dir)
    except Exception:
        return []

    if not contents:
        return []

    # Collect sessions across all files, newest first.
    all_sessions: list[str] = []
    for content in contents:
        all_sessions.extend(_split_into_sessions(content))

    # Filter by slug if provided, then cap at lookback_sessions.
    if slug:
        matching = [s for s in all_sessions if _extract_project(s) == slug]
    else:
        matching = all_sessions

    window = matching[:lookback_sessions]
    sessions_scanned = len(window)

    if sessions_scanned == 0:
        return []

    domain_count: dict[str, int] = {}
    for block in window:
        cats = _extract_categories(block)
        seen_this_session: set[str] = set()
        for cat in cats:
            if cat not in seen_this_session:
                domain_count[cat] = domain_count.get(cat, 0) + 1
                seen_this_session.add(cat)

    alerts: list[FailurePatternAlert] = []
    for domain, count in sorted(domain_count.items(), key=lambda x: -x[1]):
        if count >= threshold:
            alerts.append(FailurePatternAlert(
                domain=domain,
                count=count,
                sessions_scanned=sessions_scanned,
                message=(
                    f"{domain} has had recurring findings in {count} of the last "
                    f"{sessions_scanned} session(s). Address before starting again."
                ),
            ))

    return alerts
