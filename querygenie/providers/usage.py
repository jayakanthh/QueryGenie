"""
What a service reports about each request: tokens used, and the rate limits it sends back in headers.

Only reported numbers are kept. OpenAI-style services send x-ratelimit-* headers, Anthropic sends
anthropic-ratelimit-*; Google's Gemini API sends neither and only explains a quota when it refuses a
request (HTTP 429), so for Gemini the app can show what was exceeded, never what is left.
"""
from __future__ import annotations

import re
import time


def openai_limits(headers) -> dict | None:
    """x-ratelimit-{limit,remaining,reset}-{requests,tokens} (OpenAI, Groq, xAI and others)."""
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out = {}
    for what in ("requests", "tokens"):
        limit, left = h.get(f"x-ratelimit-limit-{what}"), h.get(f"x-ratelimit-remaining-{what}")
        if limit is not None and left is not None:
            out[what] = {"limit": _int(limit), "remaining": _int(left), "reset": _duration(h.get(f"x-ratelimit-reset-{what}"))}
    return out or None


def anthropic_limits(headers) -> dict | None:
    """anthropic-ratelimit-{requests,input-tokens,output-tokens}-{limit,remaining,reset}."""
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out = {}
    for what, name in (("requests", "requests"), ("input-tokens", "input tokens"), ("output-tokens", "output tokens")):
        limit, left = h.get(f"anthropic-ratelimit-{what}-limit"), h.get(f"anthropic-ratelimit-{what}-remaining")
        if limit is not None and left is not None:
            out[name] = {"limit": _int(limit), "remaining": _int(left), "reset": _rfc3339(h.get(f"anthropic-ratelimit-{what}-reset"))}
    return out or None


def google_refusal(error_json: dict) -> dict | None:
    """From a Gemini 429 body: which quotas were exceeded, their limits (Google writes them only in the
    message, "limit: 0"), the model it resolved to, and how long to wait."""
    err = (error_json or {}).get("error") or {}
    out, quotas = {}, []
    for d in err.get("details") or []:
        kind = d.get("@type", "")
        if kind.endswith("QuotaFailure"):
            for v in d.get("violations") or []:
                name = _quota_name(v.get("quotaId") or v.get("quotaMetric") or "")
                if name not in quotas:
                    quotas.append(name)
                out.setdefault("model", (v.get("quotaDimensions") or {}).get("model"))
        elif kind.endswith("RetryInfo") and d.get("retryDelay"):
            out["retry_s"] = _duration(d["retryDelay"])
    limits = [int(x) for x in re.findall(r"limit: (\d+)", err.get("message") or "")]
    if quotas:
        out["quotas"] = quotas
    if limits:
        out["limit"] = min(limits)
    return out or None


def classify(message: str, refusal: dict | None = None) -> str:
    """A ProviderError -> works / no_quota / daily_used / rate_limited / bad_key / no_access / not_found / error.
    `refusal` is google_refusal() of the error, when there was one."""
    m = (message or "").lower()
    if m.startswith("429") or "rate limit" in m or "quota" in m:
        if refusal:
            if refusal.get("limit") == 0:
                return "no_quota"                       # this key may not use the model at all
            if all("day" in q for q in refusal.get("quotas", [])) or (
                    any("day" in q for q in refusal.get("quotas", [])) and not any("minute" in q for q in refusal.get("quotas", []))):
                return "daily_used"
            return "rate_limited"
        return "no_quota" if "quota" in m else "rate_limited"
    if m.startswith("401") or "key was rejected" in m:
        return "bad_key"
    if m.startswith("403") or "no access" in m:
        return "no_access"
    if m.startswith("404") or "unknown model" in m:
        return "not_found"
    return "error"


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _duration(v) -> float | None:
    """'6m0s', '1.5s', '20ms', '41s' -> seconds."""
    if not v:
        return None
    total, found = 0.0, False
    for num, unit in re.findall(r"([\d.]+)\s*(ms|h|m|s)", str(v)):
        found = True
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return round(total, 1) if found else _int(v)


def _rfc3339(v) -> float | None:
    """An absolute reset time -> seconds from now."""
    if not v:
        return None
    from datetime import datetime
    try:
        return max(0.0, round(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() - time.time(), 1))
    except ValueError:
        return None


def _quota_name(quota_id: str) -> str:
    """'GenerateRequestsPerDayPerProjectPerModel-FreeTier' -> 'requests per day (free tier)'."""
    q = quota_id.split("/")[-1]
    what = "input tokens" if "InputToken" in q else "tokens" if "Token" in q else "requests"
    per = " per day" if "PerDay" in q else " per minute" if "PerMinute" in q else ""
    return what + per + (" (free tier)" if "free" in q.lower() else "")
