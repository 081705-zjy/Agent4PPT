from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from .models import ROOT, read_json
from .route_log import append as append_route_log
from scripts.lib.extract_adapter import extract_url
from scripts.lib.search_adapter import search_web


def load_config() -> dict:
    return read_json(ROOT / "config/default_config.json", {})


def _command_exists(command: str) -> bool:
    first = command.split()[0] if command else ""
    if not first:
        return False
    if "/" in first:
        return (ROOT / first).exists() if not first.startswith("/") else Path(first).exists()
    return shutil.which(first) is not None


def _tool_registry() -> dict:
    cfg = load_config()
    tools = cfg.get("tool_providers") or {}
    if cfg.get("web_search_cmd"):
        tools.setdefault("claude_web_search", {
            "kind": "cli",
            "command": cfg.get("web_search_cmd"),
            "capabilities": ["web_search"],
        })
    if cfg.get("web_fetch_cmd"):
        tools.setdefault("claude_web_fetch", {
            "kind": "cli",
            "command": cfg.get("web_fetch_cmd"),
            "capabilities": ["web_fetch"],
        })
    tools.setdefault("resource_index", {
        "kind": "local",
        "command": "builtin",
        "capabilities": ["local_resource_search"],
    })
    tools.setdefault("search_adapter", {
        "kind": "builtin_search",
        "command": "builtin",
        "capabilities": ["web_search"],
    })
    tools.setdefault("http_fetch", {
        "kind": "builtin_http",
        "command": "builtin",
        "capabilities": ["web_fetch"],
    })
    tools.setdefault("extract_adapter", {
        "kind": "builtin_extract",
        "command": "builtin",
        "capabilities": ["web_fetch"],
    })
    tools.setdefault("native_svg", {
        "kind": "local_script",
        "command": "bash scripts/export-pptx.sh",
        "capabilities": ["ppt_render", "validation"],
    })
    return tools


def _routes() -> dict:
    cfg = load_config()
    return cfg.get("tool_routes") or {
        "web_search": {"primary": "search_adapter", "fallback": []},
        "web_fetch": {"primary": "extract_adapter", "fallback": ["http_fetch"]},
        "web_extract": {"primary": "extract_adapter", "fallback": ["http_fetch"]},
        "local_resource_search": {"primary": "resource_index", "fallback": []},
        "ppt_render": {"primary": "native_svg", "fallback": []},
        "validation": {"primary": "native_svg", "fallback": []},
    }


def resolve(tool_name: str) -> dict:
    tools = _tool_registry()
    route = _routes().get(tool_name) or {}
    candidates = [route.get("primary")] + list(route.get("fallback") or [])
    candidates = [str(c) for c in candidates if c]
    return {
        "tool": tool_name,
        "route": route,
        "candidates": [
            {"provider": provider_id, "config": tools.get(provider_id, {})}
            for provider_id in candidates
        ],
    }


def health() -> dict:
    tools = _tool_registry()
    statuses = {}
    for provider_id, provider in tools.items():
        command = str(provider.get("command") or "")
        statuses[provider_id] = {
            "provider_id": provider_id,
            "kind": provider.get("kind") or "unknown",
            "capabilities": provider.get("capabilities") or [],
            "command": command,
            "command_present": command == "builtin" or _command_exists(command),
            "configured": command == "builtin" or _command_exists(command),
        }
    route_status = {}
    for tool_name, route in _routes().items():
        primary = route.get("primary")
        route_status[tool_name] = {
            "primary": primary,
            "fallback": route.get("fallback") or [],
            "configured": bool(statuses.get(str(primary), {}).get("configured")),
        }
    return {"tools": route_status, "providers": statuses}


def _run_cli(command: str, placeholder: str, value: str, timeout: int, env_extra: dict | None = None) -> tuple[int, str, str]:
    if placeholder in command:
        argv = shlex.split(command.replace(placeholder, value))
    else:
        argv = shlex.split(command) + [value]
    env = dict(os.environ)
    env["PPT_CLAUDE_TIMEOUT_SECONDS"] = str(timeout)
    if env_extra:
        env.update({str(k): str(v) for k, v in env_extra.items()})
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=timeout + 5, check=False, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


def _arxiv_id_from_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    if "arxiv.org" not in parsed.netloc.lower():
        return None
    match = re.search(r"/(?:abs|pdf)/([^/?#]+)", parsed.path)
    if not match:
        return None
    arxiv_id = match.group(1).removesuffix(".pdf")
    return arxiv_id if arxiv_id else None


def _quote_url(url: str) -> str:
    """Percent-encode non-ASCII URL path/query so urllib can fetch Chinese PDF URLs."""
    parsed = urllib.parse.urlsplit(str(url))
    netloc = parsed.netloc.encode("idna").decode("ascii") if parsed.netloc else ""
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path or "/"), safe="/:@!$&'()*+,;=%")
    query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&?/:;+,%")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, path, query, parsed.fragment))


def _extract_pdf_text(raw: bytes, timeout: int) -> str:
    """Extract PDF text when poppler's pdftotext is available; otherwise fail closed."""
    if not raw.startswith(b"%PDF"):
        return ""
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return ""
    with tempfile.TemporaryDirectory(prefix="ppt-agent-pdf-") as td:
        pdf_path = Path(td) / "source.pdf"
        txt_path = Path(td) / "source.txt"
        pdf_path.write_bytes(raw)
        proc = subprocess.run(
            [pdftotext, "-layout", str(pdf_path), str(txt_path)],
            text=True,
            capture_output=True,
            timeout=max(3, min(timeout, 20)),
            check=False,
        )
        if proc.returncode != 0 or not txt_path.exists():
            return ""
        return re.sub(r"\s+", " ", txt_path.read_text(encoding="utf-8", errors="ignore")).strip()


def _http_get_text(url: str, timeout: int) -> str:
    safe_url = _quote_url(url)
    req = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": "ppt-agent/1.0 (+https://github.com/081705-zjy)",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,application/pdf;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - route-configured source URL
        content_type = resp.headers.get("content-type", "")
        raw = resp.read(1_500_000)
    if "pdf" in content_type.lower() or raw.startswith(b"%PDF"):
        pdf_text = _extract_pdf_text(raw, timeout)
        return pdf_text or "PDF_BINARY_UNEXTRACTED: fetched PDF bytes but no usable text extractor is available"
    encoding = "utf-8"
    match = re.search(r"charset=([^;\s]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    text = raw.decode(encoding, errors="ignore")
    if "html" in content_type.lower() or re.search(r"(?i)<html|<body|<p[>\s]", text[:2000]):
        return _strip_html(text)
    return re.sub(r"\s+", " ", text).strip()


def _http_fetch(url: str, timeout: int) -> tuple[bool, str, str]:
    arxiv_id = _arxiv_id_from_url(url)
    try:
        if arxiv_id:
            api_url = f"https://export.arxiv.org/api/query?id_list={urllib.parse.quote(arxiv_id)}"
            xml_text = _http_get_text(api_url, timeout)
            try:
                root = ET.fromstring(xml_text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entry = root.find("atom:entry", ns)
                if entry is not None:
                    title = re.sub(r"\s+", " ", entry.findtext("atom:title", default="", namespaces=ns)).strip()
                    summary = re.sub(r"\s+", " ", entry.findtext("atom:summary", default="", namespaces=ns)).strip()
                    published = entry.findtext("atom:published", default="", namespaces=ns)
                    authors = [
                        re.sub(r"\s+", " ", item.findtext("atom:name", default="", namespaces=ns)).strip()
                        for item in entry.findall("atom:author", ns)
                    ]
                    text = f"{title}. Published: {published}. Authors: {', '.join(a for a in authors if a)}. Abstract: {summary}"
                    if is_valid_fetched_text(text):
                        return True, text, ""
            except ET.ParseError:
                pass
        text = _http_get_text(url, timeout)
        return is_valid_fetched_text(text), text, "" if is_valid_fetched_text(text) else "invalid or too-short http body"
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return False, "", str(exc)


_INVALID_FETCH_PATTERNS = [
    r"^%pdf",
    r"pdf_binary_unextracted",
    r"\blinearized\b.*\bxref\b",
    r"\bendobj\b",
    r"\bno content\b",
    r"web fetch is unavailable",
    r"could not retrieve",
    r"could not be verified",
    r"reason logged to stderr",
    r"no factual notes were extracted",
    r"network restriction",
    r"enterprise security policy",
    r"\bblocked\b",
]


def is_valid_fetched_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) < 240:
        return False
    lowered = normalized.lower()
    if lowered.startswith("%pdf") or len(re.findall(r"\b\d+\s+0\s+obj\b", lowered)) >= 3:
        return False
    return not any(re.search(pattern, lowered) for pattern in _INVALID_FETCH_PATTERNS)


def _normalize_json(data) -> list[dict]:
    if isinstance(data, dict):
        for key in ("results", "items", "sources", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or item.get("source_url") or "").strip()
        title = str(item.get("title") or item.get("name") or url or "Untitled source").strip()
        snippet = str(item.get("snippet") or item.get("summary") or item.get("content") or "").strip()
        if url or snippet:
            out.append({"url": url or "local:search-result", "title": title, "snippet": snippet})
    return out


def normalize_search_results(text: str) -> list[dict]:
    import json

    try:
        return _normalize_json(json.loads(text))
    except json.JSONDecodeError:
        pass
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 4 and parts[0].lower() == "url":
                parts = parts[1:]
            if len(parts) >= 3 and parts[0].startswith(("http://", "https://")):
                out.append({"url": parts[0], "title": parts[1], "snippet": parts[2]})
                continue
        match = re.search(r"https?://\S+", line)
        if match:
            url = match.group(0).rstrip(".,)")
            out.append({"url": url, "title": line[:100], "snippet": line})
    return out


def web_search(project_id: str, query: str, timeout: int | None = None, max_results: int | None = None) -> dict:
    cfg = load_config()
    timeout = int(timeout or os.environ.get("PPT_AGENT_RESEARCH_TIMEOUT_SECONDS") or cfg.get("research_adapter_timeout_seconds") or 90)
    retries = max(1, int(os.environ.get("PPT_AGENT_WEB_SEARCH_ATTEMPTS") or cfg.get("web_search_attempts") or 1))
    start = time.time()
    errors = []
    for candidate in resolve("web_search")["candidates"]:
        provider_id = candidate["provider"]
        provider = candidate["config"]
        command = str(provider.get("command") or "")
        if not command:
            continue
        for attempt in range(1, retries + 1):
            try:
                if provider.get("kind") == "builtin_search":
                    results = search_web(query, max_results=max_results)
                    code = 0 if results else 1
                    stdout = json.dumps(results, ensure_ascii=False)
                    stderr = "" if results else "search_adapter returned no results"
                else:
                    code, stdout, stderr = _run_cli(
                        command,
                        "{query}",
                        query,
                        timeout,
                        env_extra={"WEBSEARCH_MAX_RESULTS": max_results} if max_results else None,
                    )
                    results = normalize_search_results(stdout.strip()) if code == 0 else []
                ok = code == 0 and bool(results)
                append_route_log(project_id, {
                    "stage": "web_search",
                    "route_type": "tool",
                    "selected_provider": provider_id,
                    "success": ok,
                    "latency_ms": int((time.time() - start) * 1000),
                    "attempt": attempt,
                    "error": None if ok else (stderr.strip() or stdout.strip() or f"returncode={code}")[:500],
                })
                if ok:
                    return {"ok": True, "provider": provider_id, "query": query, "results": results, "warnings": errors}
                errors.append(f"{provider_id} attempt {attempt}/{retries} returned no usable results: {(stderr.strip() or stdout.strip())[:240]}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider_id} attempt {attempt}/{retries} failed: {exc}")
                append_route_log(project_id, {
                    "stage": "web_search",
                    "route_type": "tool",
                    "selected_provider": provider_id,
                    "success": False,
                    "latency_ms": int((time.time() - start) * 1000),
                    "attempt": attempt,
                    "error": str(exc)[:500],
                })
    return {"ok": False, "provider": None, "query": query, "results": [], "warnings": errors}


def web_fetch(project_id: str, url: str, timeout: int | None = None, query: str | None = None) -> dict:
    cfg = load_config()
    timeout = int(
        timeout
        or os.environ.get("PPT_AGENT_FETCH_TIMEOUT_SECONDS")
        or os.environ.get("WEBFETCH_TIMEOUT")
        or cfg.get("fetch_adapter_timeout_seconds")
        or 35
    )
    retries = max(1, int(os.environ.get("PPT_AGENT_WEB_FETCH_ATTEMPTS") or cfg.get("web_fetch_attempts") or 1))
    start = time.time()
    errors = []
    for candidate in resolve("web_fetch")["candidates"]:
        provider_id = candidate["provider"]
        provider = candidate["config"]
        command = str(provider.get("command") or "")
        if not command:
            continue
        for attempt in range(1, retries + 1):
            try:
                if provider.get("kind") == "builtin_extract":
                    extracted = extract_url(url, query=query, timeout=timeout)
                    ok = bool(extracted.get("ok") and is_valid_fetched_text(str(extracted.get("content") or "")))
                    text = str(extracted.get("content") or "")
                    error = extracted.get("error") or ("invalid or too-short extracted body" if not ok else None)
                elif provider.get("kind") == "builtin_http":
                    ok, text, error = _http_fetch(url, timeout)
                else:
                    code, stdout, stderr = _run_cli(command, "{url}", url, timeout)
                    text = re.sub(r"\s+", " ", stdout).strip()
                    ok = code == 0 and is_valid_fetched_text(text)
                    error = None
                    if not ok:
                        if code != 0:
                            error = stderr.strip() or f"returncode={code}"
                        elif text:
                            error = f"invalid_fetch_text: {text[:240]}"
                        else:
                            error = stderr.strip() or "empty fetch output"
                append_route_log(project_id, {
                    "stage": "web_fetch",
                    "route_type": "tool",
                    "selected_provider": provider_id,
                    "success": ok,
                    "latency_ms": int((time.time() - start) * 1000),
                    "attempt": attempt,
                    "error": None if ok else str(error)[:500],
                })
                if ok:
                    return {"ok": True, "provider": provider_id, "url": url, "text": text[:1200], "warnings": errors}
                errors.append(f"{provider_id} attempt {attempt}/{retries}: {error}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider_id} attempt {attempt}/{retries}: {exc}")
                append_route_log(project_id, {
                    "stage": "web_fetch",
                    "route_type": "tool",
                    "selected_provider": provider_id,
                    "success": False,
                    "latency_ms": int((time.time() - start) * 1000),
                    "attempt": attempt,
                    "error": str(exc)[:500],
                })
    return {"ok": False, "provider": None, "url": url, "text": "", "error": "; ".join(errors)[:500]}
