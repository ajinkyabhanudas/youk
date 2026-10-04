"""Where youk's runtime files live, resolved in one place and independent of agent host.

Inside the containers there are two mounts: /youk (youk's own install and state) and the
*host config root* (the agent host's config directory, when there is one). youk needs three
things from the host root, and nothing host-specific beyond that:

  audit logs   youk's own session history. Lives in the host root only on installs made
               before host-neutral paths existed; new installs keep it under /youk/audit.
  skills       the SKILL.md tree youk serves. A host that discovers skills from its own
               directory (Claude Code) has them linked there; every other host reads them
               from /youk/skills. Either way the same files are served over MCP.
  instructions the host's project-instructions file name, see INSTRUCTIONS_FILES.

Existing installs keep working unchanged: where the legacy location already exists it wins.
"""
from __future__ import annotations

import os
from pathlib import Path

YOUK_ROOT = Path(os.environ.get("YOUK_ROOT", "/youk"))

def resolve_host_root() -> Path:
    """The host config dir as mounted into the container.

    "/host" is what current installs mount; "/claude" is what installs made before
    host-neutral paths mounted. Both are honoured so an upgrade does not depend on every
    installer script having been re-run. YOUK_HOST_ROOT overrides both."""
    env = os.environ.get("YOUK_HOST_ROOT")
    if env:
        return Path(env)
    for candidate in ("/host", "/claude"):
        if Path(candidate).exists():
            return Path(candidate)
    return Path("/host")


HOST_ROOT = resolve_host_root()

# The file a host reads project instructions from. A host not listed has none that youk knows.
INSTRUCTIONS_FILES = {"claude-code": "CLAUDE.md", "codex": "AGENTS.md"}


def audit_dir(host_root: Path, youk_root: Path) -> Path:
    """Legacy location if it already exists, otherwise youk's own."""
    legacy = host_root / "audit"
    return legacy if legacy.exists() else youk_root / "audit"


def skills_dir(host_root: Path, youk_root: Path) -> Path:
    """The host's linked skills dir if it exists, otherwise the skills in youk's own tree."""
    linked = host_root / "skills"
    return linked if linked.exists() else youk_root / "skills"
