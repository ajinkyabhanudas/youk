"""Provider-neutral inference boundary for youk's optional reasoning features."""
from __future__ import annotations

import os
import hashlib
import json
from datetime import UTC, datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from pathlib import Path


class InferenceStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True)
class InferenceCapability:
    provider_id: str
    model: str
    status: InferenceStatus
    reason: str


class IntentProvider(Protocol):
    capability: InferenceCapability

    def generate(self, system: str, user: str, max_tokens: int) -> object: ...


@dataclass(frozen=True)
class ProviderEval:
    provider_id: str
    expected_status: InferenceStatus
    actual_status: InferenceStatus
    passed: bool


@dataclass(frozen=True)
class ProviderConfiguration:
    provider_id: str
    model: str
    schema_version: int = 1


def load_configuration(path: Path) -> ProviderConfiguration | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProviderConfiguration(**data)


def save_configuration(path: Path, configuration: ProviderConfiguration) -> ProviderConfiguration | None:
    """Atomically install a credential-free provider configuration and return its predecessor."""
    previous = load_configuration(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_suffix(".tmp")
    staged.write_text(json.dumps(configuration.__dict__, sort_keys=True), encoding="utf-8")
    staged.replace(path)
    return previous


def rollback_configuration(path: Path, previous: ProviderConfiguration) -> None:
    """Restore a configuration captured by save_configuration without provider I/O."""
    save_configuration(path, previous)


def evaluate_provider(provider: IntentProvider, expected: InferenceStatus) -> ProviderEval:
    """Deterministic conformance check; it never calls a provider network API."""
    capability = provider.capability
    return ProviderEval(
        provider_id=capability.provider_id,
        expected_status=expected,
        actual_status=capability.status,
        passed=capability.status is expected,
    )


class AnthropicIntentProvider:
    """The current provider adapter; vendor details stay out of core policy."""

    def __init__(self, model: str | None = None) -> None:
        model = model or os.environ.get("YOUK_INFERENCE_MODEL", "claude-haiku-4-5-20251001")
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            self.capability = InferenceCapability("anthropic", model, InferenceStatus.UNAVAILABLE, "credential is not configured")
            self._client = None
            return
        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=key)
            self.capability = InferenceCapability("anthropic", model, InferenceStatus.AVAILABLE, "configured")
        except Exception:
            self._client = None
            self.capability = InferenceCapability("anthropic", model, InferenceStatus.UNAVAILABLE, "provider client is unavailable")

    def generate(self, system: str, user: str, max_tokens: int) -> object:
        if self._client is None:
            raise RuntimeError(self.capability.reason)
        return self._client.messages.create(model=self.capability.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])


def select_intent_provider(provider_id: str | None = None, config_path: Path | None = None) -> IntentProvider:
    """Select a configured adapter; unknown providers are explicit, never fallback."""
    configuration = load_configuration(config_path) if config_path else None
    selected = provider_id or (configuration.provider_id if configuration else os.environ.get("YOUK_INFERENCE_PROVIDER", "anthropic"))
    model = configuration.model if configuration else None
    if selected == "anthropic":
        return AnthropicIntentProvider(model)
    provider = AnthropicIntentProvider.__new__(AnthropicIntentProvider)
    provider._client = None
    provider.capability = InferenceCapability(selected, "", InferenceStatus.INCOMPATIBLE, "provider adapter is not installed")
    return provider


def record_execution(path: Path, capability: InferenceCapability, request: str, outcome: str) -> dict:
    """Append a privacy-safe execution record; request content is never persisted."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "provider_id": capability.provider_id,
        "model": capability.model,
        "provider_status": capability.status.value,
        "policy_reason": capability.reason,
        "request_sha256": hashlib.sha256(request.encode()).hexdigest(),
        "outcome": outcome,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record
