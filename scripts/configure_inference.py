#!/usr/bin/env python3
"""Configure the model youk uses for its own reasoning call (optimize_intent), and check it.

youk makes one model call itself. This chooses which provider answers it without touching the
agent host's own model. Credentials come only from environment variables supplied to the process.
Providers:

  anthropic           Claude models (default)
  openai              OpenAI's chat-completions API
  openai-compatible   any server speaking that protocol: Ollama, vLLM, LM Studio, a gateway
                      (needs --base-url)

The provider, model and URL go in state/inference-provider.json, which holds no credential. A key
is optional only for a server on localhost.

  configure_inference.py --provider openai-compatible --base-url http://host.docker.internal:11434/v1 --model llama3.1
  ANTHROPIC_API_KEY=... configure_inference.py --provider anthropic
  OPENAI_API_KEY=... configure_inference.py --provider openai --model gpt-4o-mini
  configure_inference.py --show     # what is configured; never prints a key
  configure_inference.py --check    # exit 0 only if the provider is usable

Nothing here calls a provider's API; --check inspects configuration only.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "servers" / "shared"))
from youk_paths import locate_install  # noqa: E402

PROVIDERS = ("anthropic", "openai", "openai-compatible")
YOUK_DIR, _HOST_DIR, _AUDIT = locate_install(__file__)

import inference  # noqa: E402

# youk_paths bound YOUK_ROOT from the environment at import (/youk in a container); the CLI runs
# on the host, so point the provider's key-file lookup at this install's state/ directory.
inference.YOUK_ROOT = YOUK_DIR


def config_path() -> Path:
    return YOUK_DIR / "state" / "inference-provider.json"


def describe() -> tuple[str, bool]:
    """Human-readable status lines, and whether the provider is usable. Never includes a key."""
    cfg = inference.load_configuration(config_path())
    provider = inference.select_intent_provider(config_path=config_path())
    cap = provider.capability
    env_hit = next((n for n in inference.key_env_names(cap.provider_id) if os.environ.get(n, "").strip()), "")
    key_src = f"environment ({env_hit})" if env_hit else "none"
    lines = [
        f"provider: {cap.provider_id}" + ("" if cfg else " (default; no inference-provider.json)"),
        f"model:    {cap.model or '(adapter default)'}",
        f"base url: {(cfg.base_url if cfg and cfg.base_url else '') or '(provider default)'}",
        f"key:      {key_src}",
        f"status:   {cap.status.value} - {cap.reason}",
    ]
    return "\n".join(lines), cap.status is inference.InferenceStatus.AVAILABLE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Configure youk's own model call.")
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--model", default="")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 0 only if the provider is usable")
    args = ap.parse_args(argv)

    if args.provider:
        if args.provider == "openai-compatible" and not args.base_url:
            ap.error("--base-url is required for openai-compatible")
        inference.save_configuration(config_path(), inference.ProviderConfiguration(
            args.provider, args.model, base_url=args.base_url))
        print(f"configuration written to {config_path()}")
    elif not (args.show or args.check):
        ap.error("give --provider to configure, or --show / --check")

    text, usable = describe()
    if args.show or args.provider:
        print(text)
    if args.check:
        if not args.show and not args.provider:
            print(text.splitlines()[-1])
        return 0 if usable else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
