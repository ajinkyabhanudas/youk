"""Langfuse instrumentation for youk-core.

Maintainer tooling, not a youk feature. No-op unless LANGFUSE_HOST /
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are all set, so a normal install never
reaches Langfuse and never needs the stack. Setup lives in CONTRIBUTING.md.

One trace per run (session_start to session_end). Repairs and health checks are spans.

TRACE CONTENT INVARIANT (see docs/adr-011-trace-content-invariant.md):

    Traces carry derived scalars and enums. Never free text from the session.

Counts, rates, durations, enum outcomes and hashed identifiers are allowed. Task
descriptions, file paths, project names, finding text and prompts are not. This is
what keeps a shared team instance a config change rather than a redesign: pointing
LANGFUSE_HOST at a shared host must never start leaking session content. Adding
identifying fields later would be a privacy regression that cannot be retrofitted
away, because the data is already on the server.

`_ALLOWED_METADATA_KEYS` enforces the invariant and is covered by a drift sentinel
in tests/test_observability_privacy.py.

Usage:
    obs = get_obs()          # singleton, returns NoOpObs if env absent
    trace = obs.start_run(session_slug, project_dir)
    with obs.span(trace, "health-check"):
        ...
    obs.attach_score(trace, "patch_cycle_rate", 0.12)
    obs.end_run(trace, outcome="SHIPPED")
"""
from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Every key a trace is permitted to carry. Adding one is a deliberate act: it must
# be a derived scalar or enum, never free text from the session. See the module
# docstring and ADR-011.
_ALLOWED_METADATA_KEYS = frozenset({
    "session_slug_hash",   # sha256[:16] of the project slug, not the slug
    "install_id",          # anonymous, generated locally, never from user identity
    "youk_version",        # release string, for per-version comparison
})


def _langfuse_available() -> bool:
    return all(
        os.environ.get(k)
        for k in ("LANGFUSE_HOST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    )


def hash_identifier(value: str) -> str:
    """Stable, non-reversible id for grouping. Keeps grouping power, drops identity.

    Used for the project slug and anywhere else a raw name would otherwise reach a
    trace. Truncated to 16 hex chars: collisions are irrelevant for grouping, and a
    shorter value is less tempting to treat as a lookup key back to the original.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def get_install_id(youk_root: Path) -> str:
    """Anonymous per-install id, generated once and cached in state/install-id.

    Never derived from username, email, hostname or path. Without a stable grouping
    key a shared instance cannot tell ten developers apart from one developer with
    ten times the sessions, and that distinction cannot be reconstructed after the
    fact. Generating it now is what keeps team aggregation a later config change.

    Returns "unknown" rather than raising if state is unwritable. Observability must
    never be able to fail a session.
    """
    id_file = youk_root / "state" / "install-id"
    try:
        if id_file.exists():
            existing = id_file.read_text().strip()
            if existing:
                return existing
        new_id = uuid.uuid4().hex
        id_file.parent.mkdir(parents=True, exist_ok=True)
        id_file.write_text(new_id)
        return new_id
    except Exception:
        return "unknown"


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

    @contextmanager
    def span_by_id(self, trace_id: str, name: str, **metadata):
        yield None

    def record_generation(self, trace_id: str, name: str, model: str,
                          input_tokens: int, output_tokens: int, duration_s: float) -> None:
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
        """Start the run trace.

        project_dir is deliberately NOT sent. It is an absolute path containing the
        user's home directory name, so it identifies both the person and their
        filesystem layout. The slug is hashed for the same reason: it is a project
        name. Both arguments are kept in the signature because callers pass them and
        the hashing is this function's job, not the caller's.
        """
        return self._lf.trace(
            name="youk-run",
            metadata=build_trace_metadata(session_slug),
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

    @contextmanager
    def span_by_id(self, trace_id: str, name: str, **metadata):
        """Time one stage and attach it to an existing trace as a span.

        Takes a trace_id rather than a trace object so callers can open a span from
        anywhere in the run without threading the object through every signature,
        which is what kept spans unimplemented until now.

        Span metadata is trace content, so ADR-011 applies here exactly as it does to
        trace metadata. Values are scrubbed to numbers only. `name` is a literal in
        the calling code, never user data. Never raises: observability must not be
        able to fail the stage it is measuring.
        """
        import time as _time
        from datetime import datetime as _dt
        start = _dt.now()
        t0 = _time.monotonic()
        try:
            yield
        finally:
            try:
                payload = _numeric_only(metadata)
                payload["duration_s"] = round(_time.monotonic() - t0, 3)
                self._lf.span(
                    trace_id=trace_id, name=name,
                    start_time=start, end_time=_dt.now(),
                    metadata=payload,
                )
            except Exception:
                pass

    def record_generation(self, trace_id: str, name: str, model: str,
                          input_tokens: int, output_tokens: int, duration_s: float) -> None:
        """Record a model call: model name, token counts, latency. Cost is derived.

        Cost is deliberately NOT computed here. Langfuse derives it from the model name
        and usage against its own pricing table, so prices stay correct without a
        hardcoded table in this repo drifting out of date.

        Prompt and completion text are deliberately NOT recorded. Langfuse generations
        normally carry both, and here the prompt contains the user's raw task
        description. ADR-011 forbids free session text on a trace, and this is the most
        tempting place to break it. Model name is a literal in the calling code, not
        user data. Never raises.
        """
        try:
            self._lf.generation(
                trace_id=trace_id,
                name=name,
                model=model,
                usage={"input": input_tokens, "output": output_tokens, "unit": "TOKENS"},
                metadata={"duration_s": round(duration_s, 3)},
            )
        except Exception:
            pass

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


def _numeric_only(metadata: dict) -> dict:
    """Drop everything that is not a number.

    Span metadata is trace content, so ADR-011 applies. Free text is the vector that
    leaks session detail, and a stage measurement never legitimately needs it: counts,
    sizes and durations are numbers. Booleans are excluded too, since bool is an int
    subclass in Python and a stray flag reads as 0/1 noise rather than a measurement.
    """
    return {
        k: v for k, v in metadata.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def build_trace_metadata(session_slug: str, youk_root: Path | None = None) -> dict:
    """Build trace metadata carrying only derived, non-identifying values.

    The single place trace metadata is constructed, so the allowlist has one thing to
    guard. Anything not in _ALLOWED_METADATA_KEYS is dropped rather than sent, because
    a leak here is unrecoverable once it reaches a shared server.
    """
    if youk_root is None:
        youk_root = Path(os.environ.get("YOUK_ROOT", "/youk"))
    meta = {
        "session_slug_hash": hash_identifier(session_slug),
        "install_id": get_install_id(youk_root),
        "youk_version": os.environ.get("YOUK_VERSION", "unknown"),
    }
    return {k: v for k, v in meta.items() if k in _ALLOWED_METADATA_KEYS}
