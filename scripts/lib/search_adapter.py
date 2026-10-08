from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request


LOG = logging.getLogger("ppt-agent.search_adapter")


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - provider URL is fixed here
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def _clean_item(title: str, url: str, snippet: str, source: str) -> dict | None:
    url = str(url or "").strip()
    snippet = str(snippet or "").strip()
    title = str(title or url or "Untitled source").strip()
    if not url and not snippet:
        return None
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": source,
    }


def _search_tavily(query: str, max_results: int, timeout: int) -> list[dict]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    data = _post_json(
        "https://api.tavily.com/search",
        {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        },
        {},
        timeout,
    )
    out = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        normalized = _clean_item(
            item.get("title"),
            item.get("url"),
            item.get("content") or item.get("snippet"),
            "tavily",
        )
        if normalized:
            out.append(normalized)
    return out[:max_results]


def _search_serper(query: str, max_results: int, timeout: int) -> list[dict]:
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        raise RuntimeError("SERPER_API_KEY is not configured")
    data = _post_json(
        "https://google.serper.dev/search",
        {
            "q": query,
            "num": max_results,
        },
        {"X-API-KEY": api_key},
        timeout,
    )
    out = []
    for item in data.get("organic") or []:
        if not isinstance(item, dict):
            continue
        normalized = _clean_item(
            item.get("title"),
            item.get("link"),
            item.get("snippet"),
            "serper",
        )
        if normalized:
            out.append(normalized)
    return out[:max_results]


def search_web(query: str, max_results: int | None = None) -> list[dict]:
    """Search the public web through the configured independent search provider.

    Returns normalized dicts with title/url/snippet/source. Provider errors are
    logged and converted to an empty list so PPT generation can continue.
    """
    if not _env_bool("ENABLE_EXTERNAL_WEBSEARCH", True):
        LOG.info("external web search disabled by ENABLE_EXTERNAL_WEBSEARCH")
        return []
    query = str(query or "").strip()
    if not query:
        LOG.error("external web search skipped: empty query")
        return []
    provider = str(os.environ.get("SEARCH_PROVIDER") or "").strip().lower()
    if not provider:
        if os.environ.get("TAVILY_API_KEY"):
            provider = "tavily"
        elif os.environ.get("SERPER_API_KEY"):
            provider = "serper"
    timeout = _int_env("WEBSEARCH_TIMEOUT", 20)
    resolved_max_results = _int_env("WEBSEARCH_MAX_RESULTS", 5) if max_results is None else max_results
    max_results = max(1, int(resolved_max_results))
    try:
        if provider == "tavily":
            return _search_tavily(query, max_results, timeout)
        if provider == "serper":
            return _search_serper(query, max_results, timeout)
        LOG.error("external web search skipped: SEARCH_PROVIDER must be tavily or serper")
        return []
    except (RuntimeError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        LOG.error("external web search failed provider=%s query=%r error=%s", provider or "unset", query, exc)
        return []
