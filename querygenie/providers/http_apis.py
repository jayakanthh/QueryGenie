"""
Models reached over HTTP (no vendor SDKs, so the app stays small):

  Ollama            local server, http://localhost:11434 - runs any model you have pulled
  OpenAI-style      OpenAI, xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Together, and any
                    OpenAI-compatible server (LM Studio, vLLM, llama.cpp server...)
  Gemini            Google's Generative Language API

Claude is in anthropic_api.py (the official SDK). Every service is asked four times independently at
its default sampling settings; the four answers are the candidates.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import SYSTEM_PROMPT, CandidateBackend, ProviderError, parallel

TIMEOUT_S = 120
OLLAMA_URL = "http://localhost:11434"


def _request(method, url, headers=None, body=None, timeout=TIMEOUT_S):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        try:
            j = json.loads(detail)
            detail = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error") or detail
        except ValueError:
            pass
        hint = {401: "the API key was rejected", 403: "the key has no access to this model",
                404: "unknown model or address", 429: "rate limit or quota reached"}.get(exc.code, "")
        raise ProviderError(f"{exc.code} {hint + ': ' if hint else ''}{detail}".strip()) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Couldn't reach {url.split('/')[2]}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderError(f"{url.split('/')[2]} did not answer within {timeout} s") from exc


# ---------------------------------------------------------------- Ollama
def ollama_models(base_url=OLLAMA_URL):
    """Pulled models, largest first is not meaningful - keep Ollama's order (most recent)."""
    tags = _request("GET", base_url.rstrip("/") + "/api/tags", timeout=4)
    return [{"id": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1)} for m in tags.get("models", [])]


class Ollama(CandidateBackend):
    def __init__(self, model, label="", base_url=OLLAMA_URL, effort=None):
        super().__init__(model, label, effort)
        self.base_url = base_url.rstrip("/")

    def unload(self):
        """Ask Ollama to free the model now (it otherwise keeps it in memory for a few minutes)."""
        try:
            _request("POST", self.base_url + "/api/generate", body={"model": self.model, "keep_alive": 0}, timeout=10)
        except ProviderError:
            pass

    def raw_candidates(self, prompt):
        # Local and one model at a time: sequential avoids loading it four times over.
        out = []
        for i in range(4):
            body = {"model": self.model, "stream": False,
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
                    "options": {"temperature": 0.0 if i == 0 else 0.7}}
            if self.effort in ("on", "off"):                  # thinking models only
                body["think"] = self.effort == "on"
            r = _request("POST", self.base_url + "/api/chat", body=body)
            out.append((r.get("message") or {}).get("content", ""))
        return out


# ---------------------------------------------------------------- OpenAI-compatible
class OpenAICompatible(CandidateBackend):
    cloud = True

    def __init__(self, model, label="", base_url="https://api.openai.com/v1", api_key=None, cloud=True, effort=None):
        super().__init__(model, label, effort)
        self.base_url, self.api_key, self.cloud = base_url.rstrip("/"), api_key, cloud

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def raw_candidates(self, prompt):
        def one(_i):
            body = {"model": self.model,
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]}
            if self.effort:                                   # reasoning models only; others reject it
                body["reasoning_effort"] = self.effort
            r = _request("POST", self.base_url + "/chat/completions", headers=self._headers(), body=body)
            choice = (r.get("choices") or [{}])[0]
            return (choice.get("message") or {}).get("content") or ""
        return parallel(one)


def openai_models(base_url, api_key=None):
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    r = _request("GET", base_url.rstrip("/") + "/models", headers=headers, timeout=15)
    return sorted([{"id": m["id"]} for m in r.get("data", []) if m.get("id")], key=lambda m: m["id"])


# ---------------------------------------------------------------- Gemini
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"


class Gemini(CandidateBackend):
    cloud = True

    def __init__(self, model, label="", api_key=None):
        super().__init__(model, label)
        self.api_key = api_key

    def raw_candidates(self, prompt):
        name = self.model if self.model.startswith("models/") else "models/" + self.model

        def one(_i):
            r = _request("POST", f"{GEMINI_URL}/{name}:generateContent", headers={"x-goog-api-key": self.api_key},
                         body={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                               "contents": [{"role": "user", "parts": [{"text": prompt}]}]})
            parts = ((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return parallel(one)


def gemini_models(api_key):
    r = _request("GET", f"{GEMINI_URL}/models?pageSize=200", headers={"x-goog-api-key": api_key}, timeout=15)
    return [{"id": m["name"].removeprefix("models/"), "name": m.get("displayName", "")}
            for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
