"""
Task Intake Contract — CAP-9

Converts a developer's request into a filled, editable contract before heavy work.
Surfacing: (a) what youk understood, (b) provocations from adversarial frames,
(c) what this pass will NOT include.

Fill, don't interrogate: present a complete interpretation for editing, never a questionnaire.
"""
from __future__ import annotations
import json
import re
import yaml
from datetime import datetime, UTC
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import TaskSize

YOUK_ROOT = Path("/youk")
_CONTRACTS_DIR = YOUK_ROOT / "state" / "task-contracts"
_RISK_LEDGER = YOUK_ROOT / "state" / "risk-ledger.jsonl"
_FRAMES_FILE = YOUK_ROOT / "skills" / "adversarial-planning" / "references" / "frames.md"
_ROUTES_FILE = YOUK_ROOT / "config" / "routes.yaml"
_AUDIT_DIR = Path("/claude") / "audit"

_FRAME_QUESTIONS: dict[str, str] = {
    "F1": "If this works perfectly, does the user actually feel the benefit?",
    "F2": "Is there a simpler or more robust technical approach being overlooked?",
    "F3": "What evidence would confirm this is the right solution — and does it exist?",
    "F4": "Could success on the stated metric miss the real goal?",
    "F5": "What are we trusting here that could break silently?",
    "F6": "Is the ceremony proportionate to the value — or does it add friction that compounds?",
    "F7": "What breaks at 10× the expected scale or when a dependency fails?",
}

_FRAME_LABELS: dict[str, str] = {
    "F1": "USER-VALUE",
    "F2": "ENGINEERING-RIGOR",
    "F3": "EVIDENCE",
    "F4": "GOODHART",
    "F5": "TRUST",
    "F6": "ADOPTION-ECONOMICS",
    "F7": "SCALE/FAILURE",
}


def _load_routes() -> dict:
    if not _ROUTES_FILE.exists():
        return {}
    with open(_ROUTES_FILE) as f:
        return yaml.safe_load(f) or {}


def _score_size(task: str) -> TaskSize:
    """Reuse routing.py's net-score logic without importing it directly (avoids circular deps)."""
    routes = _load_routes()
    task_lower = task.lower()
    sizes = routes.get("task_sizes", {})
    size_order = {"XL": 5, "L": 4, "M": 3, "S": 2, "XS": 1}

    scored: list[tuple[int, TaskSize]] = []
    for size_name, config in sizes.items():
        positive = sum(1 for s in config.get("signals", []) if s.lower() in task_lower)
        negative = sum(1 for s in config.get("negative_signals", []) if s.lower() in task_lower)
        net = positive - (negative * 2)
        if net > 0:
            scored.append((net, TaskSize(size_name)))

    if not scored:
        xs_signals = sizes.get("XS", {}).get("signals", [])
        if any(s.lower() in task_lower for s in xs_signals):
            return TaskSize.XS
        word_count = len(task.split())
        if word_count <= 5:
            return TaskSize.XS
        elif word_count <= 15:
            return TaskSize.S
        elif word_count <= 40:
            return TaskSize.M
        return TaskSize.L

    scored.sort(key=lambda x: (x[0], size_order.get(x[1].value, 0)), reverse=True)
    return scored[0][1]


def _read_frames_from_file() -> dict[str, str]:
    """
    Read frame trigger questions from the adversarial-planning references file.
    Returns {frame_id: question} — falls back to _FRAME_QUESTIONS if file unreadable.
    No forking: this is the single source of truth for frames.
    """
    if not _FRAMES_FILE.exists():
        return _FRAME_QUESTIONS
    try:
        text = _FRAMES_FILE.read_text()
        result: dict[str, str] = {}
        current_frame: str | None = None
        for line in text.splitlines():
            m = re.match(r"^## (F\d+) —", line)
            if m:
                current_frame = m.group(1)
            elif current_frame and line.strip().startswith("- ") and current_frame not in result:
                # First bullet under each frame is the primary trigger question
                result[current_frame] = line.strip().lstrip("- ")
        # Merge with fallback for any missing frames
        for fid, q in _FRAME_QUESTIONS.items():
            result.setdefault(fid, q)
        return result
    except Exception:
        return _FRAME_QUESTIONS


def _load_recent_risk_ledger(days: int = 90) -> list[dict]:
    """Load recent ACCEPT-RISK entries from the risk ledger."""
    if not _RISK_LEDGER.exists():
        return []
    entries = []
    cutoff = datetime.now(UTC).timestamp() - (days * 86400)
    try:
        for line in _RISK_LEDGER.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            # Parse date field
            date_str = entry.get("date", "")
            try:
                ts = datetime.fromisoformat(date_str.replace("Z", "+00:00")).timestamp()
                if ts >= cutoff:
                    entries.append(entry)
            except Exception:
                entries.append(entry)  # include if date unparsable
    except Exception:
        pass
    return entries


def _load_recent_gaps(months: int = 3) -> list[str]:
    """Return recent SkillGap themes from audit logs."""
    gaps: list[str] = []
    if not _AUDIT_DIR.exists():
        return gaps
    from datetime import date
    today = date.today()
    months_to_check = []
    for i in range(months):
        if today.month - i > 0:
            months_to_check.append(f"{today.year}-{today.month - i:02d}")
        else:
            months_to_check.append(f"{today.year - 1}-{(today.month - i) % 12 or 12:02d}")
    for month in months_to_check:
        f = _AUDIT_DIR / f"{month}.md"
        if f.exists():
            try:
                for line in f.read_text().splitlines():
                    if line.startswith("SkillGap:"):
                        rest = line[len("SkillGap:"):].strip()
                        if " — " in rest:
                            gaps.append(rest.split(" — ", 1)[1].strip())
            except Exception:
                pass
    return gaps


def _load_failed_outcomes(months: int = 3) -> list[str]:
    """Return cause descriptions from FAILED audit outcomes."""
    causes: list[str] = []
    if not _AUDIT_DIR.exists():
        return causes
    from datetime import date
    today = date.today()
    months_to_check = []
    for i in range(months):
        if today.month - i > 0:
            months_to_check.append(f"{today.year}-{today.month - i:02d}")
        else:
            months_to_check.append(f"{today.year - 1}-{(today.month - i) % 12 or 12:02d}")
    for month in months_to_check:
        f = _AUDIT_DIR / f"{month}.md"
        if f.exists():
            try:
                blocks = re.split(r"(?=### Session —)", f.read_text())
                for block in blocks:
                    if "OutcomeResult: FAILED" in block or "Outcome: FAILED" in block:
                        # Extract any SkillGap or cause lines
                        for line in block.splitlines():
                            if line.startswith("SkillGap:") and " — " in line:
                                causes.append(line.split(" — ", 1)[1].strip())
            except Exception:
                pass
    return causes


def _generate_provocations(
    task: str,
    size: TaskSize,
    risk_entries: list[dict],
    gap_themes: list[str],
    failed_causes: list[str],
) -> list[dict]:
    """
    Generate adversarial provocations using frame rotation.
    Returns list of {frame, label, risk, severity, personalized, citation} sorted by severity.
    Frames read from references/frames.md — no forked frame list.
    """
    _read_frames_from_file()  # validates frames file is readable; side-effect only
    task_lower = task.lower()

    # Heuristics for frame applicability and severity
    provocations: list[dict] = []

    frame_checks = [
        ("F1", _check_f1(task_lower), "HIGH"),
        ("F2", _check_f2(task_lower), "HIGH"),
        ("F3", _check_f3(task_lower), "MEDIUM"),
        ("F4", _check_f4(task_lower), "HIGH"),
        ("F5", _check_f5(task_lower), "MEDIUM"),
        ("F6", _check_f6(task_lower, size), "MEDIUM"),
        ("F7", _check_f7(task_lower), "LOW"),
    ]

    for frame_id, (applicable, risk_text) in [(f, r) for f, r, _ in frame_checks]:
        if not applicable:
            continue
        severity = next(s for f, _, s in frame_checks if f == frame_id)

        # Check personalization: does any prior ACCEPT-RISK or gap theme match?
        personalized = False
        citation = ""
        task_words = set(task_lower.split())
        for entry in risk_entries:
            risk_str = (entry.get("risk", "") + " " + entry.get("frame", "")).lower()
            if frame_id in risk_str or len(set(risk_str.split()) & task_words) >= 2:
                count = sum(
                    1 for e in risk_entries
                    if frame_id in (e.get("frame", "") + " " + e.get("risk", "")).lower()
                )
                personalized = True
                citation = f"you accepted this risk {count} time(s) in recent contracts"
                severity = "HIGH"  # personalized risks rank higher
                break
        if not personalized:
            for gap in gap_themes:
                if len(set(gap.lower().split()) & task_words) >= 2:
                    personalized = True
                    citation = f"recurring gap theme: {gap[:60]}"
                    severity = "HIGH"
                    break
        if not personalized:
            for cause in failed_causes:
                if len(set(cause.lower().split()) & task_words) >= 2:
                    personalized = True
                    citation = f"prior FAILED outcome: {cause[:60]}"
                    severity = "HIGH"
                    break

        provocations.append({
            "frame": frame_id,
            "label": _FRAME_LABELS[frame_id],
            "risk": risk_text,
            "severity": severity,
            "personalized": personalized,
            "citation": citation,
        })

    # Sort: personalized first, then HIGH > MEDIUM > LOW
    sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    provocations.sort(key=lambda p: (0 if p["personalized"] else 1, sev_order.get(p["severity"], 3)))

    # Trim to bounds: ≤3 for MINI, 5-7 for FULL
    max_count = 3 if size == TaskSize.M else 7
    min_count = 5 if size in (TaskSize.L, TaskSize.XL) else 0
    result = provocations[:max_count]
    # Pad to min with lower-severity items if needed (but don't pad with empty)
    if len(result) < min_count:
        remaining = [p for p in provocations if p not in result]
        result += remaining[: min_count - len(result)]
    return result


def _check_f1(task_lower: str) -> tuple[bool, str]:
    signals = ["automat", "track", "metric", "measur", "report", "dashboard", "alert", "log"]
    if any(s in task_lower for s in signals):
        return True, "If this mechanism works perfectly, does the developer actually feel the benefit — or is it a metric that doesn't correspond to a felt change?"
    return True, "Does the user benefit materialize without requiring behavior change that isn't incentivized?"


def _check_f2(task_lower: str) -> tuple[bool, str]:
    signals = ["new", "add", "build", "create", "implement", "write", "tool", "system"]
    if any(s in task_lower for s in signals):
        return True, "Is there a simpler or more robust technical approach being overlooked before adding new machinery?"
    return False, ""


def _check_f3(task_lower: str) -> tuple[bool, str]:
    signals = ["fix", "bug", "broken", "wrong", "fail", "error", "issue", "problem"]
    if any(s in task_lower for s in signals):
        return True, "What evidence confirms this is the root cause? Have we traced it or are we fixing a symptom?"
    return True, "What observable evidence would confirm success — and can we verify it before calling the task done?"


def _check_f4(task_lower: str) -> tuple[bool, str]:
    signals = ["rate", "score", "percent", "count", "metric", "track", "measur", "kpi"]
    if any(s in task_lower for s in signals):
        return True, "Could optimizing the stated metric miss the real goal? Is the proxy measurement aligned with actual developer value?"
    return False, ""


def _check_f5(task_lower: str) -> tuple[bool, str]:
    signals = ["hook", "auto", "detect", "silent", "background", "persist", "state", "file"]
    if any(s in task_lower for s in signals):
        return True, "What silent failure mode exists here? What are we trusting that could break without surfacing an error?"
    return False, ""


def _check_f6(task_lower: str, size: TaskSize) -> tuple[bool, str]:
    if size in (TaskSize.L, TaskSize.XL):
        return True, "Is the ceremony this creates proportionate to the value? Does the developer need to do something different for every task?"
    return False, ""


def _check_f7(task_lower: str) -> tuple[bool, str]:
    signals = ["session", "audit", "log", "file", "state", "persist", "write", "read", "store"]
    if any(s in task_lower for s in signals):
        return True, "What happens to this mechanism when the session count or file size grows 10×? Is there a cleanup or cap?"
    return False, ""


def _next_contract_id() -> str:
    """Generate a short sequential contract id (TC-YYYYMMDD-NNN)."""
    today = datetime.now(UTC).strftime("%Y%m%d")
    _CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(_CONTRACTS_DIR.glob(f"*{today}*.md"))
    return f"TC-{today}-{len(existing) + 1:03d}"


def _render_contract(
    contract_id: str,
    task: str,
    size: TaskSize,
    provocations: list[dict],
    date_str: str,
) -> str:
    """Render the contract markdown. Fields are youk's best interpretation."""
    is_mini = size == TaskSize.M
    size_label = size.value

    lines = [
        f"TASK CONTRACT {contract_id} — {date_str} — size {size_label}",
        f"GOAL (in youk's words):        {task}",
        "DONE-MEANS (observable):       [describe what a reviewer could check to confirm done]",
        "SCOPE-IN:",
        "  - [primary deliverable]",
        "  - [secondary deliverable]",
        "SCOPE-OUT (will NOT touch):",
        "  - [highest-value exclusion — write this carefully]",
        "  - [second exclusion]",
        "ASSUMPTIONS:",
        "  - [stated-by-you] [assumption the developer stated explicitly]",
        "  - [inferred] [assumption youk inferred from context]",
        "  - [default] [assumption that holds unless stated otherwise]",
        "APPROACH:                      [2 lines max — what will be built and how]",
        "",
        "PROVOCATIONS (dispositions required before work starts):",
    ]

    for i, p in enumerate(provocations, 1):
        citation_suffix = f" ({p['citation']})" if p["citation"] else ""
        lines.append(
            f"  P{i} [{p['frame']} {p['label']}] {p['risk']}{citation_suffix}"
            f"          → IN-SCOPE | DEFER | ACCEPT-RISK | N/A"
        )

    if not is_mini:
        lines += [
            "",
            "CUT-LIST (in a complete version but NOT this pass):",
            "  - [honest triage — what would be built in a follow-up]",
        ]

    lines += [
        "",
        "LOWEST-CONFIDENCE FIELD: DONE-MEANS — observable acceptance criteria require developer input",
        "OPEN QUESTION (max 1):   none",
    ]

    return "\n".join(lines)


def generate_task_contract(task: str, size: str | None = None) -> dict:
    """
    Generate a task intake contract for the given task.

    Returns:
        contract_required (bool)
        reason (str) — when False
        contract_id (str)
        path (str)
        contract (str) — markdown ready to present
        size (str)
    """
    # Size resolution
    if size:
        try:
            resolved_size = TaskSize(size.upper())
        except ValueError:
            resolved_size = _score_size(task)
    else:
        resolved_size = _score_size(task)

    # Sizing gate (F6 ceremony-proportionality)
    if resolved_size in (TaskSize.XS, TaskSize.S):
        return {
            "contract_required": False,
            "reason": f"below contract line (size={resolved_size.value})",
            "size": resolved_size.value,
        }

    contract_id = _next_contract_id()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # Load personalization data
    risk_entries = _load_recent_risk_ledger()
    gap_themes = _load_recent_gaps()
    failed_causes = _load_failed_outcomes()

    provocations = _generate_provocations(
        task, resolved_size, risk_entries, gap_themes, failed_causes
    )

    contract_text = _render_contract(contract_id, task, resolved_size, provocations, date_str)

    # Persist the as-presented version
    _CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]", "-", task[:40].lower()).strip("-")
    filename = f"{date_str}-{slug}-{contract_id}.md"
    path = _CONTRACTS_DIR / filename

    record = {
        "contract_id": contract_id,
        "task": task,
        "size": resolved_size.value,
        "date": date_str,
        "as_presented": contract_text,
        "as_approved": None,  # filled when developer approves
    }
    path.write_text(
        f"---\n{json.dumps(record, indent=2)}\n---\n\n{contract_text}\n"
    )

    return {
        "contract_required": True,
        "contract_id": contract_id,
        "path": str(path),
        "contract": contract_text,
        "size": resolved_size.value,
    }


def approve_task_contract(
    contract_id: str,
    as_approved: str,
    disposition_map: dict[str, str] | None = None,
) -> dict:
    """
    Record the developer's approved version of the contract.
    disposition_map: {P1: "IN-SCOPE", P2: "DEFER", ...}
    Returns: {saved, fields_edited, edit_rate, unresolved_provocations}
    """
    _CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    matches = list(_CONTRACTS_DIR.glob(f"*{contract_id}*.md"))
    if not matches:
        return {"saved": False, "error": f"contract {contract_id} not found"}

    path = matches[0]
    raw = path.read_text()
    # Parse the YAML front-matter
    try:
        _, fm_text, body = raw.split("---\n", 2)
        record = json.loads(fm_text)
    except Exception:
        return {"saved": False, "error": "could not parse contract file"}

    as_presented = record.get("as_presented", "")
    record["as_approved"] = as_approved
    if disposition_map:
        record["dispositions"] = disposition_map

    # Count edited fields (lines that differ between presented and approved)
    presented_lines = set(as_presented.splitlines())
    approved_lines = set(as_approved.splitlines())
    edited = len(approved_lines - presented_lines)
    total_fields = max(len(presented_lines), 1)
    edit_rate = round(edited / total_fields, 3)
    record["edit_rate"] = edit_rate

    # Check for unresolved provocations
    unresolved: list[str] = []
    for line in as_approved.splitlines():
        if "→ IN-SCOPE | DEFER | ACCEPT-RISK | N/A" in line:
            m = re.match(r"\s*(P\d+)", line)
            if m:
                unresolved.append(m.group(1))

    record["unresolved_provocations"] = unresolved
    path.write_text(f"---\n{json.dumps(record, indent=2)}\n---\n\n{as_approved}\n")

    # Append ACCEPT-RISK items to risk ledger
    dispositions = disposition_map or {}
    for key, disposition in dispositions.items():
        if disposition.upper() == "ACCEPT-RISK":
            entry = {
                "date": datetime.now(UTC).isoformat(),
                "contract_id": contract_id,
                "risk": key,
                "frame": "",
            }
            # Find the provocation text for this key
            for line in as_approved.splitlines():
                if line.strip().startswith(f"{key} ["):
                    m = re.match(r"\s*P\d+ \[(\w+[^]]*)\] (.+?)(?:\s+→|\s*$)", line)
                    if m:
                        entry["frame"] = m.group(1).strip()
                        entry["risk"] = m.group(2).strip()
                    break
            try:
                _RISK_LEDGER.parent.mkdir(parents=True, exist_ok=True)
                with open(_RISK_LEDGER, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass

    return {
        "saved": True,
        "contract_id": contract_id,
        "fields_edited": edited,
        "edit_rate": edit_rate,
        "unresolved_provocations": unresolved,
        "blocked": len(unresolved) > 0,
    }


def check_task_contract_gate(size: str) -> dict:
    """
    Returns blocked=True iff size in (L, XL) and no approved contract with
    resolved dispositions exists this session.
    """
    try:
        task_size = TaskSize(size.upper())
    except ValueError:
        return {"blocked": False, "reason": "unrecognized size"}

    if task_size not in (TaskSize.L, TaskSize.XL):
        return {"blocked": False, "reason": f"size={size} is below contract gate (L/XL only)"}

    # Check for any contract approved today with no unresolved provocations
    _CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y%m%d")
    for f in sorted(_CONTRACTS_DIR.glob(f"*{today}*.md"), reverse=True):
        try:
            raw = f.read_text()
            _, fm_text, _ = raw.split("---\n", 2)
            record = json.loads(fm_text)
            if record.get("as_approved") and not record.get("unresolved_provocations"):
                return {"blocked": False, "contract_id": record.get("contract_id")}
        except Exception:
            continue

    return {
        "blocked": True,
        "reason": f"size={size} requires an approved task contract with resolved provocations before work starts",
    }


def compute_contract_edit_rate(last_n: int = 10) -> dict:
    """
    Compute trailing edit rate: fields materially edited / fields presented.
    R10-labeled denominator.
    Returns {edit_rate, fields_edited, fields_total, contracts_measured, r10_label}
    """
    _CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_CONTRACTS_DIR.glob("*.md"), reverse=True)[:last_n]

    total_edited = 0
    total_fields = 0
    measured = 0

    for f in files:
        try:
            raw = f.read_text()
            _, fm_text, _ = raw.split("---\n", 2)
            record = json.loads(fm_text)
            if record.get("as_approved") is not None:
                rate = record.get("edit_rate", 0.0)
                # Reconstruct absolute counts from rate and presented line count
                presented_lines = len(record.get("as_presented", "").splitlines())
                edited = round(rate * presented_lines)
                total_edited += edited
                total_fields += presented_lines
                measured += 1
        except Exception:
            continue

    if not total_fields:
        return {
            "edit_rate": 0.0,
            "fields_edited": 0,
            "fields_total": 0,
            "contracts_measured": 0,
            "r10_label": f"contract edit rate [R10]: 0% (0/0 fields, last {last_n} contracts)",
        }

    rate = round(total_edited / total_fields * 100)
    return {
        "edit_rate": round(total_edited / total_fields, 3),
        "fields_edited": total_edited,
        "fields_total": total_fields,
        "contracts_measured": measured,
        "r10_label": (
            f"contract edit rate [R10]: {rate}% "
            f"(edited {total_edited}/{total_fields} fields, last {last_n} contracts)"
        ),
    }


def compute_accept_risk_bite_rate() -> dict:
    """
    accept_risk_bite_rate: ACCEPT-RISK entries later linked to FAILED outcome / same-theme gap.
    Denominator: total ACCEPT-RISK entries in ledger.
    Returns {bite_rate, bites, total_accept_risk, r10_label}
    """
    if not _RISK_LEDGER.exists():
        return {
            "bite_rate": 0.0,
            "bites": 0,
            "total_accept_risk": 0,
            "r10_label": "accept_risk bite rate [R10]: 0% (0/0 accept-risk entries)",
        }

    entries = []
    try:
        for line in _RISK_LEDGER.read_text().splitlines():
            if line.strip():
                entries.append(json.loads(line))
    except Exception:
        pass

    if not entries:
        return {
            "bite_rate": 0.0,
            "bites": 0,
            "total_accept_risk": 0,
            "r10_label": "accept_risk bite rate [R10]: 0% (0/0 accept-risk entries)",
        }

    # Bites: entries with a "outcome" field set to "FAILED" or "gap_confirmed"
    bites = sum(1 for e in entries if e.get("outcome") in ("FAILED", "gap_confirmed"))
    total = len(entries)
    rate = round(bites / total * 100) if total else 0
    return {
        "bite_rate": round(bites / total, 3) if total else 0.0,
        "bites": bites,
        "total_accept_risk": total,
        "r10_label": (
            f"accept_risk bite rate [R10]: {rate}% "
            f"({bites}/{total} accept-risk entries confirmed)"
        ),
    }
