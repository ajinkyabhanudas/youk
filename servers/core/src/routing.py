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
    Net-score routing: positive signal matches minus (negative signal matches × 2).
    A negative signal is a strong downward vote — it takes two positive signals to
    override one negative. This makes "implement a typo fix" route XS (add=+1, typo=-2
    net=-1), not M (add=+1 only).
    """
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
        # XS signals without positive match — check if any XS signal is present
        xs_signals = sizes.get("XS", {}).get("signals", [])
        if any(s.lower() in task_lower for s in xs_signals):
            return TaskSize.XS
        # Fall back to word count heuristic
        word_count = len(task.split())
        if word_count <= 5:
            return TaskSize.XS
        elif word_count <= 15:
            return TaskSize.S
        elif word_count <= 40:
            return TaskSize.M
        return TaskSize.L

    # Highest net score wins; tie-break by size order (larger size preferred)
    scored.sort(key=lambda x: (x[0], size_order.get(x[1].value, 0)), reverse=True)
    return scored[0][1]


def route_task(
    task: str,
    skills_already_invoked: list[str] | None = None,
    intent_brief: dict | None = None,
) -> RoutingDecision:
    # Scope-collapse gate: if an intent brief was provided and scope is still
    # ambiguous, block routing and surface the collapsing question.
    # The model must re-call optimize_intent with the user's answer, then
    # re-call route_task with the resolved brief before any skill can run.
    if intent_brief and intent_brief.get("ambiguity_detected"):
        fork = intent_brief.get("solution_fork") or {}
        question = (
            fork.get("collapsing_question")
            or (intent_brief.get("clarifying_questions") or [""])[0]
            or "Please clarify the scope before proceeding."
        )
        # Stub out a minimal RoutingDecision — size unknown until scope is resolved
        return RoutingDecision(
            task=task,
            size=TaskSize.M,  # conservative placeholder
            ceremony="blocked",
            skills=[],
            nfr_mode="none",
            blocked=True,
            collapsing_question=question,
        )

    # Intent-collapse gate: scope-ambiguity (above) catches "which of two implementations?"
    # This gate catches "what does the user actually want to experience?" — a different failure.
    # A request with quality words ("elite", "better") or mindset goals ("discover the pattern")
    # is not scope-ambiguous but IS intent-opaque: either reading leads to the same size task,
    # but the translation from stated goal to concrete deliverable may be entirely wrong.
    gt = (intent_brief or {}).get("goal_translation") or {}
    if gt.get("translation_risk") == "high":
        question = (
            gt.get("translation_question")
            or "What would you observe at the end of this that tells you it worked — in terms of your own experience, not the system's output?"
        )
        return RoutingDecision(
            task=task,
            size=TaskSize.M,
            ceremony="blocked",
            skills=[],
            nfr_mode="none",
            blocked=True,
            collapsing_question=question,
        )

    routes = _load_routes()
    # If a resolved intent brief was provided, prefer its estimated size over
    # keyword scoring — the brief has already reasoned about the problem.
    if intent_brief and not intent_brief.get("ambiguity_detected"):
        brief_size = intent_brief.get("estimated_size", "")
        if brief_size in ("XS", "S", "M", "L", "XL"):
            size = TaskSize(brief_size)
        else:
            size = _score_size(task, routes)
    else:
        size = _score_size(task, routes)

    sizes_config = routes.get("task_sizes", {})
    size_config = sizes_config.get(size.value, {})

    ceremony = size_config.get("ceremony", "none")
    skills = size_config.get("skills", [])
    nfr_mode = size_config.get("nfr_mode", "fast_path_2q")
    token_budget = routes.get("token_budgets", {}).get(size.value, 0)

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

    plan_hook = ""
    if size in (TaskSize.M, TaskSize.L, TaskSize.XL) and skills:
        skill_chain = " → ".join(skills)
        plan_hook = (
            f"{size.value} task — {skill_chain}. "
            f"Starting with {skills[0]}. "
            f"Redirect with one line if wrong, otherwise proceeding."
        )

    return RoutingDecision(
        task=task,
        size=size,
        ceremony=ceremony,
        skills=skills,
        nfr_mode=nfr_mode,
        token_budget=token_budget,
        warnings=warnings,
        plan_hook=plan_hook,
    )
