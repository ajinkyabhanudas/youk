#!/usr/bin/env python3
"""One-way Paperclip -> youk evidence feed (CIR-49 / CIR-48 Proposal B item 7).

When a Paperclip-enforced task closes with a real, independently-reviewed
finding that traces to a youk skill/prompt gap (not a routine bug), this
script queues one proposal into youk's existing pending-proposal store —
via the same `add_proposal` MCP tool a human uses inside an interactive
Claude Code session. It calls that tool out-of-band with `docker run`
against the already-built youk-core:latest image, the same pattern
scripts/health_check.py already uses to run self_heal from cron.

This is a one-way write, not a live bridge: nothing here lets a Paperclip
agent call back into youk mid-task, and nothing changes how Paperclip
agents execute. CIR-48's plan doc rejected that live bridge explicitly —
this script is the smaller thing it approved instead.

Gate: refuses to write without --confirmed-by naming the independent
check that caught the finding (e.g. "shipped-gate", "reviewer:<name>",
a CI check). A finding an agent caught and fixed on its own does not
qualify — this feed is for defects an outside check caught, not routine
self-correction.

Idempotent: if a proposal already tagged for --issue exists, this prints
the existing id and exits 0 without writing a duplicate.

Usage:
  python3 scripts/paperclip_evidence_feed.py \\
    --issue CIR-39 \\
    --skill dev-loop \\
    --confirmed-by shipped-gate \\
    --finding "PR claimed done with no matching commit" \\
    --reason "dev-loop's SKILL.md never states a commit is required before /done" \\
    --proposed-change "Add a checklist line: commit before running /done."

Exit codes: 0 = queued (or already queued), 1 = refused/error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
YOUK_DIR = CLAUDE_DIR / "youk"
DOCKER_IMAGE = "youk-core:latest"


def _mcp_call(tool: str, arguments: dict, timeout: int = 90) -> dict:
    """Call a youk-core MCP tool out-of-band via a throwaway docker container.

    Same wiring as scripts/health_check.py's self_heal call: initialize,
    notifications/initialized, tools/call over stdio, parse the JSON text
    block out of the tool result. No running server touched, no new
    volume or port — reuses the image and mounts youk-core already ships.
    """
    init = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "paperclip-evidence-feed", "version": "0"},
        },
    })
    done = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    call = json.dumps({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    })
    payload = f"{init}\n{done}\n{call}\n"

    try:
        proc = subprocess.run(
            [
                "docker", "run", "-i", "--rm",
                "-v", f"{CLAUDE_DIR}:/claude",
                "-v", f"{YOUK_DIR}:/youk",
                DOCKER_IMAGE,
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise RuntimeError("docker not found — install/start Docker Desktop") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{tool} call timed out ({timeout}s) — is Docker running?") from e

    for raw in proc.stdout.splitlines():
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        content = msg.get("result", {}).get("content", [])
        for block in content:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    return {"_raw_text": block["text"]}

    raise RuntimeError(
        f"no tool result from '{tool}' — is {DOCKER_IMAGE} built? "
        f"(stderr: {proc.stderr[:400]!r})"
    )


def _issue_tag(issue: str) -> str:
    return f"[paperclip:{issue}]"


def _find_existing(issue: str) -> str | None:
    """Return the id of an existing proposal for this Paperclip issue, if any."""
    result = _mcp_call("get_proposals", {"project_slug": ""})
    tag = _issue_tag(issue)
    for p in result.get("proposals", []):
        if tag in (p.get("reason") or "") or tag in (p.get("change") or ""):
            return p.get("id")
    return None


def _build_content(args: argparse.Namespace) -> str:
    """5-part evaluable format — same shape generate_skill_improvement_proposal produces."""
    return (
        f"[PAPERCLIP FINDING — {args.issue} / {args.skill}]\n"
        f"Confirmed by: {args.confirmed_by}\n"
        f"\nWhat happened:\n  {args.finding}\n"
        f"\nProposed change:\n  {args.skill} — {args.proposed_change}\n"
        f"\nAssumption:\n  {args.reason}\n"
        f"\nIf assumption is wrong:\n"
        f"  If this finding was a one-off task variant rather than a recurring gap in "
        f"'{args.skill}', this change over-fits a single incident.\n"
        f"  -> Reject if: no second, independent occurrence shows up before the next review.\n"
        f"\nIf we do nothing:\n"
        f"  The same gap in '{args.skill}' stays reachable — the next session it applies to "
        f"has no outside check the way this Paperclip task did.\n"
        f"\nSource: Paperclip issue {args.issue}, independently confirmed by {args.confirmed_by}. "
        f"Not auto-applied — queued for human review via youk's /improve flow.\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--issue", required=True, help="Paperclip issue identifier, e.g. CIR-39")
    p.add_argument("--skill", required=True, help="youk skill/prompt implicated by the finding")
    p.add_argument("--confirmed-by", required=True,
                   help="Independent check that caught this (e.g. shipped-gate, reviewer:<name>, CI check). "
                        "Required — this feed only fires on independently-reviewed findings.")
    p.add_argument("--finding", required=True, help="One-line description of the defect that was caught")
    p.add_argument("--reason", required=True,
                   help="Why this traces to a youk skill/prompt gap, not a one-off bug")
    p.add_argument("--proposed-change", required=True, help="Concrete change to the skill being proposed")
    p.add_argument("--change-type", default="SKILL_EDIT",
                   choices=["SKILL_EDIT", "REFERENCE_ADD", "CONFIG_EDIT", "FILE_CREATE"])
    p.add_argument("--dry-run", action="store_true", help="Print what would be queued; do not call docker")
    args = p.parse_args()

    if not args.confirmed_by.strip():
        print("ERROR: --confirmed-by is required and cannot be empty — this feed only "
              "fires on independently-reviewed findings, not self-reported ones.", file=sys.stderr)
        return 1

    content = _build_content(args)
    title = f"{_issue_tag(args.issue)} {args.finding}"
    rationale = f"{_issue_tag(args.issue)} {args.reason} (confirmed by: {args.confirmed_by})"

    if args.dry_run:
        print(f"[dry-run] would queue proposal for {args.issue}:")
        print(f"  title: {title}")
        print(f"  target: {args.skill}")
        print(f"  change_type: {args.change_type}")
        print(content)
        return 0

    try:
        existing_id = _find_existing(args.issue)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if existing_id:
        print(f"already queued — {existing_id} exists for {args.issue}, skipping duplicate write")
        return 0

    try:
        result = _mcp_call("add_proposal", {
            "title": title,
            "rationale": rationale,
            "change_type": args.change_type,
            "target": args.skill,
            "content": content,
            "target_section": args.skill,
        })
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    proposal_id = result.get("proposal_id")
    if not proposal_id:
        print(f"ERROR: add_proposal did not return a proposal_id — got {result}", file=sys.stderr)
        return 1

    print(f"queued {proposal_id} for {args.issue} — targets '{args.skill}', "
          f"will surface next time a human runs /improve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
