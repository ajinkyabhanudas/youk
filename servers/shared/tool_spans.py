"""Server-side spans: record what only the server knows, from one wrapper at tool registration.

Hooks see every call from the outside and own the call counts. The server sees what hooks
cannot: how long the tool itself took, whether it raised, whether a gate blocked, and which
task a gate belongs to. So events written here carry src="server", and a report that counts
calls takes them from the hooks (src="hook") and takes latency and errors from here.

install_tool_spans(mcp, ...) replaces mcp.tool with a version that wraps each registered
function. No per-tool edits: a tool added tomorrow is covered without anyone remembering to.

Never changes a tool's behaviour: the result and any exception pass through untouched, and an
emit failure is swallowed. functools.wraps keeps the signature and docstring FastMCP reads to
build the tool schema.
"""
from __future__ import annotations

import functools
import inspect
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from arms import current_arm
from events import emit

# check_*_gate tools return {"blocked": bool}; the gate name is the event name.
GATE_CHECKS = {
    "check_nfr_gate": "nfr",
    "check_challenge_gate": "challenge",
    "check_intake_gate": "intake",
    "check_task_contract_gate": "task_contract",
    "check_proposal_backlog_gate": "proposal_backlog",
}
_SAFE = re.compile(r"^[A-Za-z0-9_.-]{1,16}$")


def _status(result) -> str:
    if isinstance(result, dict):
        if result.get("blocked") is True:
            return "block"
        if result.get("error") or result.get("error_type"):
            return "fail"
    return "ok"


def _token(value) -> str:
    """A value usable inside an event name, or "" if it is not a short identifier."""
    text = str(value) if value is not None else ""
    return text if _SAFE.match(text) else ""


def _extra_events(name: str, args: dict, result, status: str) -> list[dict]:
    """Gate and lifecycle events implied by a call. Names and numbers only."""
    if name in GATE_CHECKS:
        return [{"kind": "gate", "name": GATE_CHECKS[name], "status": status}]
    if name == "set_gate":
        gate = _token(args.get("gate_name"))
        if gate:
            return [{"kind": "gate", "name": f"set.{gate}", "n": 1 if args.get("value") else 0,
                     "task": str(args.get("task_id", ""))}]
    if name == "mark_task_done":
        return [{"kind": "outcome", "name": "task_done", "status": status,
                 "task": str(args.get("task_id", ""))}]
    if name == "route_task" and isinstance(result, dict):
        size = _token(result.get("size"))
        if size:
            return [{"kind": "gate", "name": f"route.{size}", "status": status}]
    if name == "task_checkpoint":
        size = _token(args.get("size"))
        if size:
            return [{"kind": "outcome", "name": f"checkpoint.{size}"}]
    if name == "session_end":
        return [{"kind": "outcome", "name": "session_end", "status": status}]
    return []


def _session_id(root: Path, slug: str) -> str:
    try:
        counter = json.loads((Path(root) / "state" / "session.json").read_text()).get(
            "session_counter", "")
        return f"{slug}-{counter}" if counter != "" else slug
    except Exception:
        return slug


def default_slug(root: Path) -> str:
    try:
        return json.loads((Path(root) / "state" / "session-open.json").read_text()).get(
            "slug", "unknown") or "unknown"
    except Exception:
        return "unknown"


def _record(root: Path, slug: str, name: str, args: dict, result, status: str, ms: int,
            src: str) -> None:
    try:
        session = _session_id(root, slug)
        arm = current_arm(root, slug)
        emit(root, slug, kind="tool", name=name, status=status, ms=ms, src=src, session=session,
             arm=arm)
        for extra in _extra_events(name, args, result, status):
            emit(root, slug, src=src, session=session, arm=arm, **extra)
    except Exception:
        pass


def wrap_tool(fn: Callable, get_root: Callable[[], Path], get_slug: Callable[[], str],
              src: str = "server") -> Callable:
    """The traced version of one tool function."""
    sig = inspect.signature(fn)
    name = fn.__name__

    def _args(call_args, call_kwargs) -> dict:
        try:
            bound = sig.bind_partial(*call_args, **call_kwargs)
            return dict(bound.arguments)
        except TypeError:
            return {}

    @functools.wraps(fn)
    def traced(*call_args, **call_kwargs):
        start = time.perf_counter()
        result, status = None, "ok"
        try:
            result = fn(*call_args, **call_kwargs)
            status = _status(result)
            return result
        except BaseException:
            status = "fail"
            raise
        finally:
            try:
                root = get_root()
                slug = get_slug() or "unknown"
                ms = int((time.perf_counter() - start) * 1000)
                _record(root, slug, name, _args(call_args, call_kwargs), result, status, ms, src)
            except Exception:
                pass

    traced.__youk_span__ = True
    return traced


def install_tool_spans(mcp, get_root: Callable[[], Path],
                       get_slug: Callable[[], str] | None = None, src: str = "server") -> None:
    """Make every later `@mcp.tool()` registration traced. Call once, right after the server
    object is created and before any tool is registered."""
    original = mcp.tool
    slug_getter = get_slug or (lambda: default_slug(get_root()))

    def tool(*targs, **tkwargs):
        if targs and callable(targs[0]) and not tkwargs:  # bare @mcp.tool
            return original()(wrap_tool(targs[0], get_root, slug_getter, src))
        register = original(*targs, **tkwargs)

        def decorate(fn):
            return register(wrap_tool(fn, get_root, slug_getter, src))

        return decorate

    mcp.tool = tool
