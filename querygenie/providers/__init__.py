"""
Every model the app can use, and how to build one from a saved choice ("engine spec").

An engine spec is a small dict kept in settings.json, e.g.
    {"kind": "ollama", "model": "qwen2.5-coder:7b"}
    {"kind": "openai", "model": "gpt-..."}                  # key lives in the OS keychain
    {"kind": "compat", "model": "...", "base_url": "http://localhost:1234/v1"}
API keys are never stored in settings.json or returned to the interface: they go to the macOS
Keychain / Windows Credential Manager through `keyring`.
"""

from __future__ import annotations

import os

from .base import CandidateBackend, ProviderError  # noqa: F401

KEYRING_SERVICE = "QueryGenie"

# Cloud services. "compat" presets use the OpenAI-compatible API; their addresses are the providers'
# documented OpenAI-compatible endpoints (not yet tested by the team - TBD).
CLOUD = {
    "openai":     {"name": "OpenAI (GPT)",        "base_url": "https://api.openai.com/v1"},
    "anthropic":  {"name": "Anthropic (Claude)",  "base_url": None},
    "gemini":     {"name": "Google (Gemini)",     "base_url": None},
    "xai":        {"name": "xAI (Grok)",          "base_url": "https://api.x.ai/v1"},
    "deepseek":   {"name": "DeepSeek",            "base_url": "https://api.deepseek.com/v1"},
    "mistral":    {"name": "Mistral",             "base_url": "https://api.mistral.ai/v1"},
    "groq":       {"name": "Groq",                "base_url": "https://api.groq.com/openai/v1"},
    "openrouter": {"name": "OpenRouter (hundreds of models)", "base_url": "https://openrouter.ai/api/v1"},
    "together":   {"name": "Together AI",         "base_url": "https://api.together.xyz/v1"},
}


# ---------------------------------------------------------------- keys
def _keyring():
    try:
        import keyring
        return keyring
    except ImportError as exc:
        raise ProviderError("Saving API keys needs the keyring package: pip install keyring") from exc


def key_set(provider: str, key: str | None):
    kr = _keyring()
    if key:
        kr.set_password(KEYRING_SERVICE, provider, key.strip())
    else:
        try:
            kr.delete_password(KEYRING_SERVICE, provider)
        except Exception:  # noqa: BLE001 - nothing saved
            pass


def key_get(provider: str) -> str | None:
    try:
        return _keyring().get_password(KEYRING_SERVICE, provider)
    except ProviderError:
        return None


def key_saved(provider: str) -> bool:
    return bool(key_get(provider))


# ---------------------------------------------------------------- listing models
def list_models(kind: str, base_url: str | None = None, key_name: str | None = None):
    """Models a service offers right now (asked live, so the list is never out of date)."""
    from . import http_apis

    if kind == "ollama":
        return http_apis.ollama_models(base_url or http_apis.OLLAMA_URL)
    if kind == "anthropic":
        from .anthropic_api import claude_models
        return claude_models(_need_key("anthropic"))
    if kind == "gemini":
        return http_apis.gemini_models(_need_key("gemini"))
    if kind == "compat":
        return http_apis.openai_models(base_url, key_get(key_name or "compat"))
    if kind in CLOUD:
        return http_apis.openai_models(CLOUD[kind]["base_url"], _need_key(kind))
    raise ProviderError(f"unknown provider {kind}")


def _need_key(provider):
    key = key_get(provider)
    if not key:
        raise ProviderError(f"Add your {CLOUD.get(provider, {}).get('name', provider)} API key first.")
    return key


# ---------------------------------------------------------------- building a backend
def build(spec: dict, legacy_paths: dict):
    """Turn an engine spec into a backend with decide() / decide_connected()."""
    from . import http_apis, local

    kind, model = spec.get("kind"), spec.get("model")
    label = spec.get("label") or model
    if kind == "mlx":
        path = legacy_paths.get(model, model)
        if not os.path.isdir(path):
            raise ProviderError(f"MLX model folder not found: {path}")
        return local.MLXCodes(path, label)
    if kind == "gguf":
        path = legacy_paths.get(model, model)
        if not os.path.exists(path):
            raise ProviderError(f"GGUF file not found: {path}")
        return local.GGUFCodes(path, label)
    if kind == "hf":
        return local.CodesLocal(model, label)
    if kind == "ollama":
        return http_apis.Ollama(model, label, spec.get("base_url") or http_apis.OLLAMA_URL)
    if kind == "compat":
        base = spec.get("base_url") or ""
        local_server = any(h in base for h in ("localhost", "127.0.0.1", "[::1]"))
        return http_apis.OpenAICompatible(model, label, base, key_get("compat"), cloud=not local_server)
    if kind == "anthropic":
        from .anthropic_api import Claude
        return Claude(model, label, _need_key("anthropic"))
    if kind == "gemini":
        return http_apis.Gemini(model, label, _need_key("gemini"))
    if kind in CLOUD:
        return http_apis.OpenAICompatible(model, label, CLOUD[kind]["base_url"], _need_key(kind))
    raise ProviderError(f"unknown model type {kind}")
