"""Project research uses the provider-neutral inference seam."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent / "scripts" / "project-research.py"
_SPEC = importlib.util.spec_from_file_location("project_research", _SCRIPT)
assert _SPEC and _SPEC.loader
project_research = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(project_research)

from inference import GenerationResult, InferenceCapability, InferenceStatus


class _Provider:
    capability = InferenceCapability("test", "model", InferenceStatus.AVAILABLE, "configured")

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def generate(self, system: str, user: str, max_tokens: int) -> GenerationResult:
        self.calls.append((system, user, max_tokens))
        return GenerationResult("## Finding\nUse the shared adapter.")


def test_research_uses_the_configured_provider_adapter(tmp_path, monkeypatch):
    youk_dir = tmp_path / "youk"
    (youk_dir / "knowledge" / "projects" / "demo").mkdir(parents=True)
    (youk_dir / "knowledge" / "projects" / "demo" / "context.md").write_text("project-type: python\n")
    provider = _Provider()
    monkeypatch.setattr(project_research, "_provider", lambda _: provider)

    assert project_research.run_research("demo", youk_dir) is True
    assert provider.calls and provider.calls[0][2] == 1200
    output = youk_dir / "knowledge" / "projects" / "demo" / "research-inbox"
    assert "Use the shared adapter." in next(output.glob("*-research.md")).read_text()


def test_research_skips_when_the_provider_is_unavailable(tmp_path, monkeypatch, capsys):
    provider = _Provider()
    provider.capability = InferenceCapability("test", "model", InferenceStatus.UNAVAILABLE, "credential is not configured")
    monkeypatch.setattr(project_research, "_provider", lambda _: provider)

    assert project_research.run_research("demo", tmp_path) is False
    assert "inference unavailable" in capsys.readouterr().err
