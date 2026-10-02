"""
Claude through the official Anthropic SDK (`pip install anthropic`).

Current Claude models don't take a temperature, so the four candidates are four independent
requests at the model's own settings. The model list comes from the Models API, not a fixed table.
"""

from __future__ import annotations

from .base import SYSTEM_PROMPT, CandidateBackend, ProviderError, parallel

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
# On these models a request can end with stop_reason "refusal"; the server-side fallback re-runs
# it on another model inside the same call instead of failing.
_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


def _client(api_key):
    try:
        import anthropic
    except ImportError as exc:
        raise ProviderError("Claude needs the anthropic package: pip install anthropic") from exc
    return anthropic, anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=120.0)


def _explain(anthropic, exc):
    if isinstance(exc, anthropic.AuthenticationError):
        return "the API key was rejected"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "the key has no access to this model"
    if isinstance(exc, anthropic.NotFoundError):
        return "unknown model"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate limit reached - try again shortly"
    if isinstance(exc, anthropic.BadRequestError):
        return f"request rejected: {exc.message}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error {exc.status_code}: {exc.message}"
    if isinstance(exc, anthropic.APIConnectionError):
        return "couldn't reach the Anthropic API - check the internet connection"
    return str(exc)


def claude_models(api_key):
    anthropic, client = _client(api_key)
    try:
        return [{"id": m.id, "name": m.display_name} for m in client.models.list()]
    except anthropic.AnthropicError as exc:
        raise ProviderError(_explain(anthropic, exc)) from exc


class Claude(CandidateBackend):
    cloud = True

    def __init__(self, model=DEFAULT_MODEL, label="", api_key=None, effort=None):
        super().__init__(model, label, effort)
        self.api_key = api_key

    def raw_candidates(self, prompt):
        return parallel(lambda _i: self.complete_once(prompt))

    def complete_once(self, prompt):
        anthropic, client = _client(self.api_key)
        messages = [*getattr(self, "turns", []), {"role": "user", "content": prompt}]
        extra = {"output_config": {"effort": self.effort}} if self.effort else {}
        try:
            if self.model in _FALLBACK_MODELS:
                r = client.beta.messages.create(model=self.model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                                                messages=messages, betas=["server-side-fallback-2026-06-01"],
                                                fallbacks=[{"model": "claude-opus-4-8"}], **extra)
            else:
                r = client.messages.create(model=self.model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT,
                                           messages=messages, **extra)
        except anthropic.AnthropicError as exc:
            raise ProviderError(_explain(anthropic, exc)) from exc
        if r.stop_reason == "refusal":
            return ""                             # counts as a candidate that did not run
        return "".join(b.text for b in r.content if b.type == "text")
