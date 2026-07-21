"""L0 — Environment checks. No Docker, no MCP, pure toolchain."""
import shutil
import sys
from pathlib import Path

import pytest

YOUK_DIR = Path.home() / ".claude" / "youk"


def test_python_version():
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"


def test_docker_cli_present():
    assert shutil.which("docker") is not None, (
        "docker CLI not found. Fix: install Docker Desktop"
    )


def test_pyyaml_importable():
    import yaml  # noqa: F401


def test_pytest_importable():
    import pytest  # noqa: F401


def test_models_importable():
    """servers/shared/models.py must be importable — confirms sys.path is wired."""
    from models import TaskSize  # noqa: F401
    assert TaskSize.XS is not None


def test_youk_root_structure():
    for subdir in ["state", "config", "knowledge", "skills"]:
        p = YOUK_DIR / subdir
        assert p.exists(), f"YOUK_ROOT/{subdir} missing — YOUK_ROOT misconfigured"
