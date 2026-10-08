from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request


LOG = logging.getLogger("ppt-agent.extract_adapter")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - provider URL is fixed here
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def extract_url(url: str, query: str | None = None, timeout: int | None = None) -> dict:
    """Extract readable page content through Tavily Extract.

    Returns a normalized dict: url, content, source, ok, error. Provider errors
    are logged without secrets and converted to ok=False so callers can fallback.
    """
    url = str(url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"url": url, "content": "", "source": "tavily_extract", "ok": False, "error": "url must start with http:// or https://"}
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"url": url, "content": "", "source": "tavily_extract", "ok": False, "error": "TAVILY_API_KEY is not configured"}
    timeout = int(timeout or _int_env("WEBFETCH_TIMEOUT", 30))
    extract_depth = str(os.environ.get("TAVILY_EXTRACT_DEPTH") or "basic").strip() or "basic"
    payload = {
        "urls": [url],
        "extract_depth": extract_depth,
        "format": "markdown",
        "timeout": timeout,
    }
    if query:
        payload["query"] = str(query)
    try:
        data = _post_json(
            "https://api.tavily.com/extract",
            payload,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout,
        )
        results = data.get("results") if isinstance(data, dict) else None
        first = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
        content = str(first.get("raw_content") or "").strip()
        if content:
            return {"url": str(first.get("url") or url), "content": content, "source": "tavily_extract", "ok": True, "error": None}
        failed = data.get("failed_results") if isinstance(data, dict) else None
        error = "Tavily Extract returned no raw_content"
        if isinstance(failed, list) and failed:
            error = str(failed[0])[:500]
        return {"url": url, "content": "", "source": "tavily_extract", "ok": False, "error": error}
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        LOG.error("external extract failed url=%r error=%s", url, exc)
        return {"url": url, "content": "", "source": "tavily_extract", "ok": False, "error": str(exc)}
