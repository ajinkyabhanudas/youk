"""Every module-level path must be redirectable at call time.

Two patterns make a path unreachable by any patch, and both shipped:

    _REGISTRY_FILE = Path("/youk/state/...")     # hardcoded, ignores YOUK_ROOT
    def f(path: Path = _REGISTRY_FILE)           # default bound at def time

The second is the subtle one. Patching the module constant afterwards does nothing,
because the default was captured when the function was defined. 22 of those existed
across revisable_sets, behavioral_profile, skill_signals and steering_vocab, which is
why contract tests kept writing into live state after two rounds of "fixing" the roots.

These tests fail if either pattern comes back.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SRC_DIRS = [
    Path(__file__).parent.parent / "servers" / "core" / "src",
    Path(__file__).parent.parent / "servers" / "code" / "src",
    Path(__file__).parent.parent / "servers" / "shared",
]
_PY_FILES = sorted(p for d in _SRC_DIRS if d.exists() for p in d.glob("*.py"))

# The root constants themselves are legitimately absolute; everything else derives.
# The underscore forms are local shadows of the same constants.
_ALLOWED_ABSOLUTE = {"YOUK_ROOT", "CLAUDE_ROOT", "_YOUK_ROOT", "_CLAUDE_ROOT"}


def _is_env_fallback(node: ast.AST, literal: ast.Constant) -> bool:
    """True when the literal is the default arg of os.environ.get / os.getenv.

    `Path(os.environ.get("YOUK_ROOT", "/youk"))` is already redirectable: the env var
    overrides it. Flagging it would push people toward worse code to satisfy a linter.
    """
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call) or len(sub.args) < 2:
            continue
        func = sub.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name in {"get", "getenv"} and any(a is literal for a in sub.args[1:]):
            return True
    return False


def test_source_files_were_found():
    """Guards the sweeps below against passing vacuously on an empty glob."""
    assert _PY_FILES, "no server source files found"


def _is_path_annotated(arg: ast.arg) -> bool:
    """Only Path parameters matter here.

    `n: int = _COMMIT_LOOKBACK` is a tuning constant and binding it at def time is
    correct: nothing needs to redirect an integer. Flagging it would force pointless
    None-resolution boilerplate into every function with a numeric knob.
    """
    return arg.annotation is not None and "Path" in ast.unparse(arg.annotation)


@pytest.mark.parametrize("py", _PY_FILES, ids=lambda p: p.name)
def test_no_def_time_path_defaults(py):
    """A Path default in a signature is captured at def time and cannot be patched."""
    tree = ast.parse(py.read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = node.args.args[len(node.args.args) - len(node.args.defaults):]
        for arg, default in list(zip(positional, node.args.defaults)) + list(
            zip(node.args.kwonlyargs, node.args.kw_defaults)
        ):
            if (
                isinstance(default, ast.Name)
                and re.fullmatch(r"_[A-Z_]+", default.id)
                and _is_path_annotated(arg)
            ):
                offenders.append(f"{node.name}({arg.arg}={default.id})")
    assert offenders == [], (
        f"{py.name} binds module constants as defaults: {offenders}. "
        "Use `param: Path | None = None` and resolve inside the body, so the current "
        "module global is read at call time and the path stays redirectable."
    )


@pytest.mark.parametrize("py", _PY_FILES, ids=lambda p: p.name)
def test_no_hardcoded_root_paths(py):
    """Only YOUK_ROOT / CLAUDE_ROOT may spell an absolute root; the rest derive."""
    tree = ast.parse(py.read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        # A name ending in _root IS the root definition, which is the one place an
        # absolute path belongs. That covers probe candidates too: contract_verifier
        # sets _docker_root = Path("/claude") and only uses it if it exists, falling
        # back to an env var or ~/.claude. Flagging that would push it toward worse code.
        if any(n in _ALLOWED_ABSOLUTE or n.lower().endswith("_root") for n in names):
            continue
        for sub in ast.walk(node.value):
            if (
                isinstance(sub, ast.Constant)
                and isinstance(sub.value, str)
                and sub.value.startswith(("/youk", "/claude"))
                and not _is_env_fallback(node, sub)
            ):
                offenders.append(f"{names or '<expr>'} = ...{sub.value!r}")
    assert offenders == [], (
        f"{py.name} hardcodes an absolute root: {offenders}. "
        "Derive from YOUK_ROOT / CLAUDE_ROOT so tests and alternate installs can "
        "redirect it."
    )


class TestRedirectionActuallyWorks:
    """Behavioural proof, not just a static sweep."""

    def test_patching_the_constant_reaches_the_function(self, tmp_path, monkeypatch):
        import revisable_sets as rs

        target = tmp_path / "registry.json"
        monkeypatch.setattr(rs, "_REGISTRY_FILE", target)
        rs._save_registry({})
        assert target.exists(), "write did not follow the patched constant"

    def test_explicit_path_argument_still_wins(self, tmp_path):
        import revisable_sets as rs

        explicit = tmp_path / "explicit.json"
        rs._save_registry({}, path=explicit)
        assert explicit.exists(), "explicit path argument was ignored"

    def test_pre_fix_binding_would_not_have_followed_the_patch(self, tmp_path):
        """Bar 7: prove this catches the old shape rather than only passing."""
        original = tmp_path / "original.json"

        def old_style(path: Path = original) -> Path:  # default bound now
            return path

        redirected = tmp_path / "redirected.json"
        original = redirected  # noqa: F841 — rebinding the name, as monkeypatch would
        assert old_style() != redirected, "def-time default unexpectedly followed rebinding"


class TestImportsHaveNoWriteSideEffects:
    """Importing a module must not write to disk.

    server.py seeded a judgment-set at module scope, so every import wrote to
    state/revisable-sets.json. Found via sys.addaudithook after four failed attempts
    with Python-level patches, which could not see the C-level open.

    Two costs. Any importer mutates state: tests, linters, doc tooling. And it defeats
    test isolation, because the write happens during the fixture's own import, before
    the fixture can redirect anything.
    """

    def test_no_module_scope_call_to_a_known_writer(self):
        """Static guard. Catches the shape without needing to execute an import."""
        import ast

        writers = {"_rs_enroll", "enroll", "_save_registry", "save_contract"}

        def _module_scope_stmts(body: list[ast.stmt]) -> list[ast.stmt]:
            """Statements that execute on import.

            Excludes function and class bodies, which only run when called. Excludes
            `if __name__ == "__main__":`, which runs on execution but not on import —
            that is exactly where a startup side effect belongs. Descends into try
            and plain if blocks, since those do execute at import time.
            """
            out: list[ast.stmt] = []
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
                    continue
                if isinstance(node, (ast.Try, ast.If)):
                    out.extend(_module_scope_stmts(node.body))
                    out.extend(_module_scope_stmts(getattr(node, "orelse", [])))
                    continue
                out.append(node)
            return out

        offenders = []
        for py in _PY_FILES:
            tree = ast.parse(py.read_text())
            for stmt in _module_scope_stmts(tree.body):
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call):
                        name = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                        if name in writers:
                            offenders.append(f"{py.name}: {name}() at module scope")
        assert offenders == [], (
            f"module-scope writes: {offenders}. Move into a function called from "
            "__main__ so importing the module stays free of side effects."
        )
