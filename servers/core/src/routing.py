from __future__ import annotations
import yaml
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import TaskSize, RoutingDecision, SoftRuleWarning, ViolationType

YOUK_ROOT = Path("/youk")
ROUTES_FILE = YOUK_ROOT / "config" / "routes.yaml"


def _load_routes() -> dict:
    if not ROUTES_FILE.exists():
        return {}
    with open(ROUTES_FILE) as f:
        return yaml.safe_load(f)


def _score_size(task: str, routes: dict) -> TaskSize:
    """
    Score task size by matching against signal keywords.
    Returns the highest-priority size whose signals appear in the task description.
    Tie-break: prefer more specific (larger) size.
    """
    task_lower = task.lower()
    sizes = routes.get("task_sizes", {})

    matched: list[tuple[int, TaskSize]] = []
    size_order = {"XL": 5, "L": 4, "M": 3, "S": 2, "XS": 1}

    for size_name, config in sizes.items():
        signals = config.get("signals", [])
        score = sum(1 for s in signals if s.lower() in task_lower)
        if score > 0:
            matched.append((score, TaskSize(size_name)))

    if not matched:
        # Default by description length
        word_count = len(task.split())
        if word_count <= 5:
            return TaskSize.XS
        elif word_count <= 15:
            return TaskSize.S
        elif word_count <= 40:
            return TaskSize.M
        else:
            return TaskSize.L

    # Highest match score wins; tie-break by size order (larger wins)
    matched.sort(key=lambda x: (x[0], size_order.get(x[1].value, 0)), reverse=True)
    return matched[0][1]


def route_task(task: str, skills_already_invoked: list[str] | None = None) -> RoutingDecision:
    routes = _load_routes()
    size = _score_size(task, routes)
    sizes_config = routes.get("task_sizes", {})
    size_config = sizes_config.get(size.value, {})

    ceremony = size_config.get("ceremony", "none")
    skills = size_config.get("skills", [])
    nfr_mode = size_config.get("nfr_mode", "fast_path_2q")

    # Build soft rule warnings
    warnings: list[SoftRuleWarning] = []
    invoked = skills_already_invoked or []

    if size in (TaskSize.M, TaskSize.L, TaskSize.XL) and "nfr_check" not in invoked:
        warnings.append(SoftRuleWarning(
            rule_id="nfr-before-m-tasks",
            name="NFR check before M+ tasks",
            message=f"Sized as {size.value} — NFR check recommended before coding.",
            violation_type=ViolationType.SURFACE,
        ))

    if size in (TaskSize.L, TaskSize.XL) and "write_spec" not in invoked:
        warnings.append(SoftRuleWarning(
            rule_id="spec-before-l-tasks",
            name="write-spec before L/XL tasks",
            message=f"Sized as {size.value} — write-spec recommended before dev-loop.",
            violation_type=ViolationType.SURFACE,
        ))

    return RoutingDecision(
        task=task,
        size=size,
        ceremony=ceremony,
        skills=skills,
        nfr_mode=nfr_mode,
        warnings=warnings,
    )
