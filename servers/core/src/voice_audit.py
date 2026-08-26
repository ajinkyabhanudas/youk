"""Voice audit — scan recent commit messages for AI-tells at session_end.

Called from end_session(). Reads the last N commit messages via git log,
runs check_text on each, and writes findings to state/voice-audit.json.

The json is read by session_start to surface "last session voice misses"
so they appear in the session plan before any new work starts.

Silent-fail throughout — git unavailable or check failures never block session_end.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


_COMMIT_LOOKBACK = 10


def audit_recent_commits(youk_root: Path, n: int = _COMMIT_LOOKBACK) -> dict[str, Any]:
    """Run voice check on the last N commit messages. Write findings to state/voice-audit.json."""
    try:
        from voice_fingerprint import check_text
    except ImportError:
        return {"skipped": True, "reason": "import_error"}

    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={n}", "--format=%H\x1f%s\x1f%b\x1f---END---"],
            capture_output=True, text=True, timeout=10,
            cwd=youk_root,
        )
        if result.returncode != 0:
            return {"skipped": True, "reason": "git_error"}
        raw = result.stdout
    except Exception as e:
        return {"skipped": True, "reason": str(e)}

    commits = []
    for block in raw.split("---END---"):
        block = block.strip()
        if not block:
            continue
        parts = block.split("\x1f", 3)
        if len(parts) < 2:
            continue
        sha, subject = parts[0].strip(), parts[1].strip()
        body = parts[2].strip() if len(parts) > 2 else ""
        full_text = f"{subject}\n\n{body}".strip() if body else subject
        if not full_text:
            continue

        try:
            r = check_text(full_text)
        except Exception:
            continue

        hard = r.get("tells_hard", [])
        # Commit bodies are structurally colon-dense (change lists, file annotations,
        # section headers). colon_scaffolding is calibrated for prose — exclude it here
        # to avoid false positives on legitimate structured commit descriptions.
        soft = [t for t in r.get("tells_soft", []) if not t.startswith("colon_scaffolding")]
        gate = r.get("gate", "UNKNOWN")

        if hard or soft:
            commits.append({
                "sha": sha[:8],
                "subject": subject[:80],
                "gate": gate,
                "tells_hard": hard,
                "tells_soft": soft,
            })

    findings = {
        "ts": datetime.utcnow().isoformat(),
        "commits_checked": n,
        "commits_with_tells": len(commits),
        "findings": commits,
    }

    try:
        out = youk_root / "state" / "voice-audit.json"
        out.write_text(json.dumps(findings, indent=2))
    except Exception:
        pass

    return findings


def load_voice_audit(youk_root: Path) -> dict[str, Any]:
    """Load the most recent voice audit result from state/voice-audit.json."""
    try:
        f = youk_root / "state" / "voice-audit.json"
        if f.exists():
            return json.loads(f.read_text())
    except Exception:
        pass
    return {}


def format_voice_audit_warning(audit: dict[str, Any]) -> str:
    """Format audit findings as a session_start warning block, or empty string if clean."""
    findings = audit.get("findings", [])
    if not findings:
        return ""

    lines = [f"[VOICE AUDIT] Last session: {len(findings)} commit(s) with AI-tells."]
    for f in findings[:5]:
        hard = ", ".join(f["tells_hard"])
        soft = ", ".join(f["tells_soft"])
        tells = " | ".join(filter(None, [hard, soft]))
        lines.append(f"  {f['sha']} {f['subject'][:50]}: {tells}")

    em_dash_count = sum(
        1 for f in findings
        if any("em_dash" in t for t in f.get("tells_hard", []))
    )
    if em_dash_count:
        lines.append(f"  Most common: em_dash in title ({em_dash_count}x) — use colon or drop separator")

    return "\n".join(lines)
