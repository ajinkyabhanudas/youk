from __future__ import annotations

import re
import json
import yaml
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")
from models import TaskSize, RoutingDecision, SoftRuleWarning, ViolationType

YOUK_ROOT = Path("/youk")
ROUTES_FILE = YOUK_ROOT / "config" / "routes.yaml"
def _breadcrumb_file(slug: str = "") -> Path:
    """Return slug-scoped breadcrumb path, falling back to root for unknown slug."""
    if slug:
        d = YOUK_ROOT / "state" / "sessions" / slug
        d.mkdir(parents=True, exist_ok=True)
        return d / "routing-breadcrumb.json"
    return YOUK_ROOT / "state" / "routing-breadcrumb.json"


def _write_routing_breadcrumb(task: str, size: str, slug: str = "") -> None:
    """Record that route_task fired for this task. Cleared by task_checkpoint after read."""
    import hashlib as _hashlib
    task_id = _hashlib.sha1(task.encode()).hexdigest()[:12]
    # Work that names a task already in this project's plan (e.g. "build S08") is that task, so
    # starting and finishing it lands on the plan's node and not on a second hashed one.
    try:
        from graph import find_mentioned_task
        task_id = (find_mentioned_task(slug, task) if slug else None) or task_id
    except Exception:
        pass
    _BREADCRUMB_FILE = _breadcrumb_file(slug)
    try:
        _BREADCRUMB_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BREADCRUMB_FILE.write_text(json.dumps({
            "task": task[:200],
            "task_id": task_id,
            "size": size,
            "routed_at": datetime.utcnow().isoformat(),
        }))
    except Exception:
        pass


def _write_medium_risk_question(question: str, slug: str = "") -> None:
    """Persist medium-risk translation question so task_checkpoint can verify it was surfaced."""
    target = (
        _breadcrumb_file(slug).parent / "medium-risk-question.json"
        if slug
        else YOUK_ROOT / "state" / "medium-risk-question.json"
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "question": question,
            "surfaced": False,
            "written_at": datetime.utcnow().isoformat(),
        }))
    except Exception:
        pass


def _load_routes() -> dict:
    if not ROUTES_FILE.exists():
        return {}
    with open(ROUTES_FILE) as f:
        return yaml.safe_load(f)


# ── Scope escalation (CIR-150 item 2 / CIR-151) ────────────────────────────────
#
# task_contract.py's disposition vocabulary was IN-SCOPE | DEFER | ACCEPT-RISK |
# N/A — no way for a finding that "the ORIGINAL problem framing is wrong" (Lens 1:
# is the stated problem a symptom of a deeper problem? / intake Phase 4 GAP
# SYNTHESIS: the restated problem materially changes scope) to actually widen
# what gets built. It could only be printed and dropped, or fall into
# challenge's minimum-revision check — which is the WRONG rule for this case:
# minimum-revision governs REVISING a direction to address an objection WITHIN
# its existing scope; it exists specifically to suppress widening there. This is
# the opposite situation — the scope itself needs to grow — and must not be
# suppressed by that rule. write_scope_escalation / _consume_scope_escalation
# below is the real mechanism: a one-shot, slug-scoped signal file that forces
# route_task's very next call this session to a floor size, so the finding
# actually changes what gets built instead of just getting surfaced as text.

_SIZE_RANK = {TaskSize.XS: 1, TaskSize.S: 2, TaskSize.M: 3, TaskSize.L: 4, TaskSize.XL: 5}


def _scope_escalation_file(slug: str) -> Path:
    """Path only — no mkdir. Path.exists()/.read_text() never need the parent
    directory to exist, and route_task calls this on every invocation (via
    _consume_scope_escalation) regardless of whether any escalation was ever
    written, so a side-effecting mkdir here would create session directories
    for slugs that never had one and, worse, crash on a read-only mount where
    the state tree hasn't been created yet by anything else."""
    d = YOUK_ROOT / "state" / "sessions" / (slug or "unknown")
    return d / "scope-escalation.json"


def write_scope_escalation(slug: str, task: str, reason: str, suggested_size: str, source: str) -> dict:
    """
    Persist a scope-escalation signal. Called from task_contract.py's ESCALATE
    disposition, or directly by challenge/intake when Lens 1 / GAP SYNTHESIS
    finds the original framing was wrong.

    suggested_size must be M, L, or XL — escalation only ever grows scope, never
    shrinks it. Returns {"escalated": False, "reason": ...} on an invalid size
    rather than raising: this is called from in-session skill reasoning that
    should degrade safely on a malformed value, not crash the calling turn.
    """
    try:
        target = TaskSize(suggested_size.upper())
    except ValueError:
        return {"escalated": False, "reason": f"invalid suggested_size: {suggested_size!r}"}
    if target not in (TaskSize.M, TaskSize.L, TaskSize.XL):
        return {"escalated": False, "reason": "escalation must target M, L, or XL"}

    entry = {
        # Normalized the same way _scope_escalation_file resolves the file
        # path, so a slug of "" and "unknown" can never look like a mismatch
        # between where the file lives and what _consume_scope_escalation's
        # slug check compares against.
        "slug": slug or "unknown",
        "task": task[:200],
        "reason": reason,
        "suggested_size": target.value,
        "source": source,
        "ts": datetime.utcnow().isoformat(),
        "consumed": False,
    }
    _escalation_path = _scope_escalation_file(slug)
    _escalation_path.parent.mkdir(parents=True, exist_ok=True)
    _escalation_path.write_text(json.dumps(entry))
    return {
        "escalated": True,
        "suggested_size": target.value,
        "instruction": (
            f"Scope escalation recorded ({source}): {reason} Call route_task "
            f"again for this task — the next call this session will not settle "
            f"for a size smaller than {target.value}."
        ),
    }


def _consume_scope_escalation(slug: str) -> TaskSize | None:
    """
    Read and consume (mark used) a pending scope escalation for this slug.

    One-shot by design: applies to exactly the next route_task call, not every
    subsequent call this session. An escalation that silently reapplied forever
    would make route_task's returned size unpredictable long after the finding
    that justified it stopped being the live concern.
    """
    f = _scope_escalation_file(slug)
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
    except Exception:
        return None
    if data.get("consumed") or data.get("slug") != (slug or "unknown"):
        return None
    try:
        size = TaskSize(data.get("suggested_size", ""))
    except ValueError:
        return None
    data["consumed"] = True
    try:
        f.write_text(json.dumps(data))
    except Exception:
        pass
    return size


_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {}


def _signal_in(signal: str, text_lower: str) -> bool:
    """Whole-word match with ordinary inflections (add -> adds/added/adding,
    migrate -> migrating). A bare substring test fired "add" inside "padding"
    and "address", sending a CSS tweak through the full M-size gate chain."""
    sig = signal.lower()
    pattern = _SIGNAL_PATTERNS.get(sig)
    if pattern is None:
        stem = re.escape(sig[:-1]) + "(?:e|es|ed|ing)" if sig.endswith("e") else re.escape(sig) + "(?:s|es|ed|ing)?"
        pattern = _SIGNAL_PATTERNS[sig] = re.compile(r"(?<![a-z0-9])" + stem + r"(?![a-z0-9])")
    return pattern.search(text_lower) is not None


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
        positive = sum(1 for s in config.get("signals", []) if _signal_in(s, task_lower))
        negative = sum(1 for s in config.get("negative_signals", []) if _signal_in(s, task_lower))
        net = positive - (negative * 2)
        if net > 0:
            scored.append((net, TaskSize(size_name)))

    if not scored:
        # XS signals without positive match — check if any XS signal is present
        xs_signals = sizes.get("XS", {}).get("signals", [])
        if any(_signal_in(s, task_lower) for s in xs_signals):
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
    slug: str = "",
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

    _medium_risk_question: str = ""
    if gt.get("translation_risk") == "medium":
        _medium_risk_question = (
            gt.get("translation_question")
            or "What would a successful outcome look like from your perspective — not the system's output?"
        )
        _write_medium_risk_question(_medium_risk_question, slug=slug)

    routes = _load_routes()
    _size_order = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5}
    _size_mismatch_flag = False
    _size_mismatch_note = ""
    _llm_estimated_size = ""

    # An LLM judging the size of its own task, unchecked, is the same
    # self-confirmation gap every other high-stakes judgment call in this
    # codebase has a deterministic check for. estimated_size is always
    # cross-checked against route_task's own keyword scoring of the same
    # text; the larger of the two wins, never the smaller self-reported one.
    deterministic_size = _score_size(task, routes)
    if intent_brief and not intent_brief.get("ambiguity_detected"):
        brief_size = intent_brief.get("estimated_size", "")
        if brief_size in ("XS", "S", "M", "L", "XL"):
            _llm_estimated_size = brief_size
            if _size_order[brief_size] < _size_order[deterministic_size.value]:
                size = deterministic_size
                _size_mismatch_flag = True
                _size_mismatch_note = (
                    f"optimize_intent estimated {brief_size}, but deterministic "
                    f"keyword scoring of the same task text found {deterministic_size.value} "
                    f"— using {deterministic_size.value} (the larger, safer size)."
                )
            else:
                size = TaskSize(brief_size)
        else:
            size = deterministic_size
    else:
        size = deterministic_size

    try:
        from sizing_decision import log_sizing_decision
        log_sizing_decision(
            task=task,
            deterministic_size=deterministic_size.value,
            llm_estimated_size=_llm_estimated_size,
            resolved_size=size.value,
            mismatch_flag=_size_mismatch_flag,
            log_path=YOUK_ROOT / "state" / "sizing-decisions.jsonl",
            grounding=(intent_brief or {}).get("grounding"),
        )
    except Exception as e:
        # Never block the routing decision, but never hide that the record is
        # missing either: a gap here silently starves precedent retrieval.
        print(f"youk: sizing decision not logged ({type(e).__name__}: {e})", file=sys.stderr)

    # Scope escalation (CIR-150 item 2 / CIR-151): a pending, unconsumed
    # write_scope_escalation() signal for this slug forces a floor on the size
    # computed above — never lowers it, only raises it, and only once.
    scope_escalated = False
    scope_escalation_reason = ""
    _escalated_size = _consume_scope_escalation(slug)
    if _escalated_size is not None and _SIZE_RANK[_escalated_size] > _SIZE_RANK[size]:
        scope_escalated = True
        scope_escalation_reason = (
            f"escalated from {size.value} to {_escalated_size.value} — the "
            "original problem framing was found to be wrong, not just under-specified"
        )
        size = _escalated_size

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

    if _medium_risk_question and size in (TaskSize.M, TaskSize.L, TaskSize.XL):
        warnings.append(SoftRuleWarning(
            rule_id="medium-translation-risk",
            name="Medium translation risk",
            message=f"Translation risk is medium. Surface this before coding: {_medium_risk_question}",
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

    # Overengineering detection: scope-expanding language in the task description.
    # Fires inline so route_task callers get the signal without a separate tool call.
    _OVERENG_TERMS = {
        "extensible", "pluggable", "generic", "flexible", "reusable", "for all",
        "future-proof", "future proof", "scalable", "modular", "configurable",
        "abstraction", "framework", "platform", "general-purpose",
    }
    task_lower = task.lower()
    _overeng_flag = size in (TaskSize.M, TaskSize.L, TaskSize.XL) and any(
        t in task_lower for t in _OVERENG_TERMS
    )
    _overeng_note: str | None = None
    if _overeng_flag:
        matched = [t for t in _OVERENG_TERMS if t in task_lower]
        _overeng_note = (
            f"Task uses scope-expanding language ({', '.join(matched[:3])}). "
            "Consider the simplest implementation that satisfies the current need. "
            "Approve current scope (A), choose a simpler path (B), or defer scope discussion (C)."
        )

    decision = RoutingDecision(
        task=task,
        size=size,
        ceremony=ceremony,
        skills=skills,
        nfr_mode=nfr_mode,
        token_budget=token_budget,
        warnings=warnings,
        plan_hook=plan_hook,
        overengineering_flag=_overeng_flag,
        overengineering_note=_overeng_note,
        size_mismatch_flag=_size_mismatch_flag,
        size_mismatch_note=_size_mismatch_note,
        scope_escalated=scope_escalated,
        scope_escalation_reason=scope_escalation_reason,
    )
    # Write breadcrumb so task_checkpoint can verify routing ran before M+ work.
    # Only write for non-blocked M+ decisions — XS/S bypass is intentional.
    if not decision.blocked and size in (TaskSize.M, TaskSize.L, TaskSize.XL):
        _write_routing_breadcrumb(task, size.value, slug=slug)
    return decision
