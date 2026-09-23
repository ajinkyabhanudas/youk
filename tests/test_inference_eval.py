from dataclasses import dataclass

from inference import (
    InferenceCapability,
    InferenceStatus,
    ProviderConfiguration,
    evaluate_provider,
    load_configuration,
    rollback_configuration,
    save_configuration,
)


@dataclass
class FakeProvider:
    capability: InferenceCapability

    def generate(self, system: str, user: str, max_tokens: int) -> object:
        raise AssertionError("conformance evaluation must not make a network call")


def test_provider_substitution_eval_accepts_compatible_adapter():
    provider = FakeProvider(InferenceCapability("test-provider", "test-v1", InferenceStatus.AVAILABLE, "fixture"))
    assert evaluate_provider(provider, InferenceStatus.AVAILABLE).passed


def test_api_down_eval_requires_explicit_degraded_state():
    provider = FakeProvider(InferenceCapability("test-provider", "test-v1", InferenceStatus.UNAVAILABLE, "fixture outage"))
    result = evaluate_provider(provider, InferenceStatus.UNAVAILABLE)
    assert result.passed
    assert result.actual_status is InferenceStatus.UNAVAILABLE


def test_incompatible_provider_cannot_pass_available_eval():
    provider = FakeProvider(InferenceCapability("future-provider", "", InferenceStatus.INCOMPATIBLE, "adapter missing"))
    assert not evaluate_provider(provider, InferenceStatus.AVAILABLE).passed


def test_configuration_rollback_restores_the_exact_previous_provider(tmp_path):
    path = tmp_path / "provider.json"
    original = ProviderConfiguration("provider-a", "model-a")
    replacement = ProviderConfiguration("provider-b", "model-b")
    assert save_configuration(path, original) is None
    previous = save_configuration(path, replacement)
    assert previous == original
    rollback_configuration(path, previous)
    assert load_configuration(path) == original


def test_selection_uses_persisted_configuration_over_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / "provider.json"
    save_configuration(path, ProviderConfiguration("future-provider", "model-x"))
    from inference import select_intent_provider

    selected = select_intent_provider(config_path=path)
    assert selected.capability.provider_id == "future-provider"
    assert selected.capability.status is InferenceStatus.INCOMPATIBLE
