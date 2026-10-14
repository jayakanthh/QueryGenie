"""
Models reached over HTTP (no vendor SDKs, so the app stays small):

  Ollama            local server, http://localhost:11434 - runs any model you have pulled
  OpenAI-style      OpenAI, xAI (Grok), DeepSeek, Mistral, Groq, OpenRouter, Together, and any
                    OpenAI-compatible server (LM Studio, vLLM, llama.cpp server...)
  Gemini            Google's Generative Language API

Claude is in anthropic_api.py (the official SDK). A cloud service is asked four times independently at
its default sampling settings; if some answers are the same query, a few more requests ask for a different
formulation. Ollama runs one request at a time, raising the temperature and showing the model what it has
already written, until there are four different queries.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request

from .base import SYSTEM_PROMPT, CandidateBackend, ProviderError

TIMEOUT_S = 120
LOCAL_TIMEOUT_S = 600      # a large local model can take minutes to load on first use
OLLAMA_URL = "http://localhost:11434"


def _ssl_context():
    """Mozilla's CA bundle from certifi: the python.org macOS Python (and the packaged app built from it)
    has no system certificates, so HTTPS fails with CERTIFICATE_VERIFY_FAILED without this."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = _ssl_context()


def _request(method, url, headers=None, body=None, timeout=TIMEOUT_S, meta=None):
    """JSON request. With `meta` (a dict), the response headers are put in meta["headers"]."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            if meta is not None:
                meta["headers"] = dict(r.headers)
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail, refusal = exc.read().decode(errors="replace"), None
        try:                                   # parse the whole body first: cutting it breaks the JSON
            j = json.loads(detail)
            if exc.code == 429:
                from .usage import google_refusal
                refusal = google_refusal(j)
            detail = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("error") or detail
        except ValueError:
            pass
        detail = str(detail).split("\n")[0].strip()[:300]
        hint = {401: "the API key was rejected", 403: "the key has no access to this model",
                404: "unknown model or address", 429: "rate limit or quota reached"}.get(exc.code, "")
        if exc.code == 429 and refusal:
            from .usage import classify
            kind = classify("429 quota", refusal)
            hint = {"no_quota": "this key can't use this model (its free-tier limit is 0) - try a smaller one, e.g. a Flash model",
                    "daily_used": "this key's daily quota for this model is used up",
                    "rate_limited": "too many requests at once - the free tier allows only a few per minute"}[kind]
            if (refusal.get("retry_s") or 0) >= 120:
                hint += f" (try again in about {int(refusal['retry_s'] // 60)} min)"
        raise ProviderError(f"{exc.code} {hint + ': ' if hint else ''}{detail}".strip(), refusal) from exc
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
        # Local, so one request at a time (the model is never loaded twice), until four different queries.
        return self.diverse_candidates(self._once, prompt)

    def complete_once(self, prompt):
        return self._once(prompt, 0.0)

    def _once(self, prompt, temperature):
        body = {"model": self.model, "stream": False,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *getattr(self, "turns", []),
                             {"role": "user", "content": prompt}],
                "options": {"temperature": temperature}}
        if self.effort in ("on", "off"):                      # thinking models only
            body["think"] = self.effort == "on"
        r = _request("POST", self.base_url + "/api/chat", body=body, timeout=LOCAL_TIMEOUT_S)
        self.note(r.get("prompt_eval_count"), r.get("eval_count"))
        return (r.get("message") or {}).get("content", "")


# ---------------------------------------------------------------- OpenAI-compatible
class OpenAICompatible(CandidateBackend):
    cloud = True

    def __init__(self, model, label="", base_url="https://api.openai.com/v1", api_key=None, cloud=True, effort=None):
        super().__init__(model, label, effort)
        self.base_url, self.api_key, self.cloud = base_url.rstrip("/"), api_key, cloud

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def raw_candidates(self, prompt):
        return self.sample(prompt)

    def complete_once(self, prompt):
        body = {"model": self.model,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *getattr(self, "turns", []),
                             {"role": "user", "content": prompt}]}
        if self.effort:                                       # reasoning models only; others reject it
            body["reasoning_effort"] = self.effort
        meta = {}
        r = _request("POST", self.base_url + "/chat/completions", headers=self._headers(), body=body, meta=meta)
        from .usage import openai_limits
        u = r.get("usage") or {}
        self.note(u.get("prompt_tokens"), u.get("completion_tokens"), openai_limits(meta.get("headers")))
        choice = (r.get("choices") or [{}])[0]
        return (choice.get("message") or {}).get("content") or ""


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
        return self.sample(prompt)

    def complete_once(self, prompt):
        name = self.model if self.model.startswith("models/") else "models/" + self.model
        r = _request("POST", f"{GEMINI_URL}/{name}:generateContent", headers={"x-goog-api-key": self.api_key},
                     body={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                           "contents": [*({"role": "model" if t["role"] == "assistant" else "user", "parts": [{"text": t["content"]}]}
                                          for t in getattr(self, "turns", [])),
                                        {"role": "user", "parts": [{"text": prompt}]}]})
        u = r.get("usageMetadata") or {}
        out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)
        self.note(u.get("promptTokenCount"), out or None)
        parts = ((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def gemini_models(api_key):
    r = _request("GET", f"{GEMINI_URL}/models?pageSize=200", headers={"x-goog-api-key": api_key}, timeout=15)
    return [{"id": m["name"].removeprefix("models/"), "name": m.get("displayName", "")}
            for m in r.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
