"""Reported usage and rate limits (querygenie/providers/usage.py) - no network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from querygenie.providers.usage import anthropic_limits, classify, google_refusal, openai_limits  # noqa: E402


def test_openai_headers():
    h = {"x-ratelimit-limit-requests": "500", "x-ratelimit-remaining-requests": "499", "x-ratelimit-reset-requests": "120ms",
         "x-ratelimit-limit-tokens": "30000", "x-ratelimit-remaining-tokens": "28000", "x-ratelimit-reset-tokens": "6m0s"}
    lim = openai_limits(h)
    assert lim["requests"] == {"limit": 500, "remaining": 499, "reset": 0.1}
    assert lim["tokens"]["reset"] == 360
    assert openai_limits({}) is None


def test_anthropic_headers():
    lim = anthropic_limits({"anthropic-ratelimit-requests-limit": "50", "anthropic-ratelimit-requests-remaining": "49"})
    assert lim["requests"]["remaining"] == 49 and lim["requests"]["reset"] is None


def test_google_free_tier_without_quota():
    body = {"error": {"message": "You exceeded your current quota...\n* Quota exceeded for metric: x, limit: 0, model: gemini-3.1-pro",
                      "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
                          {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaDimensions": {"model": "gemini-3.1-pro"}},
                          {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                          {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "56381s"}]}}
    r = google_refusal(body)
    assert r == {"quotas": ["requests per day (free tier)", "requests per minute (free tier)"], "model": "gemini-3.1-pro",
                 "retry_s": 56381, "limit": 0}
    assert classify("429 rate limit or quota reached: You exceeded your current quota", r) == "no_quota"
    assert classify("429 rate limit or quota reached", {"quotas": ["requests per minute (free tier)"], "limit": 10}) == "rate_limited"
    assert classify("429 rate limit or quota reached", {"quotas": ["requests per day (free tier)"], "limit": 50}) == "daily_used"
    assert classify("401 the API key was rejected: bad") == "bad_key"
    assert classify("unknown model") == "not_found"


def test_short_rate_limits_are_retried_and_failures_recorded(monkeypatch):
    import time
    from querygenie.providers.base import CandidateBackend, ProviderError
    monkeypatch.setattr(time, "sleep", lambda s: None)
    tries = {"n": 0}

    class Flaky(CandidateBackend):
        def complete_once(self, prompt):
            tries["n"] += 1
            if tries["n"] <= 2:
                raise ProviderError("429 rate limit or quota reached", {"quotas": ["requests per minute (free tier)"], "limit": 5, "retry_s": 3})
            return "SELECT 1"

    b = Flaky("m")
    assert b.sample("p") == ["SELECT 1"] * 4 and b.failures == []

    class NoQuota(CandidateBackend):
        def complete_once(self, prompt):
            raise ProviderError("429 rate limit or quota reached", {"quotas": ["requests per day (free tier)"], "limit": 0})

    b = NoQuota("m")
    try:
        b.sample("p")
    except ProviderError:
        pass
    assert len(b.failures) == 4                      # never retried: a limit of 0 won't clear
