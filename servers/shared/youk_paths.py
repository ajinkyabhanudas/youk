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


def resolve_audit_dir(host_root: Path, youk_root: Path) -> Path:
    """Legacy location if it already exists, otherwise youk's own."""
    legacy = host_root / "audit"
    return legacy if legacy.exists() else youk_root / "audit"


def read_path_map(youk_root: Path) -> dict[str, str]:
    """state/path-map.env, written by the installer. Missing or unreadable means an install
    that predates it, which callers treat as the legacy layout."""
    try:
        lines = (youk_root / "state" / "path-map.env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    pairs = (ln.split("=", 1) for ln in lines if "=" in ln and not ln.lstrip().startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def resolve_skills_dir(host_root: Path, youk_root: Path) -> Path:
    """Where skills are read from.

    The installer records whether it linked youk's skills into the host dir
    (HOST_SKILLS_LINKED). When it says no, the host dir may hold some other tool's skills, so
    youk's own tree is used regardless of what is there. Without the key (every install made
    before it existed, all on Claude Code) the host's skills dir is used when it exists."""
    if read_path_map(youk_root).get("HOST_SKILLS_LINKED") == "0":
        return youk_root / "skills"
    linked = host_root / "skills"
    return linked if linked.exists() else youk_root / "skills"


def locate_install(script_file: str | Path) -> tuple[Path, Path, Path]:
    """For scripts that run on the host, outside the containers: (youk_dir, host_dir, audit_dir).

    youk_dir is YOUK_HOME if set, otherwise the repo the script sits in. host_dir is what the
    installer recorded in state/path-map.env, otherwise the Claude Code dir that installs
    made before host-neutral paths always used."""
    env_home = os.environ.get("YOUK_HOME")
    youk_dir = Path(env_home) if env_home else Path(script_file).resolve().parent.parent
    mapped = read_path_map(youk_dir).get("HOST_CONFIG_DIR")
    host_dir = Path(mapped) if mapped else Path.home() / ".claude"
    return youk_dir, host_dir, resolve_audit_dir(host_dir, youk_dir)


def instruction_files(root: Path) -> list[Path]:
    """The project-instruction files that exist directly under `root` (a host config dir or a
    project directory), for every host youk knows, in a stable order."""
    return [root / name for name in sorted(set(INSTRUCTIONS_FILES.values())) if (root / name).exists()]
