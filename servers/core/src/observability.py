"""Langfuse instrumentation for youk-core.

No-op when LANGFUSE_HOST / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are absent.
One trace per run (session_start → session_end). Repairs and health checks are spans.

Usage:
    obs = get_obs()          # singleton, returns NoOpObs if env absent
    trace = obs.start_run(session_slug, project_dir)
    with obs.span(trace, "health-check"):
        ...
    obs.attach_score(trace, "patch_cycle_rate", 0.12)
    obs.end_run(trace, outcome="SHIPPED")
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any


def _langfuse_available() -> bool:
    return all(
        os.environ.get(k)
        for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    )


class _NoOpTrace:
    id = "noop"


class NoOpObs:
    def start_run(self, *a, **kw) -> _NoOpTrace:
        return _NoOpTrace()

    @contextmanager
    def span(self, trace: Any, name: str, **kw):
        yield None

    def attach_score(self, trace: Any, name: str, value: float, comment: str = "") -> None:
        pass

    def attach_score_by_id(self, trace_id: str, name: str, value: float, comment: str = "") -> None:
        pass

    def end_run(self, trace: Any, **kw) -> None:
        pass

    def end_run_by_id(self, trace_id: str, **kw) -> None:
        pass

    def flush(self) -> None:
        pass


class LangfuseObs:
    def __init__(self) -> None:
        from langfuse import Langfuse
        self._lf = Langfuse(
            host=os.environ["LANGFUSE_HOST"],
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        )

    def start_run(self, session_slug: str, project_dir: str) -> Any:
        return self._lf.trace(
            name="youk-run",
            metadata={"session_slug": session_slug, "project_dir": project_dir},
            tags=["youk"],
        )

    @contextmanager
    def span(self, trace: Any, name: str, **metadata):
        span = trace.span(name=name, metadata=metadata or None)
        try:
            yield span
        finally:
            span.end()

    def attach_score(self, trace: Any, name: str, value: float, comment: str = "") -> None:
        self._lf.score(
            trace_id=trace.id,
            name=name,
            value=value,
            comment=comment or None,
        )

    def attach_score_by_id(self, trace_id: str, name: str, value: float, comment: str = "") -> None:
        self._lf.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment or None,
        )

    def end_run(self, trace: Any, outcome: str = "NONE", commits_made: bool = False) -> None:
        trace.update(
            output={"outcome": outcome, "commits_made": commits_made},
        )

    def end_run_by_id(self, trace_id: str, outcome: str = "NONE", commits_made: bool = False) -> None:
        self._lf.trace(
            id=trace_id,
            output={"outcome": outcome, "commits_made": commits_made},
        )

    def flush(self) -> None:
        self._lf.flush()


_instance: NoOpObs | LangfuseObs | None = None


def get_obs() -> NoOpObs | LangfuseObs:
    global _instance
    if _instance is None:
        if _langfuse_available():
            try:
                _instance = LangfuseObs()
            except Exception:
                _instance = NoOpObs()
        else:
            _instance = NoOpObs()
    return _instance


def compute_patch_cycle_rate(candidates: list[dict]) -> float | None:
    """Ratio of patch_cycle=True to total candidates. None when candidates is empty."""
    if not candidates:
        return None
    cycling = sum(1 for c in candidates if c.get("patch_cycle"))
    return round(cycling / len(candidates), 3)
