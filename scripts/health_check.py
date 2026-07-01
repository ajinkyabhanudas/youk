#!/usr/bin/env python3
"""Autonomous health check — calls self_heal via Docker MCP without a Claude Code session.

Reads 30 days of audit logs, generates improvement proposals, prints a summary.
Safe for cron — no side effects beyond writing proposals to PENDING.md.

Usage:
  python3 scripts/health_check.py     # manual run
  make health-check                   # via Makefile
  0 9 * * 1 cd ~/.claude/youk && make health-check >> ~/.claude/audit/cron.log 2>&1
"""
import json
import subprocess
import sys
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
YOUK_DIR = CLAUDE_DIR / "youk"

MCP_INIT = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "health-check", "version": "0"},
    },
})
MCP_DONE = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
MCP_CALL = json.dumps({
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "self_heal", "arguments": {}},
})


def main() -> int:
    payload = f"{MCP_INIT}\n{MCP_DONE}\n{MCP_CALL}\n"

    try:
        proc = subprocess.run(
            [
                "docker", "run", "-i", "--rm",
                "-v", f"{CLAUDE_DIR}:/claude",
                "-v", f"{YOUK_DIR}:/youk",
                "youk-core:latest",
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except FileNotFoundError:
        print("ERROR: docker not found. Install Docker Desktop.", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("ERROR: health check timed out (90s). Is Docker running?", file=sys.stderr)
        return 1

    for raw in proc.stdout.splitlines():
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        content = msg.get("result", {}).get("content", [])
        for block in content:
            if block.get("type") != "text":
                continue
            try:
                report = json.loads(block["text"])
            except (json.JSONDecodeError, TypeError):
                # self_heal returned non-JSON text — print raw and succeed
                print(block["text"][:600])
                return 0

            score = report.get("org_score", "?")
            findings = report.get("findings", [])
            proposals_queued = report.get("promotion_proposals_queued", 0)
            skill_gaps = report.get("skill_gap_signals", [])

            print(f"youk health  org: {score}/10")
            for finding in findings[:3]:
                print(f"  {finding}")
            if skill_gaps:
                print(f"  Skill gaps detected: {len(skill_gaps)}")
            if proposals_queued:
                print(f"  {proposals_queued} proposal(s) queued — review with /health in Claude Code")

            try:
                return 0 if float(score) >= 5.0 else 1
            except (ValueError, TypeError):
                return 0

    # No tool result found in output
    print("ERROR: health check failed — is Docker running and youk-core:latest built?", file=sys.stderr)
    print("  Fix: make build", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
