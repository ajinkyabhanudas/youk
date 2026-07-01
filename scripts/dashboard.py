#!/usr/bin/env python3
"""youk terminal dashboard — reads audit logs and state files, renders trend summary.

Usage:
  python3 scripts/dashboard.py          # terminal output
  python3 scripts/dashboard.py --html   # write ~/.claude/youk/reports/dashboard-YYYY-MM-DD.html
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

CLAUDE_DIR = Path.home() / ".claude"
AUDIT_DIR = CLAUDE_DIR / "audit"
YOUK_DIR = CLAUDE_DIR / "youk"
STATE_DIR = YOUK_DIR / "state"
PROPOSALS_FILE = YOUK_DIR / "knowledge" / "proposals" / "PENDING.md"
REPORTS_DIR = YOUK_DIR / "reports"

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HealthEntry:
    date: str
    org_score: float
    key_finding: str = ""
    skills_invoked: list[str] = field(default_factory=list)


@dataclass
class SessionEntry:
    date: str
    commits: str = "?"
    close_cluster: str = "?"
    tokens_total: int = 0
    tokens_budget: int = 0
    skill_gaps: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)


@dataclass
class DashboardData:
    health_entries: list[HealthEntry] = field(default_factory=list)
    sessions: list[SessionEntry] = field(default_factory=list)
    pending_proposals: list[str] = field(default_factory=list)
    current_session: int = 0
    current_project: str = ""


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_audit_logs(audit_dir: Path) -> tuple[list[HealthEntry], list[SessionEntry]]:
    health_entries: list[HealthEntry] = []
    session_entries: list[SessionEntry] = []

    for audit_file in sorted(audit_dir.glob("*.md")):
        text = audit_file.read_text(encoding="utf-8")
        # Split only on top-level section headers (SKILL-HEALTH REVIEW or Session).
        # Sub-headers inside a session block (### Changes shipped, etc.) must not split.
        blocks = re.split(r"(?=^### (?:SKILL-HEALTH REVIEW|Session))", text, flags=re.MULTILINE)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            if block.startswith("### SKILL-HEALTH REVIEW"):
                entry = _parse_health_block(block)
                if entry:
                    health_entries.append(entry)
            elif block.startswith("### Session"):
                entry = _parse_session_block(block)
                if entry:
                    session_entries.append(entry)

    return health_entries, session_entries


def _parse_health_block(block: str) -> HealthEntry | None:
    m = re.search(r"SKILL-HEALTH REVIEW\s*[—\-]\s*(\d{4}-\d{2}-\d{2})", block)
    if not m:
        return None
    date = m.group(1)

    sm = re.search(r"Org score:\s*([\d.]+)/10", block)
    if not sm:
        return None
    org_score = float(sm.group(1))

    key_finding = ""
    for line in block.splitlines():
        if line.startswith("Key finding:"):
            key_finding = line[len("Key finding:"):].strip()
            break

    skills: list[str] = []
    for line in block.splitlines():
        if "Skills invoked" in line and ":" in line:
            raw = line.split(":", 1)[1].strip()
            skills = [s.strip() for s in raw.split(",") if s.strip()]
            break

    return HealthEntry(date=date, org_score=org_score, key_finding=key_finding, skills_invoked=skills)


def _parse_session_block(block: str) -> SessionEntry | None:
    m = re.search(r"Session\s*[—\-]\s*(\d{4}-\d{2}-\d{2})", block)
    if not m:
        return None
    date = m.group(1)

    commits = "?"
    cm = re.search(r"Commits(?:\s+made)?:\s*(yes|no)", block, re.IGNORECASE)
    if cm:
        commits = "Y" if cm.group(1).lower() == "yes" else "N"

    close = "?"
    ccm = re.search(r"CloseCluster:\s*(yes|no)", block, re.IGNORECASE)
    if ccm:
        close = "Y" if ccm.group(1).lower() == "yes" else "N"

    skills: list[str] = []
    for line in block.splitlines():
        if re.match(r"^Skills:\s*", line):
            raw = line.split(":", 1)[1].strip()
            skills = [s.strip() for s in raw.split(",") if s.strip() and s.strip() != "none"]
            break

    # "Tokens: 15000/75000 (20%)" or "Tokens: 15000 (no budget set)"
    tokens_total = 0
    tokens_budget = 0
    tm = re.search(r"Tokens:\s*(\d+)/(\d+)", block)
    if tm:
        tokens_total = int(tm.group(1))
        tokens_budget = int(tm.group(2))
    else:
        tm2 = re.search(r"Tokens:\s*(\d+)\s+\(no budget", block)
        if tm2:
            tokens_total = int(tm2.group(1))

    gaps: list[str] = []
    for line in block.splitlines():
        if line.startswith("SkillGap:"):
            gaps.append(line[len("SkillGap:"):].strip())

    return SessionEntry(
        date=date,
        commits=commits,
        close_cluster=close,
        tokens_total=tokens_total,
        tokens_budget=tokens_budget,
        skill_gaps=gaps,
        skills=skills,
    )


def parse_proposals(proposals_file: Path) -> list[str]:
    if not proposals_file.exists():
        return []
    text = proposals_file.read_text(encoding="utf-8")
    return re.findall(r"^##\s+(?:Proposal[:\s]+)?(.+)$", text, re.MULTILINE)


def load_state(state_dir: Path) -> tuple[int, str]:
    session_file = state_dir / "session.json"
    if not session_file.exists():
        return 0, ""
    try:
        data = json.loads(session_file.read_text())
        return data.get("session_counter", 0), data.get("last_project", "")
    except Exception:
        return 0, ""


# ── ANSI helpers ──────────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def bold(t: str) -> str: return _c("1", t)
def dim(t: str) -> str: return _c("2", t)
def green(t: str) -> str: return _c("32", t)
def yellow(t: str) -> str: return _c("33", t)
def red(t: str) -> str: return _c("31", t)
def cyan(t: str) -> str: return _c("36", t)


def _strip_ansi(t: str) -> str:
    return re.sub(r"\033\[\d+m", "", t)


def _pad(content: str, width: int, pad_left: int = 2) -> str:
    inner = " " * pad_left + content
    fill = width - 2 - len(_strip_ansi(inner))
    return "│" + inner + " " * max(0, fill) + "│"


# ── Sparkline ─────────────────────────────────────────────────────────────────

_SPARK = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float], lo: float = 0.0, hi: float = 10.0) -> str:
    n = len(_SPARK) - 1
    chars = []
    for v in values:
        idx = round((v - lo) / (hi - lo) * n)
        chars.append(_SPARK[max(0, min(n, idx))])
    return "".join(chars)


# ── Terminal renderer ─────────────────────────────────────────────────────────

def render_terminal(data: DashboardData) -> None:
    width = min(shutil.get_terminal_size((80, 24)).columns, 90)

    def divider(lc: str = "├", rc: str = "┤", char: str = "─", title: str = "") -> str:
        if title:
            inner = f"  {title} "
            fill = width - 2 - len(_strip_ansi(inner))
            return lc + inner + char * max(0, fill) + rc
        return lc + char * (width - 2) + rc

    out: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    out.append("┌" + "─" * (width - 2) + "┐")
    health = data.health_entries[-1] if data.health_entries else None
    score_str = f"  org score: {bold(f'{health.org_score}/10')}" if health else ""
    proj = data.current_project.lstrip("/") if data.current_project else "—"
    out.append(_pad(bold("youk") + dim(" — system dashboard"), width))
    out.append(_pad(dim(f"session #{data.current_session}  project: ") + cyan(proj) + dim(score_str), width))
    out.append(divider())

    # ── Org score trend ─────────────────────────────────────────────────────
    out.append(divider(title="org score trend"))
    if data.health_entries:
        scores = [e.org_score for e in data.health_entries]
        spark = sparkline(scores)
        latest = scores[-1]
        if len(scores) == 1:
            out.append(_pad(f"{latest}/10  {spark}  " + dim("(1 data point — need 2+ for trend)"), width))
        else:
            delta = latest - scores[0]
            sign = "+" if delta >= 0 else ""
            trend = green(f"{sign}{delta:.1f}") if delta >= 0 else red(f"{sign}{delta:.1f}")
            out.append(_pad(f"{latest}/10  {spark}  {trend} over {len(scores)} health checks", width))
        if health and health.key_finding:
            finding = health.key_finding
            max_w = width - 12
            if len(finding) > max_w:
                finding = finding[:max_w - 3] + "..."
            out.append(_pad(dim(f"last: {finding}"), width))
    else:
        out.append(_pad(dim("no health checks yet — run /health to establish a baseline"), width))
    out.append(divider())

    # ── Session history ──────────────────────────────────────────────────────
    out.append(divider(title="session history (last 10)"))
    sessions = sorted(data.sessions, key=lambda s: s.date, reverse=True)[:10]
    if sessions:
        out.append(_pad(dim(f"{'date':<12} {'commits':<9} {'close':<7} {'tokens':<14} gaps"), width))
        out.append(_pad(dim("─" * (width - 8)), width))
        for s in sessions:
            tok = f"{s.tokens_total:>8,}" if s.tokens_total else dim(f"{'—':>8}")
            cmt = green("Y") if s.commits == "Y" else (red("N") if s.commits == "N" else dim("?"))
            cls = green("Y") if s.close_cluster == "Y" else (red("N") if s.close_cluster == "N" else dim("?"))
            gaps_n = str(len(s.skill_gaps)) if s.skill_gaps else dim("0")
            out.append(_pad(f"{s.date:<12} commits:{cmt}   close:{cls}  {tok}    gaps:{gaps_n}", width))
    else:
        out.append(_pad(dim("no sessions recorded yet"), width))
    out.append(divider())

    # ── Skill gap heat map ───────────────────────────────────────────────────
    out.append(divider(title="skill gaps"))
    all_gaps: dict[str, int] = {}
    for s in data.sessions:
        for gap in s.skill_gaps:
            skill = gap.split("—")[0].strip() if "—" in gap else gap.split(":")[0].strip()
            all_gaps[skill] = all_gaps.get(skill, 0) + 1

    if all_gaps:
        max_count = max(all_gaps.values())
        bar_w = 16
        for skill, count in sorted(all_gaps.items(), key=lambda x: x[1], reverse=True)[:8]:
            bar_len = round(count / max_count * bar_w)
            bar = "█" * bar_len + dim("░" * (bar_w - bar_len))
            cnt = red(str(count)) if count >= 3 else (yellow(str(count)) if count >= 2 else str(count))
            out.append(_pad(f"{skill:<22}  {bar}  {cnt}x", width))
    else:
        out.append(_pad(dim("no skill gaps recorded — pass skill_gaps= to session_end() to log them"), width))
    out.append(divider())

    # ── Token efficiency ─────────────────────────────────────────────────────
    out.append(divider(title="token efficiency (last 5 sessions)"))
    with_tokens = [s for s in sorted(data.sessions, key=lambda s: s.date, reverse=True) if s.tokens_total > 0][:5]
    if with_tokens:
        for s in with_tokens:
            if s.tokens_budget > 0:
                pct = s.tokens_total / s.tokens_budget * 100
                pct_str = f"{pct:.0f}% of {s.tokens_budget:,} budget"
                pct_col = red(pct_str) if pct > 80 else (yellow(pct_str) if pct > 60 else green(pct_str))
                out.append(_pad(f"{s.date}  {s.tokens_total:>8,} tokens  {pct_col}", width))
            else:
                out.append(_pad(f"{s.date}  {s.tokens_total:>8,} tokens  " + dim("(no budget set — call track_tokens after route_task)"), width))
    else:
        out.append(_pad(dim("no token data yet — track_tokens() at session checkpoints populates this"), width))
    out.append(divider())

    # ── Pending proposals ────────────────────────────────────────────────────
    out.append(divider(title="pending proposals"))
    if data.pending_proposals:
        for title in data.pending_proposals[:5]:
            out.append(_pad(f"  {yellow('▸')} {title}", width))
        if len(data.pending_proposals) > 5:
            out.append(_pad(dim(f"  ... and {len(data.pending_proposals) - 5} more — run /health"), width))
    else:
        out.append(_pad(dim("0 proposals pending"), width))

    out.append("└" + "─" * (width - 2) + "┘")
    print("\n".join(out))


# ── HTML renderer ─────────────────────────────────────────────────────────────

def render_html(data: DashboardData, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    health = data.health_entries[-1] if data.health_entries else None
    scores = [e.org_score for e in data.health_entries]
    spark = sparkline(scores) if scores else ""
    score_display = f"{health.org_score}/10" if health else "—"

    sessions = sorted(data.sessions, key=lambda s: s.date, reverse=True)[:10]

    def td_yno(v: str) -> str:
        cls = {"Y": "y", "N": "n", "?": "q"}.get(v, "q")
        return f'<td class="{cls}">{v}</td>'

    session_rows = "".join(
        f"<tr><td>{s.date}</td>{td_yno(s.commits)}{td_yno(s.close_cluster)}"
        f"<td class='mono'>{f'{s.tokens_total:,}' if s.tokens_total else '—'}</td>"
        f"<td>{len(s.skill_gaps)}</td></tr>"
        for s in sessions
    ) or "<tr><td colspan='5' class='dim'>no sessions recorded</td></tr>"

    all_gaps: dict[str, int] = {}
    for s in data.sessions:
        for gap in s.skill_gaps:
            skill = gap.split("—")[0].strip() if "—" in gap else gap.split(":")[0].strip()
            all_gaps[skill] = all_gaps.get(skill, 0) + 1

    max_gap = max(all_gaps.values()) if all_gaps else 1
    gap_rows = "".join(
        f"<tr><td>{sk}</td><td><div class='bar' style='width:{round(c/max_gap*100)}%'></div></td><td>{c}</td></tr>"
        for sk, c in sorted(all_gaps.items(), key=lambda x: x[1], reverse=True)[:8]
    ) or "<tr><td colspan='3' class='dim'>no skill gaps recorded</td></tr>"

    proposal_items = "".join(f"<li>{t}</li>" for t in data.pending_proposals) or "<li class='dim'>0 proposals pending</li>"
    finding_html = f"<p class='finding'>{health.key_finding}</p>" if health and health.key_finding else ""
    proj = data.current_project.lstrip("/") or "—"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>youk dashboard</title>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--bd:#30363d;--fg:#e6edf3;--dim:#8b949e;
  --gr:#3fb950;--yl:#d29922;--rd:#f85149;--cy:#58a6ff;}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--fg);font-family:-apple-system,sans-serif;padding:2rem}}
h1{{font-size:1.1rem;color:var(--dim);font-weight:400;margin-bottom:.5rem}}
h1 strong{{color:var(--fg);font-size:1.3rem}}
.meta{{font-size:.75rem;color:var(--dim);margin-bottom:1.5rem}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}
.card{{background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:1.25rem}}
.card h2{{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--dim);margin-bottom:.75rem}}
.score{{font-size:2.5rem;font-weight:700;color:var(--gr)}}
.spark{{font-family:monospace;font-size:1.1rem;color:var(--dim);margin-top:.4rem}}
.finding{{font-size:.8rem;color:var(--dim);margin-top:.6rem;line-height:1.5}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th{{color:var(--dim);font-weight:500;text-align:left;padding:.35rem .5rem;border-bottom:1px solid var(--bd)}}
td{{padding:.35rem .5rem;border-bottom:1px solid var(--bd)}}
td.mono{{font-family:monospace}}
td.y{{color:var(--gr)}}
td.n{{color:var(--rd)}}
td.q{{color:var(--dim)}}
td.dim{{color:var(--dim)}}
.bar{{height:6px;border-radius:3px;background:var(--cy)}}
ul{{list-style:none;padding:0}}
ul li{{padding:.35rem 0;border-bottom:1px solid var(--bd);font-size:.82rem}}
ul li:last-child{{border-bottom:none}}
li.dim{{color:var(--dim)}}
.full{{grid-column:1/-1}}
</style>
</head>
<body>
<h1><strong>youk</strong> — system dashboard</h1>
<p class="meta">session #{data.current_session} &nbsp;·&nbsp; {proj} &nbsp;·&nbsp; {generated}</p>
<div class="grid">
  <div class="card">
    <h2>org score</h2>
    <div class="score">{score_display}</div>
    <div class="spark">{spark or "(no trend data yet)"}</div>
    {finding_html}
  </div>
  <div class="card">
    <h2>pending proposals</h2>
    <ul>{proposal_items}</ul>
  </div>
  <div class="card full">
    <h2>session history (last 10)</h2>
    <table>
      <thead><tr><th>date</th><th>commits</th><th>close-cluster</th><th>tokens</th><th>gaps</th></tr></thead>
      <tbody>{session_rows}</tbody>
    </table>
  </div>
  <div class="card full">
    <h2>skill gaps</h2>
    <table>
      <thead><tr><th>skill</th><th style="width:55%">frequency</th><th>count</th></tr></thead>
      <tbody>{gap_rows}</tbody>
    </table>
  </div>
</div>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"Report written: {output_path}")
    print(f"Open with: open '{output_path}'")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    html_mode = "--html" in sys.argv

    if not AUDIT_DIR.exists():
        print(f"Audit directory not found: {AUDIT_DIR}", file=sys.stderr)
        print("Run a session and call session_end() to start generating audit data.", file=sys.stderr)
        sys.exit(1)

    health_entries, sessions = parse_audit_logs(AUDIT_DIR)
    proposals = parse_proposals(PROPOSALS_FILE)
    session_counter, current_project = load_state(STATE_DIR)

    data = DashboardData(
        health_entries=health_entries,
        sessions=sessions,
        pending_proposals=proposals,
        current_session=session_counter,
        current_project=current_project,
    )

    if html_mode:
        today = datetime.now().strftime("%Y-%m-%d")
        render_html(data, REPORTS_DIR / f"dashboard-{today}.html")
    else:
        render_terminal(data)


if __name__ == "__main__":
    main()
