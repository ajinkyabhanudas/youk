import json

from inference import InferenceStatus, record_execution, select_intent_provider


def test_unknown_provider_is_incompatible(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = select_intent_provider("future-provider")
    assert provider.capability.status is InferenceStatus.INCOMPATIBLE
    assert provider.capability.reason == "provider adapter is not installed"


def test_missing_credential_is_explicitly_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = select_intent_provider("anthropic")
    assert provider.capability.status is InferenceStatus.UNAVAILABLE
    assert provider.capability.reason == "credential is not configured"


def test_execution_trace_hashes_request_and_never_persists_content(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    request = "private customer request"
    record_execution(tmp_path / "trace.jsonl", select_intent_provider("anthropic").capability, request, "degraded")
    persisted = json.loads((tmp_path / "trace.jsonl").read_text())
    assert persisted["outcome"] == "degraded"
    assert request not in repr(persisted)
    assert len(persisted["request_sha256"]) == 64
