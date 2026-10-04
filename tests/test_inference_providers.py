"""The OpenAI-compatible adapter and the credential path, tested against a real local HTTP server so
the request on the wire is what is asserted, not an imagined client call."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import inference
from inference import (
    InferenceStatus,
    OpenAICompatibleIntentProvider,
    ProviderConfiguration,
    key_file_path,
    load_configuration,
    resolve_api_key,
    save_configuration,
    select_intent_provider,
)

_SCRIPT = Path(__file__).parent.parent / "scripts" / "configure_inference.py"


class _Stub:
    """A chat-completions server that records requests and plays back queued responses."""

    def __init__(self):
        self.requests: list[dict] = []
        self.responses: list[tuple[int, dict | str, dict]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                stub.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                      "body": json.loads(self.rfile.read(length) or b"{}")})
                status, payload, headers = stub.responses.pop(0) if stub.responses else (200, _ok("default"), {})
                data = payload if isinstance(payload, str) else json.dumps(payload)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data.encode())

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def queue(self, status=200, payload=None, headers=None):
        self.responses.append((status, payload if payload is not None else _ok("x"), headers or {}))


def _ok(text, prompt=7, completion=3):
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


@pytest.fixture
def stub():
    s = _Stub()
    yield s
    s.server.shutdown()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("YOUK_INFERENCE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                 "YOUK_INFERENCE_BASE_URL", "YOUK_INFERENCE_MODEL"):
        monkeypatch.delenv(name, raising=False)


# --- the request and the response --------------------------------------------------

def test_request_on_the_wire_and_normalised_result(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("YOUK_INFERENCE_API_KEY", "sk-secret")
    stub.queue(payload=_ok('{"estimated_size": "M"}', prompt=11, completion=5))
    p = OpenAICompatibleIntentProvider("openai-compatible", "m1", stub.url, youk_root=tmp_path)
    out = p.generate("be brief", "size this", 400)
    assert out == inference.GenerationResult('{"estimated_size": "M"}', 11, 5)
    (req,) = stub.requests
    assert req["path"] == "/v1/chat/completions" and req["auth"] == "Bearer sk-secret"
    assert req["body"] == {"model": "m1", "max_tokens": 400,
                           "messages": [{"role": "system", "content": "be brief"},
                                        {"role": "user", "content": "size this"}]}


def test_content_parts_list_is_joined(stub, tmp_path):
    stub.queue(payload={"choices": [{"message": {"content": [{"type": "text", "text": "ab"}, {"text": "c"}]}}]})
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    assert p.generate("s", "u", 10).text == "abc"      # a local server: no key needed


def test_newer_models_that_reject_max_tokens_get_one_retry(stub, tmp_path):
    stub.queue(status=400, payload={"error": {"message": "Unsupported parameter: use max_completion_tokens"}})
    stub.queue(payload=_ok("fine"))
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    assert p.generate("s", "u", 50).text == "fine"
    assert "max_tokens" in stub.requests[0]["body"] and "max_completion_tokens" not in stub.requests[0]["body"]
    assert stub.requests[1]["body"]["max_completion_tokens"] == 50 and "max_tokens" not in stub.requests[1]["body"]


def test_http_errors_surface_with_status_and_never_the_key(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("YOUK_INFERENCE_API_KEY", "sk-secret")
    stub.queue(status=401, payload={"error": "bad key"})
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    with pytest.raises(RuntimeError) as exc:
        p.generate("s", "u", 5)
    assert "HTTP 401" in str(exc.value) and "sk-secret" not in str(exc.value)


def test_a_redirect_is_not_followed_so_the_key_is_not_resent(stub, tmp_path, monkeypatch):
    monkeypatch.setenv("YOUK_INFERENCE_API_KEY", "sk-secret")
    stub.queue(status=307, payload="", headers={"Location": "http://127.0.0.1:1/steal"})
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    with pytest.raises(RuntimeError, match="HTTP 307"):
        p.generate("s", "u", 5)
    assert len(stub.requests) == 1


def test_unreachable_and_malformed_responses_are_explicit(stub, tmp_path):
    dead = OpenAICompatibleIntentProvider("openai-compatible", "m", "http://127.0.0.1:1/v1", youk_root=tmp_path)
    with pytest.raises(RuntimeError, match="cannot reach 127.0.0.1"):
        dead.generate("s", "u", 5)
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    stub.queue(payload="not json at all")
    with pytest.raises(RuntimeError, match="not JSON"):
        p.generate("s", "u", 5)
    stub.queue(payload={"unexpected": True})
    with pytest.raises(RuntimeError, match="no choices"):
        p.generate("s", "u", 5)


# --- when is a provider usable ------------------------------------------------------

@pytest.mark.parametrize("pid,model,url,key,status", [
    ("openai-compatible", "m", "", "k", InferenceStatus.UNAVAILABLE),              # no URL
    ("openai-compatible", "m", "ftp://x/v1", "k", InferenceStatus.INCOMPATIBLE),   # not http(s)
    ("openai-compatible", "", "https://api.example.com/v1", "k", InferenceStatus.UNAVAILABLE),  # no model
    ("openai-compatible", "m", "https://api.example.com/v1", "", InferenceStatus.UNAVAILABLE),  # remote needs a key
    ("openai-compatible", "m", "https://api.example.com/v1", "k", InferenceStatus.AVAILABLE),
    ("openai-compatible", "m", "http://localhost:11434/v1", "", InferenceStatus.AVAILABLE),      # local: key optional
    ("openai-compatible", "m", "http://host.docker.internal:11434/v1", "", InferenceStatus.AVAILABLE),
    ("openai", "gpt-x", "", "k", InferenceStatus.AVAILABLE),                        # URL defaults to OpenAI's
    ("openai", "gpt-x", "", "", InferenceStatus.UNAVAILABLE),
])
def test_capability_matrix(tmp_path, monkeypatch, pid, model, url, key, status):
    if key:
        monkeypatch.setenv("YOUK_INFERENCE_API_KEY", key)
    cap = OpenAICompatibleIntentProvider(pid, model, url, youk_root=tmp_path).capability
    assert cap.status is status, cap.reason


def test_an_unavailable_provider_refuses_to_generate_with_its_reason(tmp_path):
    p = OpenAICompatibleIntentProvider("openai-compatible", "m", "", youk_root=tmp_path)
    with pytest.raises(RuntimeError, match="base URL is not configured"):
        p.generate("s", "u", 5)


# --- credentials: env first, then the provider's own key file --------------------------

def test_key_resolution_order_and_isolation_between_providers(tmp_path, monkeypatch):
    f = key_file_path("openai", tmp_path)
    f.parent.mkdir(parents=True)
    f.write_text("file-key\n")
    assert resolve_api_key("openai", ("OPENAI_API_KEY",), tmp_path) == "file-key"
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert resolve_api_key("openai", ("OPENAI_API_KEY",), tmp_path) == "env-key"
    # a key written for one provider is never read for another
    assert resolve_api_key("anthropic", ("ANTHROPIC_API_KEY",), tmp_path) == ""
    assert key_file_path("../../etc/passwd", tmp_path).name == "invalid.key"


def test_openai_alias_accepts_the_standard_openai_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert OpenAICompatibleIntentProvider("openai", "m", youk_root=tmp_path).capability.status is InferenceStatus.AVAILABLE


# --- selection and configuration ------------------------------------------------------

def test_selection_builds_the_adapter_from_a_credential_free_config(tmp_path):
    cfg = tmp_path / "provider.json"
    save_configuration(cfg, ProviderConfiguration("openai-compatible", "llama3.1", base_url="http://localhost:11434/v1"))
    assert "key" not in cfg.read_text().lower()
    chosen = select_intent_provider(config_path=cfg)
    assert isinstance(chosen, OpenAICompatibleIntentProvider)
    assert (chosen.capability.provider_id, chosen.capability.model) == ("openai-compatible", "llama3.1")
    assert chosen.capability.status is InferenceStatus.AVAILABLE


def test_a_config_written_before_base_url_existed_still_loads(tmp_path):
    cfg = tmp_path / "provider.json"
    cfg.write_text(json.dumps({"provider_id": "anthropic", "model": "m", "schema_version": 1}))
    assert load_configuration(cfg) == ProviderConfiguration("anthropic", "m", base_url="")


def test_the_anthropic_adapter_now_reads_the_key_file_too(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "YOUK_ROOT", tmp_path)
    f = key_file_path("anthropic", tmp_path)
    f.parent.mkdir(parents=True)
    f.write_text("sk-ant-from-file")
    assert inference.AnthropicIntentProvider("m").capability.status is InferenceStatus.AVAILABLE


# --- the intent call end to end on another model --------------------------------------

def test_optimize_intent_runs_on_an_openai_compatible_server(stub, tmp_path, monkeypatch):
    import intent
    stub.queue(payload=_ok(json.dumps({"problem": "p", "estimated_size": "M", "ambiguity_detected": False})))
    provider = OpenAICompatibleIntentProvider("openai-compatible", "m", stub.url, youk_root=tmp_path)
    monkeypatch.setattr(intent, "_PROVIDER", provider)
    monkeypatch.setattr(intent, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(intent, "YOUK_ROOT", tmp_path)
    result = intent.optimize_intent("rework the retry behaviour of the uploader")
    assert result["mode"] == "api_optimized" and result["estimated_size"] == "M"
    assert stub.requests[0]["body"]["messages"][1]["content"].startswith("Raw input: rework the retry")


# --- scripts/configure_inference.py ---------------------------------------------------

def _cli(tmp_path, *args, stdin="", env=None):
    (tmp_path / "state").mkdir(exist_ok=True)
    full_env = {"PATH": os.environ["PATH"], "YOUK_HOME": str(tmp_path), **(env or {})}
    return subprocess.run([sys.executable, str(_SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, env=full_env)


def test_cli_writes_a_credential_free_config_and_a_private_key_file(tmp_path):
    out = _cli(tmp_path, "--provider", "openai", "--model", "gpt-x", "--key-stdin", stdin="sk-live-123\n")
    assert out.returncode == 0, out.stderr
    assert "sk-live-123" not in out.stdout + out.stderr
    key = tmp_path / "state" / "inference-keys" / "openai.key"
    assert key.read_text() == "sk-live-123\n" and (key.stat().st_mode & 0o777) == 0o600
    cfg = json.loads((tmp_path / "state" / "inference-provider.json").read_text())
    assert cfg["provider_id"] == "openai" and "sk-live-123" not in json.dumps(cfg)
    assert _cli(tmp_path, "--check").returncode == 0


def test_cli_key_from_env_and_missing_env_is_an_error(tmp_path):
    ok = _cli(tmp_path, "--provider", "anthropic", "--key-from-env", "MY_KEY", env={"MY_KEY": "sk-ant-x"})
    assert ok.returncode == 0 and (tmp_path / "state" / "inference-keys" / "anthropic.key").exists()
    bad = _cli(tmp_path, "--provider", "openai", "--key-from-env", "NOT_SET")
    assert bad.returncode == 2 and "NOT_SET" in bad.stderr


def test_cli_check_fails_when_unconfigured_and_show_never_prints_a_key(tmp_path):
    assert _cli(tmp_path, "--check").returncode == 1
    _cli(tmp_path, "--provider", "openai-compatible", "--base-url", "https://api.example.com/v1",
         "--model", "m", "--key-stdin", stdin="topsecret")
    shown = _cli(tmp_path, "--show")
    assert "topsecret" not in shown.stdout and "key:      file" in shown.stdout and "status:   available" in shown.stdout


def test_cli_requires_a_base_url_for_openai_compatible(tmp_path):
    out = _cli(tmp_path, "--provider", "openai-compatible", "--model", "m")
    assert out.returncode == 2 and "--base-url" in out.stderr
