"""Detect drift between the repo skills tree and the runtime skills tree.

install.sh symlinks every directory in YOUK_ROOT/skills into CLAUDE_ROOT/skills, but
it only runs at install time. A skill added to the repo afterwards has no symlink, so
route_to_skill cannot load it even though it is committed and looks present to anyone
reading the repo. Nothing surfaced this, and it is how CLAUDE.md ended up routing to
`intake` and `coverage-tree` when neither was reachable at runtime.

Two directions of drift, both worth reporting and only one worth alarming about:

unlinked  - in the repo, absent from runtime. Routes to it fail. This is the real bug.
orphaned  - a real directory in runtime with no repo counterpart. install.sh skips real
            directories rather than replacing them, so it survives reinstall. What it
            does not survive is losing the machine: it is not version controlled and
            does not ship to anyone else.

Read-only. Reports drift, never repairs it, because creating symlinks is install.sh's
job and doing it from a health check would hide the fact that install is stale.
"""
from __future__ import annotations

from pathlib import Path


def _skill_dirs(root: Path) -> set[str]:
    """Skill directory names only.

    install.sh also symlinks top-level files (SKILL-REGISTRY.md, FOUNDER-GUIDE.md,
    stack-overlay-schema.md). Those are not skills, and counting them reports
    documentation as drift. A skill is an extensionless directory, so entries with a
    suffix are excluded. Symlinks are counted without resolving, because a dangling
    symlink is a different failure than a missing one and must not read as unlinked.
    """
    if not root.exists():
        return set()
    return {
        d.name for d in root.iterdir()
        if (d.is_dir() or d.is_symlink())
        and not d.name.startswith(".")
        and not d.suffix
    }


def check_skill_links(youk_root: Path, claude_root: Path) -> dict:
    """Compare repo skills against runtime skills.

    Returns {unlinked, orphaned, repo_count, runtime_count, healthy, message}.
    Never raises: a health check must not be able to fail a session.
    """
    try:
        repo_dir = youk_root / "skills"
        runtime_dir = claude_root / "skills"

        # No runtime tree means youk is running directly from the repo, which is a
        # valid dev setup rather than drift.
        if not runtime_dir.exists() or not repo_dir.exists():
            return {
                "unlinked": [], "orphaned": [],
                "repo_count": len(_skill_dirs(repo_dir)),
                "runtime_count": len(_skill_dirs(runtime_dir)),
                "healthy": True,
                "message": "",
            }

        repo = _skill_dirs(repo_dir)
        runtime = _skill_dirs(runtime_dir)
        unlinked = sorted(repo - runtime)
        orphaned = sorted(runtime - repo)

        parts = []
        if unlinked:
            parts.append(
                f"{len(unlinked)} repo skill(s) not reachable at runtime "
                f"({', '.join(unlinked)}) — routes to them fail. Run scripts/install.sh."
            )
        if orphaned:
            parts.append(
                f"{len(orphaned)} runtime skill(s) not in the repo "
                f"({', '.join(orphaned)}) — not version controlled and not shipped; "
                "they survive reinstall but not machine loss."
            )

        return {
            "unlinked": unlinked,
            "orphaned": orphaned,
            "repo_count": len(repo),
            "runtime_count": len(runtime),
            "healthy": not unlinked,   # orphans are untidy, unlinked skills are broken
            "message": " ".join(parts),
        }
    except Exception:
        return {
            "unlinked": [], "orphaned": [], "repo_count": 0, "runtime_count": 0,
            "healthy": True, "message": "",
        }
