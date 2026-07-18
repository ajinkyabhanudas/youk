#!/usr/bin/env python3
"""youk stats export — produces a shareable STATS.md from local audit data.

Usage:
  python3 scripts/export_stats.py             # writes STATS.md to youk root
  python3 scripts/export_stats.py --stdout    # print to stdout instead
  python3 scripts/export_stats.py --check     # exit 0 if data is meaningful, 1 if not

youk tracks process discipline (gate compliance, skill invocation), not outcome
quality. A high org_score means the engineering gates fired — it does not mean
every line of code was correct. See STATS.md for the full caveat.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
AUDIT_DIR = CLAUDE_DIR / "audit"
YOUK_DIR = CLAUDE_DIR / "youk"
METRICS_FILE = YOUK_DIR / "state" / "improvement-metrics.json"
OUTPUT_FILE = YOUK_DIR / "STATS.md"

MIN_SESSIONS = 15  # below this, data has too much variance to be meaningful

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

_SPARK = " ▁▂▃▄▅▆▇█"


# ── Data classes ───────────────────────────────────────────────────────────────

class SessionRecord:
    __slots__ = ("date", "has_commits", "has_close_cluster", "skills", "has_capability_skill")

    def __init__(
        self,
        date: str,
        has_commits: bool,
        has_close_cluster: bool,
        skills: list[str],
    ) -> None:
        self.date = date
        self.has_commits = has_commits
        self.has_close_cluster = has_close_cluster
        self.skills = skills
        self.has_capability_skill = any(
            s.lower().replace("-", "_") in _CAPABILITY_SKILLS or s.lower() in _CAPABILITY_SKILLS
            for s in skills
        )


class MetricsSnapshot:
    __slots__ = ("timestamp", "org_score", "close_cluster_rate", "skill_invocation_rate")

    def __init__(self, entry: dict) -> None:
        self.timestamp: str = entry.get("timestamp", "")
        self.org_score: float = entry.get("org_score", 0.0)
        self.close_cluster_rate: float = entry.get("close_cluster_rate", 0.0)
        self.skill_invocation_rate: float | None = entry.get("skill_invocation_rate")


# ── Parsers ────────────────────────────────────────────────────────────────────

def _parse_sessions(audit_dir: Path) -> list[SessionRecord]:
    sessions: list[SessionRecord] = []
    for audit_file in sorted(audit_dir.glob("*.md")):
        text = audit_file.read_text(encoding="utf-8")
        blocks = text.split("### Session —")[1:]
        for block in blocks:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", block)
            if not m:
                continue
            date = m.group(1)

            has_commits = bool(re.search(r"Commits(?:\s+made)?:\s*yes", block, re.IGNORECASE))
            has_close = bool(re.search(r"CloseCluster:\s*yes", block, re.IGNORECASE))

            skills: list[str] = []
            for line in block.splitlines():
                if re.match(r"^Skills:\s*", line):
                    raw = line.split(":", 1)[1].strip()
                    skills = [s.strip() for s in raw.split(",") if s.strip() and s.strip() != "none"]
                    break

            sessions.append(SessionRecord(date, has_commits, has_close, skills))

    return sessions


def _load_metrics(metrics_file: Path) -> list[MetricsSnapshot]:
    if not metrics_file.exists():
        return []
    try:
        data = json.loads(metrics_file.read_text())
        return [MetricsSnapshot(e) for e in data.get("entries", []) if "org_score" in e]
    except Exception:
        return []


# ── Computation ────────────────────────────────────────────────────────────────

def _sparkline(values: list[float], lo: float = 0.0, hi: float = 10.0) -> str:
    n = len(_SPARK) - 1
    return "".join(
        _SPARK[max(0, min(n, round((v - lo) / (hi - lo) * n)))]
        for v in values
    )


def _org_score_trajectory(metrics: list[MetricsSnapshot]) -> list[tuple[str, float]]:
    """Deduplicated daily snapshots — last entry per date."""
    seen: dict[str, float] = {}
    for m in metrics:
        date = m.timestamp[:10] if m.timestamp else ""
        if date:
            seen[date] = m.org_score
    return sorted(seen.items())


def _skill_rate_meaningful(sessions: list[SessionRecord]) -> tuple[int, int, int]:
    """
    Returns (rate_pct, numerator, denominator).
    Denominator = sessions where real work happened (commits=yes OR skills≠none).
    This is a proxy for M+ tasks — task size is not recorded in the audit.
    """
    denominator = [s for s in sessions if s.has_commits or s.skills]
    if not denominator:
        return 0, 0, 0
    numerator = [s for s in denominator if s.has_capability_skill]
    pct = round(len(numerator) / len(denominator) * 100)
    return pct, len(numerator), len(denominator)


def _close_cluster_rate(sessions: list[SessionRecord]) -> tuple[int, int, int]:
    """Returns (rate_pct, closed, total)."""
    total = len(sessions)
    if not total:
        return 0, 0, 0
    closed = sum(1 for s in sessions if s.has_close_cluster)
    return round(closed / total * 100), closed, total


def _gate_trend(metrics: list[MetricsSnapshot]) -> tuple[float | None, float | None]:
    """Returns (first_org_score, latest_org_score) using unique daily snapshots."""
    traj = _org_score_trajectory(metrics)
    if len(traj) < 2:
        return None, None
    return traj[0][1], traj[-1][1]


def _developer_autonomy(audit_dir: Path) -> tuple[int, int]:
    """
    Returns (caught_sessions, tracked_sessions).
    caught = sessions where DeveloperCaught: line appears (dev pre-empted a gate).
    tracked = sessions with any Skills: line (gate could have fired).
    """
    caught = 0
    tracked = 0
    for f in sorted(audit_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        for block in text.split("### Session —")[1:]:
            has_skills_line = any(
                re.match(r"^Skills:\s*", line) for line in block.splitlines()
            )
            if has_skills_line:
                tracked += 1
            if "DeveloperCaught:" in block:
                caught += 1
    return caught, tracked


def _skill_gap_trend(audit_dir: Path) -> list[tuple[str, int]]:
    """Returns [(month, gap_count)] sorted oldest→newest — shows whether gaps are shrinking."""
    by_month: dict[str, int] = {}
    for f in sorted(audit_dir.glob("*.md")):
        month = f.stem  # filename is YYYY-MM.md
        count = f.read_text(encoding="utf-8").count("SkillGap:")
        if count:
            by_month[month] = count
    return sorted(by_month.items())


# ── Renderer ───────────────────────────────────────────────────────────────────

def _render(
    sessions: list[SessionRecord],
    metrics: list[MetricsSnapshot],
    audit_dir: Path | None = None,
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d")
    total_sessions = len(sessions)

    traj = _org_score_trajectory(metrics)
    scores = [v for _, v in traj]
    latest_score = scores[-1] if scores else None
    first_score, last_score = _gate_trend(metrics)

    skill_pct, skill_num, skill_denom = _skill_rate_meaningful(sessions)
    close_pct, close_n, close_total = _close_cluster_rate(sessions)

    spark = _sparkline(scores) if len(scores) >= 2 else "(not enough health checks yet)"

    if latest_score is not None:
        delta = round(last_score - first_score, 1) if (first_score is not None and last_score is not None) else None
        score_line = f"{latest_score}/10"
        if delta is not None and len(traj) >= 2:
            sign = "+" if delta >= 0 else ""
            score_line += f"  ({sign}{delta} over {len(traj)} health checks)"
    else:
        score_line = "no data yet"

    lines: list[str] = []
    lines.append("# youk — session stats")
    lines.append("")
    lines.append(f"*Exported: {now} · {total_sessions} sessions recorded*")
    lines.append("")
    lines.append(
        "> **What this measures:** youk tracks process discipline — whether engineering "
        "gates fired (NFR check, code review, skill invocation) before code was written. "
        "A high org\\_score means the gates ran. It does not measure whether the code "
        "shipped was correct, performant, or secure. Those are separate quality signals."
    )
    lines.append("")

    if total_sessions < MIN_SESSIONS:
        lines.append(
            f"> ⚠ **Early data:** only {total_sessions} sessions recorded. "
            f"Stats become meaningful above {MIN_SESSIONS} sessions — "
            "low session counts produce high-variance numbers."
        )
        lines.append("")

    lines.append("## org score trajectory")
    lines.append("")
    lines.append(f"**{score_line}**")
    lines.append("")
    if len(scores) >= 2:
        lines.append(f"`{spark}`")
        lines.append("")
        lines.append("*Left = oldest health check, right = most recent. Scale: 0–10.*")
    lines.append("")
    lines.append("*Target: 7.0+ sustained over 20+ sessions.*")
    lines.append("")

    lines.append("## skill invocation rate")
    lines.append("")
    if skill_denom:
        lines.append(
            f"**{skill_pct}% ({skill_num}/{skill_denom} real-work sessions)** — "
            "capability skill fired in at least one session with real work (commits or skill activity)."
        )
    else:
        lines.append("**—** no sessions with work recorded yet.")
    lines.append("")
    lines.append(
        "Capability skills: `nfr-check`, `dev-loop`, `code-review`, `stress-test`, "
        "`adr`, `write-spec`, `pm-review`, `security-review`, `verify`, `learn`."
    )
    lines.append("")
    lines.append("*Target: >60%. Below 50% means gates are being skipped on real work.*")
    lines.append("")

    lines.append("## session close rate")
    lines.append("")
    if close_total:
        lines.append(
            f"**{close_pct}% ({close_n}/{close_total} all sessions)** — "
            "sessions closed with `/done` (code-review + verify + learn in sequence)."
        )
    else:
        lines.append("**—** no sessions recorded yet.")
    lines.append("")
    lines.append("*Target: >50%. `/done` is what closes the learning loop.*")
    lines.append("")

    # ── Outcome signals (compounding evidence, not just compliance) ───────────────
    if audit_dir is not None:
        caught, tracked = _developer_autonomy(audit_dir)
        gap_trend = _skill_gap_trend(audit_dir)

        lines.append("## developer autonomy")
        lines.append("")
        lines.append(
            "*Did the developer pre-empt gates before youk asked? "
            "This is the primary signal that compounding is working — "
            "the developer internalised the gate, not just the tool.*"
        )
        lines.append("")
        if tracked:
            pct = round(caught / tracked * 100)
            lines.append(
                f"**{pct}% ({caught}/{tracked} gate-eligible sessions)** — "
                "developer pre-empted a gate before youk asked."
            )
        else:
            lines.append("**—** no gate-eligible sessions recorded yet.")
        lines.append("")
        lines.append("*Target: rising trend over time. 0% is normal in early sessions.*")
        lines.append("")

        lines.append("## skill gap trend")
        lines.append("")
        lines.append(
            "*SkillGap lines written per month — how many times youk detected a missed gate. "
            "A decreasing trend means gaps are being fixed. An increasing trend means new "
            "patterns are being encountered (expected in early sessions).*"
        )
        lines.append("")
        if gap_trend:
            lines.append("| month | gaps logged |")
            lines.append("|-------|-------------|")
            for month, count in gap_trend:
                lines.append(f"| {month} | {count} |")
        else:
            lines.append("*No SkillGap entries yet.*")
        lines.append("")
        lines.append("*Target: stable or decreasing after session 20.*")
        lines.append("")

    lines.append("## trajectory table")
    lines.append("")
    if traj:
        lines.append("| date | org score |")
        lines.append("|------|-----------|")
        for date, score in traj:
            lines.append(f"| {date} | {score}/10 |")
    else:
        lines.append("*No health check data yet — run `/health` to generate.*")
    lines.append("")

    # Reconciliation table — shown when skill rate and close rate use different denominators,
    # making a single "session %" ambiguous. Two denominators → two rows.
    if skill_denom and close_total and skill_denom != close_total:
        lines.append("## denominator reconciliation")
        lines.append("")
        lines.append(
            "> Two metrics use different session pools. "
            "Skill rate counts only sessions with real work; close rate counts all sessions. "
            "A session without commits or skills is counted by close rate but not skill rate."
        )
        lines.append("")
        lines.append("| metric | value | numerator | denominator | denominator definition |")
        lines.append("|--------|-------|-----------|-------------|------------------------|")
        lines.append(
            f"| skill invocation rate | {skill_pct}% | {skill_num} | {skill_denom} | sessions with commits or skill activity |"
        )
        lines.append(
            f"| session close rate | {close_pct}% | {close_n} | {close_total} | all recorded sessions |"
        )
        if audit_dir is not None and tracked:
            lines.append(
                f"| developer autonomy | {round(caught / tracked * 100)}% | {caught} | {tracked} | sessions with a gate-eligible Skills: line |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*These stats are from the author's own sessions. "
        "Run `make export-stats` in your own youk install to generate yours.*"
    )
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    stdout_mode = "--stdout" in sys.argv
    check_mode = "--check" in sys.argv

    if not AUDIT_DIR.exists():
        print(
            f"No audit data found at {AUDIT_DIR}\n"
            "Run at least one session and call session_end() to generate audit entries.",
            file=sys.stderr,
        )
        sys.exit(1)

    sessions = _parse_sessions(AUDIT_DIR)
    metrics = _load_metrics(METRICS_FILE)

    if check_mode:
        if len(sessions) < MIN_SESSIONS:
            print(
                f"Only {len(sessions)} sessions recorded (minimum {MIN_SESSIONS} for meaningful stats).",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"OK — {len(sessions)} sessions, {len(metrics)} health snapshots.")
        sys.exit(0)

    print(f"Sessions read: {len(sessions)}", file=sys.stderr)
    print(f"Health snapshots: {len(metrics)}", file=sys.stderr)

    if len(sessions) < MIN_SESSIONS:
        print(
            f"⚠ Only {len(sessions)} sessions — stats will include a low-data warning. "
            f"Export is most meaningful above {MIN_SESSIONS} sessions.",
            file=sys.stderr,
        )

    content = _render(sessions, metrics, audit_dir=AUDIT_DIR)

    if stdout_mode:
        print(content)
    else:
        OUTPUT_FILE.write_text(content, encoding="utf-8")
        print(f"Written: {OUTPUT_FILE}", file=sys.stderr)
        print(f"Preview: open '{OUTPUT_FILE}'", file=sys.stderr)


if __name__ == "__main__":
    main()
