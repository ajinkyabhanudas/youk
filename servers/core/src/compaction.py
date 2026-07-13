"""
Context compaction — youk's alternative to Claude's generic auto-compaction.

The key difference: Claude compacts by recency. Youk compacts by information tier.
CONTRACT content is pinned verbatim. DECISION content is summarized. EXPLORATION
is compressed. CLARIFICATION is dropped. The brief is rebuilt from structured files,
not summarized from conversation — so no information is lost through paraphrase.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, "/shared")

YOUK_ROOT = Path("/youk")

_TIER_INSTRUCTION = """CONTRACT lines are load-bearing behavioral agreements — preserve them VERBATIM through any further compaction. Never paraphrase, shorten, or omit them. They are exactly what must survive."""


def _slug(project_dir: str) -> str:
    return Path(project_dir).name or "unknown"


def _load_contracts(slug: str) -> list[str]:
    f = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    if not f.exists():
        return []
    return [
        line.strip()
        for line in f.read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("---")
    ]


def _load_decisions(slug: str) -> list[str]:
    f = YOUK_ROOT / "knowledge" / "projects" / slug / "decisions.md"
    if not f.exists():
        return []
    # Return the most recent 5 decision headings with one-line summary
    lines = f.read_text().splitlines()
    decisions = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ") and current:
            decisions.append("\n".join(current))
            current = [line]
        elif line.strip():
            current.append(line)
    if current:
        decisions.append("\n".join(current))
    return decisions[-5:]  # last 5 decisions only


def _load_task_state() -> dict:
    state_file = YOUK_ROOT / "state" / "session.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text())
    except Exception:
        return {}


def _load_session_plan(slug: str = "") -> list[str]:
    plan_file = YOUK_ROOT / "state" / "session-plan.json"
    if not plan_file.exists():
        return []
    try:
        data = json.loads(plan_file.read_text())
        # Guard: if stored plan belongs to a different project, return empty so
        # build_brief doesn't embed another project's resume point in this brief.
        if slug and data.get("slug") and data["slug"] != slug:
            return []
        return data.get("plan", [])
    except Exception:
        return []


def _load_domain_gaps(max_gaps: int = 3) -> list[str]:
    """Load HIGH-priority unaddressed gaps from knowledge/domain/gaps.md."""
    gaps_file = YOUK_ROOT / "knowledge" / "domain" / "gaps.md"
    if not gaps_file.exists():
        return []
    gaps = []
    for line in gaps_file.read_text().splitlines():
        if "HIGH" not in line:
            continue
        # Skip rows that are already addressed (have a date in the Addressed column)
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 5 and cells[4] not in ("—", "-", ""):
            continue
        if cells and cells[0] not in ("Concept", "---"):
            gaps.append(cells[0])
            if len(gaps) >= max_gaps:
                break
    return gaps


def _load_survey_summary(slug: str, max_chars: int = 400) -> str:
    """Return the first max_chars of survey.md — stack + architecture headline only."""
    survey = YOUK_ROOT / "knowledge" / "projects" / slug / "survey.md"
    if not survey.exists():
        return ""
    try:
        return survey.read_text()[:max_chars]
    except Exception:
        return ""


def _load_domain_knowledge_summary(cap: int = 10) -> str:
    """Returns comma-separated concept headings from knowledge/domain/ for the brief."""
    domain_dir = YOUK_ROOT / "knowledge" / "domain"
    if not domain_dir.exists():
        return ""
    headings = []
    for f in sorted(domain_dir.glob("*.md")):
        if f.name in ("gaps.md",):
            continue
        try:
            for line in f.read_text().splitlines():
                if line.startswith("## "):
                    headings.append(line[3:].strip())
                    if len(headings) >= cap:
                        break
        except Exception:
            continue
        if len(headings) >= cap:
            break
    return ", ".join(headings) if headings else ""


_BRIEF_STOP_WORDS = {
    "the", "a", "an", "and", "or", "not", "in", "on", "at", "from",
    "to", "with", "by", "for", "of", "it", "is", "we", "you", "can",
    "do", "this", "that", "what", "how", "why", "when", "where",
    "help", "me", "my", "our", "its", "be", "has", "have", "are",
    "was", "were", "will", "would", "could", "should", "want", "need",
    "get", "make", "let", "just", "also", "now", "then", "use",
}


def _intent_keywords(intent: str) -> set[str]:
    return {
        w.lower().strip(".,!?:;\"'()[]")
        for w in intent.split()
        if len(w) > 3 and w.lower() not in _BRIEF_STOP_WORDS
    }


def _contract_matches(contract: str, keywords: set[str]) -> bool:
    if not keywords:
        return True  # no intent = include everything
    return bool({w.lower() for w in contract.split()} & keywords)


def build_brief(project_dir: str, intent: str = "", mode: str = "full") -> dict:
    """
    Build a structured context brief from youk's knowledge store.

    mode="full"  — complete brief (~800-1200 tokens), used at session_start
                   and compact_context. Includes all contracts, all decisions,
                   survey, domain knowledge, gaps.

    mode="index" — intent-gated minimal brief (~100-200 tokens), used when
                   called with a specific intent. Contracts matching intent are
                   verbatim; others are a count only. Decisions compressed.
                   No survey or domain knowledge (too expensive for per-turn use).

    The brief is rebuilt from files, not conversation — contracts survive
    compaction without paraphrase degradation.
    """
    slug = _slug(project_dir)
    contracts = _load_contracts(slug)
    decisions = _load_decisions(slug)
    state = _load_task_state()
    session_plan = _load_session_plan(slug)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    keywords = _intent_keywords(intent) if intent else set()
    is_index = mode == "index" and bool(keywords)

    sections: list[str] = [f"[YOUK CONTEXT BRIEF — {timestamp}]"]

    if is_index:
        # Index model: matching contracts verbatim, rest as count
        matching = [c for c in contracts if _contract_matches(c, keywords)]
        others = len(contracts) - len(matching)
        if matching:
            sections.append("## Contracts (matching current task — verbatim):")
            for c in matching:
                sections.append(f"- {c}")
        if others > 0:
            sections.append(f"(+{others} other contract(s) in contracts.md — read if needed)")

        # Active task from state
        active_file = YOUK_ROOT / "state" / "active_task.json"
        if active_file.exists():
            try:
                import json as _json
                at = _json.loads(active_file.read_text())
                task = at.get("task", "")
                files = ", ".join(at.get("files_touched", [])[:3])
                signal = at.get("last_signal", "")
                parts = [f"Active: {task}"]
                if files:
                    parts.append(f"files: {files}")
                if signal:
                    parts.append(f"last: {signal[:80]}")
                sections.append(" | ".join(parts))
            except Exception:
                pass

        # Resume: first non-warning plan item only
        resume = next((p for p in session_plan if p and not p.startswith("⚠")), "")
        if resume:
            sections.append(f"Resume: {resume[:120]}")

        # Decisions: compressed, 3 max
        if decisions:
            compressed = []
            for d in decisions[-3:]:
                dlines = d.strip().splitlines()
                heading = dlines[0] if dlines else ""
                body = next((ln for ln in dlines[1:] if ln.strip()), "")
                compressed.append(f"{heading}: {body}".strip()[:80])
            sections.append("Decisions: " + " / ".join(compressed))

        sections.append("[/YOUK CONTEXT BRIEF]")
    else:
        # Full model: everything (session_start, compact_context)
        if contracts:
            sections.append("## Pinned Contracts (verbatim — never summarize or paraphrase)")
            for c in contracts:
                sections.append(f"- {c}")
        else:
            sections.append("## Pinned Contracts\n(none saved yet — call session_end to capture working agreements)")

        # Decisions: verbatim when they match intent keywords, compressed otherwise
        if decisions:
            sections.append("## Active Decisions")
            for d in decisions:
                dlines = d.strip().splitlines()
                heading = dlines[0] if dlines else ""
                body = next((ln for ln in dlines[1:] if ln.strip()), "")
                if keywords and any(kw in d.lower() for kw in keywords):
                    sections.append(d.strip())
                else:
                    sections.append(f"{heading}: {body}".strip())

        project = state.get("last_project", project_dir)
        session_n = state.get("session_counter", "?")
        sections.append(
            f"## Session state\n"
            f"Project: {slug} | Session #{session_n} | Dir: {project}"
        )

        if session_plan:
            plan_lines = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(session_plan))
            sections.append(f"## Session plan (from last session_start)\n{plan_lines}")

        survey_summary = _load_survey_summary(slug)
        if survey_summary:
            sections.append(f"## Codebase survey\n{survey_summary}\n(run /survey to refresh)")

        domain_summary = _load_domain_knowledge_summary()
        if domain_summary:
            sections.append(f"## Domain knowledge\n{domain_summary} — /learn adds more")

        domain_gaps = _load_domain_gaps()
        if domain_gaps:
            sections.append(
                "## Active knowledge gaps (HIGH priority)\n"
                + ", ".join(domain_gaps)
                + " — address with /learn"
            )

        sections.append(f"## Compaction instruction\n{_TIER_INSTRUCTION}")

    brief = "\n\n".join(sections)

    # Extract a resume candidate from the session plan — first non-warning item gives
    # a meaningful "what were we working on" for next session if tab is closed without /done.
    resume_candidate = ""
    for item in session_plan:
        if item and not item.startswith("⚠"):
            resume_candidate = item[:200]
            break

    checkpoint_file = YOUK_ROOT / "state" / "session-checkpoint.json"
    try:
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "slug": slug,
            "plan_items": session_plan,
            "contracts_count": len(contracts),
            "resume_candidate": resume_candidate,
        }, indent=2))
        open_file = YOUK_ROOT / "state" / "session-open.json"
        if open_file.exists():
            open_file.unlink()
    except Exception:
        pass

    return {
        "brief": brief,
        "contracts_count": len(contracts),
        "decisions_count": len(decisions),
        "session_plan_items": len(session_plan),
        "slug": slug,
        "generated_at": timestamp,
        "instruction": (
            "PASTE this brief VERBATIM into your next response — do not summarize or paraphrase. "
            "It must appear in recent context to survive the next compaction cycle. "
            "CONTRACT lines are invariant: never rephrase, never shorten, never drop."
        ),
    }


_STOP_WORDS = {
    "always", "never", "use", "the", "a", "an", "and", "or", "not",
    "in", "on", "at", "from", "to", "with", "by", "for", "of", "it", "is",
}


def _conflict_check(new_contract: str, existing: set[str]) -> list[str]:
    new_words = {w for w in new_contract.lower().split() if w not in _STOP_WORDS and len(w) > 2}
    conflicts = []
    for ex in existing:
        ex_words = {w for w in ex.lower().split() if w not in _STOP_WORDS and len(w) > 2}
        if len(new_words & ex_words) >= 2:
            conflicts.append(ex)
    return conflicts


def _tokenize(text: str) -> set[str]:
    """Tokenize contract text: lowercase, strip punctuation, drop stop words and short words."""
    import re as _re
    cleaned = _re.sub(r"[^\w\s]", " ", text.lower())
    return {w for w in cleaned.split() if w not in _STOP_WORDS and len(w) > 3}


def _is_semantic_duplicate(new_contract: str, existing: set[str], threshold: float = 0.8) -> bool:
    """True if new_contract shares ≥threshold of its meaningful words with any existing contract.
    Threshold of 0.8 prevents suppression of related-but-distinct contracts (e.g. class vs hook
    components share domain words but express different rules) while catching near-identical
    restatements of the same agreement."""
    new_words = _tokenize(new_contract)
    # Skip dedup for very short contracts — not enough signal for reliable matching
    if len(new_words) < 3:
        return False
    for ex in existing:
        ex_words = _tokenize(ex)
        if not ex_words:
            continue
        overlap = len(new_words & ex_words)
        # Anchored to smaller set: catches restatements regardless of length difference
        smaller = min(len(new_words), len(ex_words))
        if overlap / smaller >= threshold:
            return True
    return False


def write_contracts(slug: str, new_contracts: list[str]) -> dict:
    """
    Append new contract lines to knowledge/projects/{slug}/contracts.md.
    Returns {"added": int, "conflicts": list[str]} — conflicts are existing contracts
    whose keywords overlap significantly with any of the new ones.
    """
    contracts_file = YOUK_ROOT / "knowledge" / "projects" / slug / "contracts.md"
    contracts_file.parent.mkdir(parents=True, exist_ok=True)

    existing_raw: list[str] = []
    if contracts_file.exists():
        existing_raw = [
            line.strip().lstrip("- ")
            for line in contracts_file.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    existing_normalized = {c.lower() for c in existing_raw}
    existing_set = set(existing_raw)

    to_add = [
        c for c in new_contracts
        if c.strip().lstrip("- ").lower() not in existing_normalized
        and not _is_semantic_duplicate(c, existing_set)
    ]
    all_conflicts: list[str] = []
    for c in to_add:
        all_conflicts.extend(_conflict_check(c, existing_set))

    if not to_add:
        return {"added": 0, "conflicts": all_conflicts}

    with open(contracts_file, "a") as f:
        if not contracts_file.read_text().strip() if contracts_file.exists() else True:
            f.write(f"# Working contracts: {slug}\n\n")
        for c in to_add:
            f.write(f"- {c}\n")

    return {"added": len(to_add), "conflicts": all_conflicts}
