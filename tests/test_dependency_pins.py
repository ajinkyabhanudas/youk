"""Guards dependency specs that would break the servers on a fresh build.

`mcp>=1.0.0` resolved to mcp 2.x, which renames FastMCP to MCPServer and drops
`mcp.server.fastmcp` entirely. server.py imports that module, so the next Docker
rebuild would have failed to start both servers. CI surfaced it first because CI
installs fresh; the running containers kept working on an already-resolved 1.28.1.

The general rule this encodes: a dependency whose major version bump renames the
API the code imports must carry an upper bound. An unpinned lower bound is a
time bomb that goes off on the next clean install, not on the commit that added it.

Dependencies now live in pyproject.toml and are pinned by uv.lock, which every entry
point installs from, so the guard checks both the spec and the resolved version.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent


def _load(name: str) -> dict:
    return tomllib.loads((_REPO / name).read_text())


def _mcp_spec() -> str | None:
    for dep in _load("pyproject.toml")["project"]["dependencies"]:
        if dep.replace(" ", "").startswith("mcp") and not dep.startswith("mcp-"):
            return dep
    return None


class TestMcpIsPinnedBelow2:
    def test_pyproject_mcp_has_an_upper_bound(self):
        spec = _mcp_spec()
        assert spec is not None, "pyproject.toml no longer depends on mcp"
        assert "<2" in spec.replace(" ", ""), (
            f"pyproject.toml specifies {spec!r} with no upper bound. mcp 2.x renames "
            "FastMCP to MCPServer and removes mcp.server.fastmcp, which server.py imports, "
            "so a fresh install would fail to start the server."
        )

    def test_lockfile_resolves_mcp_1(self):
        locked = [p for p in _load("uv.lock")["package"] if p["name"] == "mcp"]
        assert locked, "uv.lock has no mcp entry"
        assert all(p["version"].startswith("1.") for p in locked), (
            f"uv.lock resolves mcp to {[p['version'] for p in locked]}; the servers need 1.x"
        )


class TestEntryPointsInstallFromTheLock:
    def test_no_requirements_files_remain(self):
        """Two sources of truth is how the local env and CI drifted apart."""
        assert not list(_REPO.glob("servers/*/requirements.txt"))

    def test_ci_installs_from_the_lock(self):
        ci = _REPO / ".github" / "workflows" / "ci.yml"
        if not ci.exists():
            pytest.skip("no CI workflow")
        text = ci.read_text()
        assert "uv sync --frozen" in text
        assert "pip install" not in text.replace("pip install pyyaml", ""), (
            "CI installs packages outside the lock"
        )

    @pytest.mark.parametrize("name", ["core", "code"])
    def test_dockerfiles_install_from_the_lock(self, name):
        text = (_REPO / "servers" / name / "Dockerfile").read_text()
        assert "uv sync --frozen" in text
        assert "pip install" not in text
