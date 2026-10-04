"""Provider-neutral inference boundary for youk's optional reasoning features."""
from __future__ import annotations

import os
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from pathlib import Path
from urllib.parse import urlparse

from youk_paths import YOUK_ROOT


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


@dataclass(frozen=True)
class GenerationResult:
    """What every provider adapter returns, so callers never touch a vendor's
    response object. Swapping the provider means writing one adapter that
    produces this; nothing downstream changes."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class IntentProvider(Protocol):
    capability: InferenceCapability

    def generate(self, system: str, user: str, max_tokens: int) -> GenerationResult: ...


@dataclass(frozen=True)
class ProviderEval:
    provider_id: str
    expected_status: InferenceStatus
    actual_status: InferenceStatus
    passed: bool


@dataclass(frozen=True)
class ProviderConfiguration:
    """Credential-free: a key never goes in this file (see key_file_path)."""
    provider_id: str
    model: str
    schema_version: int = 1
    base_url: str = ""


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


_SAFE_ID = re.compile(r"[A-Za-z0-9._-]+")


def key_file_path(provider_id: str, youk_root: Path | None = None) -> Path:
    """Where a provider's API key lives: state/inference-keys/{provider}.key under youk's own tree,
    which both containers already mount. One file per provider, so a key written for one provider is
    never sent to another. state/ is gitignored."""
    safe = provider_id if _SAFE_ID.fullmatch(provider_id) else "invalid"
    return (youk_root or YOUK_ROOT) / "state" / "inference-keys" / f"{safe}.key"


def key_env_names(provider_id: str) -> tuple[str, ...]:
    """Environment variables checked for a provider's key, in order."""
    return {"anthropic": ("ANTHROPIC_API_KEY",),
            "openai": ("YOUK_INFERENCE_API_KEY", "OPENAI_API_KEY")}.get(provider_id, ("YOUK_INFERENCE_API_KEY",))


def resolve_api_key(provider_id: str, env_names: tuple[str, ...], youk_root: Path | None = None) -> str:
    """The first of: the named environment variables, then the provider's key file. Empty if none."""
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    try:
        return key_file_path(provider_id, youk_root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


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
        key = resolve_api_key("anthropic", key_env_names("anthropic"))
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

    def generate(self, system: str, user: str, max_tokens: int) -> GenerationResult:
        if self._client is None:
            raise RuntimeError(self.capability.reason)
        response = self._client.messages.create(model=self.capability.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}])
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text="".join(getattr(block, "text", "") for block in response.content),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would resend the Authorization header to wherever it points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class _HttpError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}")
        self.status, self.body = status, body


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_OPENAI_URL = "https://api.openai.com/v1"


class OpenAICompatibleIntentProvider:
    """Any server that speaks the OpenAI chat-completions protocol: OpenAI itself, Ollama, vLLM,
    LM Studio, or a gateway in front of any model. Plain stdlib HTTP, so it adds no dependency.

    Configure with provider id "openai" (base URL defaults to OpenAI's) or "openai-compatible"
    (base URL required), a model, and a key. A key is optional only for a local server."""

    def __init__(self, provider_id: str = "openai-compatible", model: str | None = None,
                 base_url: str | None = None, *, youk_root: Path | None = None, timeout: float = 60.0) -> None:
        self._timeout = timeout
        model = model or os.environ.get("YOUK_INFERENCE_MODEL", "")
        url = (base_url or os.environ.get("YOUK_INFERENCE_BASE_URL", "")
               or (_OPENAI_URL if provider_id == "openai" else "")).rstrip("/")
        self._base_url = url
        self._key = resolve_api_key(provider_id, key_env_names(provider_id), youk_root)
        self.capability = self._assess(provider_id, model, url)

    def _assess(self, provider_id: str, model: str, url: str) -> InferenceCapability:
        def cap(status: InferenceStatus, reason: str) -> InferenceCapability:
            return InferenceCapability(provider_id, model, status, reason)

        if not url:
            return cap(InferenceStatus.UNAVAILABLE, "base URL is not configured")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return cap(InferenceStatus.INCOMPATIBLE, "base URL must be an http or https URL")
        if not model:
            return cap(InferenceStatus.UNAVAILABLE, "model is not configured")
        if not self._key and parsed.hostname not in _LOCAL_HOSTS:
            return cap(InferenceStatus.UNAVAILABLE, "credential is not configured")
        return cap(InferenceStatus.AVAILABLE, "configured")

    def _post(self, body: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        request = urllib.request.Request(f"{self._base_url}/chat/completions",
                                         data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _HttpError(exc.code, exc.read().decode("utf-8", "replace")[:300]) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"cannot reach {urlparse(self._base_url).hostname}: {exc.reason}") from None
        except (ValueError, UnicodeDecodeError):
            raise RuntimeError("the provider returned a response that is not JSON") from None

    def generate(self, system: str, user: str, max_tokens: int) -> GenerationResult:
        if self.capability.status is not InferenceStatus.AVAILABLE:
            raise RuntimeError(self.capability.reason)
        body = {"model": self.capability.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            payload = self._post({**body, "max_tokens": max_tokens})
        except _HttpError as exc:
            # Newer OpenAI models reject max_tokens and name the replacement in the error.
            if exc.status == 400 and "max_completion_tokens" in exc.body:
                try:
                    payload = self._post({**body, "max_completion_tokens": max_tokens})
                except _HttpError as retry:
                    raise RuntimeError(f"provider returned HTTP {retry.status}: {retry.body}") from None
            else:
                raise RuntimeError(f"provider returned HTTP {exc.status}: {exc.body}") from None
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("the provider's response has no choices[0].message.content") from None
        if isinstance(content, list):  # some servers return a list of content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        usage = payload.get("usage") or {}
        return GenerationResult(
            text=content or "",
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
        )


def select_intent_provider(provider_id: str | None = None, config_path: Path | None = None) -> IntentProvider:
    """Select a configured adapter; unknown providers are explicit, never fallback."""
    configuration = load_configuration(config_path) if config_path else None
    selected = provider_id or (configuration.provider_id if configuration else os.environ.get("YOUK_INFERENCE_PROVIDER", "anthropic"))
    model = (configuration.model or None) if configuration else None
    if selected == "anthropic":
        return AnthropicIntentProvider(model)
    if selected in ("openai", "openai-compatible"):
        return OpenAICompatibleIntentProvider(
            selected, model, (configuration.base_url or None) if configuration else None)
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
