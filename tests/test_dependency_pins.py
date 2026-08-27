"""Guards dependency specs that would break the servers on a fresh build.

`mcp>=1.0.0` resolved to mcp 2.x, which renames FastMCP to MCPServer and drops
`mcp.server.fastmcp` entirely. server.py imports that module, so the next Docker
rebuild would have failed to start both servers. CI surfaced it first because CI
installs fresh; the running containers kept working on an already-resolved 1.28.1.

The general rule this encodes: a dependency whose major version bump renames the
API the code imports must carry an upper bound. An unpinned lower bound is a
time bomb that goes off on the next clean install, not on the commit that added it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_REQ_FILES = sorted(_REPO.glob("servers/*/requirements.txt"))


def _spec_for(path: Path, package: str) -> str | None:
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if re.match(rf"^{re.escape(package)}\b", line):
            return line
    return None


class TestRequirementsFilesExist:
    def test_found_requirements_files(self):
        """Guards against the tests below passing vacuously on an empty glob."""
        assert _REQ_FILES, "no servers/*/requirements.txt found"


class TestMcpIsPinnedBelow2:
    @pytest.mark.parametrize("req", _REQ_FILES, ids=lambda p: p.parent.name)
    def test_mcp_has_an_upper_bound(self, req):
        spec = _spec_for(req, "mcp")
        if spec is None:
            pytest.skip(f"{req} does not depend on mcp")
        assert "<2" in spec.replace(" ", ""), (
            f"{req} specifies {spec!r} with no upper bound. mcp 2.x renames FastMCP to "
            "MCPServer and removes mcp.server.fastmcp, which server.py imports, so a "
            "fresh install would fail to start the server."
        )

    def test_both_servers_agree_on_the_mcp_spec(self):
        """A version skew between the two servers is its own failure mode."""
        specs = {r.parent.name: _spec_for(r, "mcp") for r in _REQ_FILES}
        present = {k: v for k, v in specs.items() if v}
        assert len(set(present.values())) <= 1, f"mcp spec differs across servers: {present}"


class TestCiInstallsTheSamePin:
    def test_ci_pins_mcp_below_2(self):
        """CI resolving a different major than the servers is how this bug reached main."""
        ci = _REPO / ".github" / "workflows" / "ci.yml"
        if not ci.exists():
            pytest.skip("no CI workflow")
        text = ci.read_text()
        if "mcp" not in text:
            pytest.skip("CI does not install mcp")
        mcp_specs = re.findall(r'"(mcp[^"]*)"', text)
        assert mcp_specs, "mcp referenced in CI but not as a quoted version spec"
        for spec in mcp_specs:
            assert "<2" in spec.replace(" ", ""), (
                f"CI installs {spec!r} with no upper bound, so it can resolve mcp 2.x "
                "while the servers run 1.x"
            )
