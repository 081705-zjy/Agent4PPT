from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, wait

from .models import ROOT, now, read_json, write_json
from . import tool_providers


def load_config() -> dict:
    return read_json(ROOT / "config/default_config.json", {})


def is_zh(text: str, language: str = "zh") -> bool:
    return language.lower().startswith("zh") or bool(re.search(r"[\u4e00-\u9fff]", text))


def _clean_topic(topic: str) -> str:
    cleaned = re.sub(r"[:：|｜\-—–]+", " ", str(topic or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _canonical_topic_terms(topic: str) -> list[str]:
    lowered = str(topic or "").lower()
    terms = []
    if ("端" in topic or "edge" in lowered) and ("存储" in topic or "storage" in lowered):
        terms.extend([
            "edge storage optimization",
            "heterogeneous storage architecture",
            "edge computing storage systems",
        ])
    if "自进化" in topic or "self-evolving" in lowered or "self evolving" in lowered:
        terms.extend([
            "self-evolving agents",
            "self-evolving AI agents",
            "AgentEvolver",
            "lifelong agentic systems",
        ])
    if "智能体" in topic or "agent" in lowered:
        terms.append("LLM agents")
    return list(dict.fromkeys(terms))


def _depth_value(cfg: dict, base_key: str, depth: str, default: int) -> int:
    depth_key = f"{base_key}_{str(depth or 'light').lower()}"
    try:
        return int(cfg.get(depth_key) or cfg.get(base_key) or default)
    except (TypeError, ValueError):
        return default


def build_queries(topic: str, language: str, depth: str = "light") -> list[str]:
    if depth == "none":
        return []
    cleaned_topic = _clean_topic(topic)
    canonical = _canonical_topic_terms(topic)
    primary = " ".join(canonical[:2]) if canonical else cleaned_topic
    if is_zh(topic, language):
        english_primary = primary if canonical else f"{cleaned_topic} edge storage architecture"
        queries = [
            f"{english_primary} recent survey paper",
            f"{english_primary} IEEE ACM arxiv paper",
            f"{cleaned_topic} 综述 论文",
            f"{cleaned_topic} 架构 优化 benchmark",
        ]
        if depth == "deep":
            queries.extend([
                f"{english_primary} system architecture benchmark",
                f"{cleaned_topic} 学术 综述 异构 存储",
                "edge AI memory hierarchy storage bottleneck survey",
                "KV cache offloading edge device heterogeneous memory",
                "edge cloud collaborative inference memory scheduling",
                "near memory computing edge AI storage architecture",
                "LLM agent memory management long context state storage",
                "端侧大模型 存储优化 异构内存 综述",
            ])
    else:
        queries = [
            f"{cleaned_topic} recent survey paper",
            f"{cleaned_topic} system architecture optimization",
            f"{cleaned_topic} challenges trends benchmark",
        ]
        if depth == "deep":
            queries.extend([
                f"{cleaned_topic} arxiv paper",
                f"{cleaned_topic} ACM IEEE survey",
                "edge AI memory hierarchy storage bottleneck survey",
                "KV cache offloading edge device heterogeneous memory",
                "edge cloud collaborative inference memory scheduling",
                "near memory computing edge AI storage architecture",
                "LLM agent memory management long context state storage",
            ])
    return list(dict.fromkeys(q for q in queries if q.strip()))


def _source_rank(item: dict) -> int:
    url = str(item.get("url") or "").lower()
    title = str(item.get("title") or "").lower()
    text = f"{url} {title}"
    score = 0
    high_value_domains = (
        "arxiv.org",
        "dl.acm.org",
        "ieeexplore.ieee.org",
        "usenix.org",
        "openreview.net",
        "proceedings.mlr.press",
        "pmc.ncbi.nlm.nih.gov",
        "nist.gov",
        "w3.org",
        "ietf.org",
    )
    if any(domain in url for domain in high_value_domains):
        score += 80
    if any(token in text for token in ("osdi", "sosp", "asplos", "isca", "micro", "hpca", "sigcomm", "vldb")):
        score += 35
    if url.endswith(".pdf") or ".pdf" in url or "arxiv.org/pdf" in url:
        score += 25
    if any(token in text for token in ("survey", "综述", "benchmark", "architecture", "system", "paper")):
        score += 15
    if any(domain in url for domain in ("github.com", "docs.", "developer.", "cloud.google.com", "aws.amazon.com", "microsoft.com")):
        score += 10
    if any(domain in url for domain in ("researchgate.net", "slideshare.net", "readkong.com")):
        score -= 50
    if any(token in text for token in ("advertisement", "marketing", "solution brief")):
        score -= 20
    return score


_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_RESTRICTED_PUBLISHER_DOMAINS = (
    "ieeexplore.ieee.org",
    "dl.acm.org",
)
_OPEN_ACCESS_DOMAINS = (
    "arxiv.org",
    "ar5iv.labs.arxiv.org",
    "semanticscholar.org",
    "openreview.net",
    "usenix.org",
    "pmc.ncbi.nlm.nih.gov",
)


def _normalize_doi(value: str) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    doi = doi.strip().strip(".,;，。；)）]")
    return doi.lower()


def _extract_doi(*values: str) -> str:
    for value in values:
        text = str(value or "")
        match = _DOI_RE.search(text)
        if match:
            return _normalize_doi(match.group(0))
    return ""


def _normalized_title(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b(arxiv|ieee|acm|doi)\b", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _paper_key(item: dict) -> str:
    doi = str(item.get("doi") or "") or _extract_doi(
        str(item.get("doi") or ""),
        str(item.get("url") or ""),
        str(item.get("snippet") or ""),
        str(item.get("title") or ""),
    )
    if doi:
        return f"doi:{doi}"
    title_key = _normalized_title(str(item.get("title") or ""))
    if title_key and len(title_key) >= 12:
        return f"title:{title_key}"
    return f"url:{str(item.get('url') or item.get('snippet') or '')}"


def _is_restricted_publisher_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return any(domain in lowered for domain in _RESTRICTED_PUBLISHER_DOMAINS)


def _is_open_access_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return any(domain in lowered for domain in _OPEN_ACCESS_DOMAINS) or lowered.endswith(".pdf") or ".pdf" in lowered


def _open_access_query(item: dict) -> str:
    title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
    doi = str(item.get("doi") or "") or _extract_doi(
        str(item.get("url") or ""),
        str(item.get("snippet") or ""),
        title,
    )
    parts = []
    if title:
        parts.append(f'"{title}"')
    if doi:
        parts.append(doi)
    parts.append("arxiv OR pdf OR semanticscholar")
    return " ".join(parts)


def _rank_results(results: list[dict]) -> list[dict]:
    ranked = []
    for index, item in enumerate(results):
        out = dict(item)
        out["source_rank"] = _source_rank(out)
        ranked.append((out["source_rank"], -index, out))
    ranked.sort(reverse=True)
    return [item for _, _, item in ranked]


def _source_quality_score(item: dict) -> tuple[int, int]:
    evidence_source = str(item.get("evidence_source") or "")
    fetch_status = str(item.get("fetch_status") or "")
    url = str(item.get("url") or "")
    score = _source_rank(item)
    if evidence_source == "fetched_text" or fetch_status == "fetched":
        score += 500
    elif evidence_source == "search_snippet":
        score += 120
    if _is_open_access_url(url):
        score += 180
    if _is_restricted_publisher_url(url):
        score -= 40
    if item.get("blocked_publisher"):
        score -= 80
    return score, len(str(item.get("evidence_text") or item.get("snippet") or ""))


def _merge_paper_versions(results: list[dict]) -> tuple[list[dict], dict]:
    groups: dict[str, list[dict]] = {}
    for item in results:
        out = dict(item)
        out["doi"] = str(out.get("doi") or "") or _extract_doi(
            str(out.get("url") or ""),
            str(out.get("snippet") or ""),
            str(out.get("title") or ""),
        )
        group_key = str(out.get("alternate_for_key") or "") or _paper_key(out)
        groups.setdefault(group_key, []).append(out)

    merged: list[dict] = []
    merged_duplicate_count = 0
    open_alternative_count = 0
    blocked_publisher_count = 0
    for items in groups.values():
        if len(items) > 1:
            merged_duplicate_count += len(items) - 1
        blocked_publisher_count += sum(1 for item in items if item.get("blocked_publisher") or _is_restricted_publisher_url(str(item.get("url") or "")))
        open_alternative_count += sum(1 for item in items if _is_open_access_url(str(item.get("url") or "")) and item.get("alternate_source_role") == "open_access_candidate")
        best = max(items, key=_source_quality_score)
        variants = []
        publisher_urls = []
        alternate_urls = []
        for item in items:
            variant = {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "doi": item.get("doi") or "",
                "provider": item.get("provider") or "",
                "fetch_status": item.get("fetch_status") or "",
                "evidence_source": item.get("evidence_source") or "",
                "role": item.get("alternate_source_role") or ("publisher_metadata" if item.get("blocked_publisher") else "source"),
            }
            variants.append(variant)
            url = str(item.get("url") or "")
            if _is_restricted_publisher_url(url):
                publisher_urls.append(url)
            elif url and url != best.get("url"):
                alternate_urls.append(url)
        out = dict(best)
        out["source_variants"] = variants
        out["merged_source_count"] = len(items)
        out["publisher_urls"] = list(dict.fromkeys(publisher_urls))
        out["alternate_urls"] = list(dict.fromkeys(alternate_urls))
        if any(item.get("doi") for item in items):
            out["doi"] = next(str(item.get("doi")) for item in items if item.get("doi"))
        if any(item.get("blocked_publisher") for item in items):
            out["has_blocked_publisher_variant"] = True
        merged.append(out)
    merged = _rank_results(merged)
    audit = {
        "merged_duplicate_count": merged_duplicate_count,
        "blocked_publisher_count": blocked_publisher_count,
        "open_alternative_count": open_alternative_count,
        "merged_source_count": len(merged),
        "raw_source_count": len(results),
    }
    return merged, audit


def _run_adapter(command: str, placeholder: str, value: str, timeout: int) -> tuple[int, str, str]:
    if placeholder in command:
        argv = shlex.split(command.replace(placeholder, value))
    else:
        argv = shlex.split(command) + [value]
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _run_adapter_health(command: str, placeholder: str, value: str, timeout: int) -> tuple[int, str, str]:
    if placeholder in command:
        argv = shlex.split(command.replace(placeholder, value))
    else:
        argv = shlex.split(command) + [value]
    env = dict(os.environ)
    env["PPT_AGENT_HEALTHCHECK"] = "1"
    env["PPT_CLAUDE_TIMEOUT_SECONDS"] = str(timeout)
    proc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=timeout + 2, check=False, env=env)
    return proc.returncode, proc.stdout, proc.stderr


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


def _normalize_text(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) == 3:
                out.append({"url": parts[0], "title": parts[1], "snippet": parts[2]})
                continue
        match = re.search(r"https?://\S+", line)
        if match:
            url = match.group(0).rstrip(".,)")
            out.append({"url": url, "title": line[:100], "snippet": line})
    return out


def parse_results(text: str) -> list[dict]:
    try:
        return _normalize_json(json.loads(text))
    except json.JSONDecodeError:
        return _normalize_text(text)


def local_results(project_dir: Path, topic: str, limit: int = 8) -> list[dict]:
    out = []
    for root_name in ("sources", "assets", "templates"):
        root = project_dir / root_name
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.suffix.lower() not in {".md", ".txt", ".csv", ".json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            snippet = re.sub(r"\s+", " ", text).strip()[:320]
            if not snippet:
                continue
            rel = path.relative_to(project_dir).as_posix()
            out.append({
                "url": f"local:{rel}",
                "title": rel,
                "snippet": snippet,
                "provider": "local-resource",
                "query": topic,
            })
            if len(out) >= limit:
                return out
    return out


def manifest_results(project_dir: Path, topic: str, limit: int = 12) -> list[dict]:
    manifest = read_json(project_dir / "run-manifest.json", {})
    urls = manifest.get("source_urls") if isinstance(manifest, dict) else []
    if not isinstance(urls, list):
        return []
    out = []
    seen = set()
    for raw_url in urls:
        url = str(raw_url or "").strip()
        if not url or url in seen or not url.startswith(("http://", "https://")):
            continue
        seen.add(url)
        title = re.sub(r"^https?://", "", url).strip("/")
        out.append({
            "url": url,
            "title": title or "Manifest source",
            "snippet": "",
            "provider": "run-manifest",
            "query": topic,
            "fetch_status": "not_attempted",
            "evidence_text": "",
            "evidence_source": "manifest_source_only",
        })
        if len(out) >= limit:
            break
    return out


def search(project_dir: Path, topic: str, language: str, depth: str = "light", search_cmd: str | None = None) -> dict:
    cfg = load_config()
    command = search_cmd or os.environ.get("PPT_AGENT_SEARCH_CMD") or str(cfg.get("web_search_cmd") or "")
    timeout = int(os.environ.get("WEBSEARCH_TIMEOUT") or os.environ.get("PPT_AGENT_RESEARCH_TIMEOUT_SECONDS") or cfg.get("research_adapter_timeout_seconds") or 25)
    per_query_default = _depth_value(cfg, "max_search_results_per_query", depth, 5)
    max_results = int(os.environ.get("WEBSEARCH_MAX_RESULTS") or per_query_default)
    max_research_results = int(os.environ.get("PPT_AGENT_MAX_RESEARCH_RESULTS") or _depth_value(cfg, "max_research_results", depth, 12))
    queries = build_queries(topic, language, depth)
    if queries:
        default_query_limit = _depth_value(cfg, "max_search_queries", depth, len(queries))
        query_limit = int(os.environ.get("PPT_AGENT_MAX_SEARCH_QUERIES") or default_query_limit or len(queries))
        queries = queries[:max(1, query_limit)]
    results: list[dict] = []
    warnings: list[str] = []
    seen = set()
    web_results_count = 0
    open_alternative_query_count = 0
    manifest_fallback_count = 0
    local_fallback_count = 0
    project_id = project_dir.name
    if queries:
        for query in queries:
            if search_cmd:
                try:
                    code, stdout, stderr = _run_adapter(command, "{query}", query, timeout)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"web-search failed for '{query}': {exc}")
                    continue
                if code != 0:
                    warnings.append(f"web-search returned {code} for '{query}': {stderr.strip()[:180]}")
                    continue
                parsed = parse_results(stdout.strip())
                provider = "web-search"
                provider_warnings = []
            else:
                routed = tool_providers.web_search(project_id, query, timeout=timeout, max_results=max_results)
                parsed = routed.get("results") or []
                provider = routed.get("provider") or "web_search"
                provider_warnings = list(routed.get("warnings") or [])
                if not parsed and routed.get("error"):
                    provider_warnings.append(str(routed.get("error")))
            if not parsed:
                preview = "; ".join(provider_warnings)[:240] or "empty output"
                warnings.append(f"web-search returned no parseable sources for '{query}': {preview}")
                continue
            for item in parsed:
                key = item.get("url") or item.get("snippet")
                if not key or key in seen:
                    continue
                seen.add(key)
                item["provider"] = provider
                item["query"] = query
                results.append(item)
                web_results_count += 1
                if len(results) >= max_research_results:
                    break
            if len(results) >= max_research_results:
                break
        if results and not search_cmd:
            restricted_items = [
                item for item in results
                if _is_restricted_publisher_url(str(item.get("url") or ""))
            ][:4]
            for original in restricted_items:
                query = _open_access_query(original)
                if not query.strip():
                    continue
                routed = tool_providers.web_search(project_id, query, timeout=timeout, max_results=3)
                parsed = routed.get("results") or []
                if not parsed:
                    if routed.get("error"):
                        warnings.append(f"open-access search returned no sources for '{original.get('title') or original.get('url')}': {str(routed.get('error'))[:180]}")
                    continue
                open_alternative_query_count += 1
                original_key = _paper_key(original)
                added_for_original = 0
                for alt in parsed:
                    alt_url = str(alt.get("url") or "")
                    if not alt_url.startswith("http") or _is_restricted_publisher_url(alt_url):
                        continue
                    key = alt.get("url") or alt.get("snippet")
                    if not key or key in seen:
                        continue
                    alt = dict(alt)
                    alt["provider"] = routed.get("provider") or "web_search"
                    alt["query"] = query
                    alt["alternate_for_key"] = original_key
                    alt["alternate_for_url"] = original.get("url") or ""
                    alt["alternate_for_title"] = original.get("title") or ""
                    alt["alternate_source_role"] = "open_access_candidate"
                    alt["doi"] = str(original.get("doi") or "") or _extract_doi(
                        str(original.get("url") or ""),
                        str(original.get("snippet") or ""),
                        str(original.get("title") or ""),
                    )
                    seen.add(key)
                    results.append(alt)
                    web_results_count += 1
                    added_for_original += 1
                    if added_for_original >= 2:
                        break
    if results:
        results = _rank_results(results)
    if not results:
        results = manifest_results(project_dir, topic)
        if results:
            manifest_fallback_count = len(results)
            warnings.append("web-search produced no usable sources; previous run-manifest source URLs were preserved without factual excerpts")
    if not results:
        results = local_results(project_dir, topic)
        if not results:
            warnings.append("no web-search adapter configured or no results returned; no citations were fabricated")
        else:
            local_fallback_count = len(results)
            warnings.append("web-search produced no usable sources; local project resources were used as fallback")
    return {
        "queries": queries,
        "results": results,
        "warnings": warnings,
        "web_results_count": web_results_count,
        "open_alternative_query_count": open_alternative_query_count,
        "manifest_fallback_count": manifest_fallback_count,
        "local_fallback_count": local_fallback_count,
        "max_research_results": max_research_results,
        "max_search_results_per_query": max_results,
        "depth": depth,
    }


def fetch(result: dict, fetch_cmd: str | None = None, project_id: str | None = None) -> dict:
    url = str(result.get("url") or "")
    if _is_restricted_publisher_url(url):
        result["doi"] = str(result.get("doi") or "") or _extract_doi(
            url,
            str(result.get("snippet") or ""),
            str(result.get("title") or ""),
        )
        result["blocked_publisher"] = True
        result["fetch_status"] = "blocked_fetch"
        result["fetch_warning"] = "publisher blocks automated or unauthenticated full-text fetch; metadata preserved and open-access alternatives are searched"
        result["evidence_text"] = str(result.get("snippet") or "")
        result["evidence_source"] = "publisher_metadata" if result.get("snippet") else "none"
        return result
    if not url.startswith("http"):
        result["fetch_status"] = "local"
        result["evidence_text"] = str(result.get("snippet") or "")
        result["evidence_source"] = "local_resource"
        return result
    cfg = load_config()
    command = fetch_cmd or os.environ.get("PPT_AGENT_FETCH_CMD")
    if not command and project_id:
        fetched = tool_providers.web_fetch(project_id, url, query=str(result.get("query") or "") or None)
        text = str(fetched.get("text") or "")
        if fetched.get("ok") and tool_providers.is_valid_fetched_text(text):
            result["fetched_text"] = fetched["text"]
            result["fetch_provider"] = fetched.get("provider")
            result["fetch_status"] = "fetched"
            result["evidence_text"] = fetched["text"]
            result["evidence_source"] = "fetched_text"
            if fetched.get("warnings"):
                result["fetch_errors"] = fetched.get("warnings")
        else:
            manifest_only = result.get("evidence_source") == "manifest_source_only"
            result["fetch_status"] = "fetch_failed" if manifest_only else ("snippet_only" if result.get("snippet") else "failed")
            result["fetch_warning"] = fetched.get("error") or "web_fetch did not return valid source text"
            result["evidence_text"] = "" if manifest_only else str(result.get("snippet") or "")
            result["evidence_source"] = "manifest_source_only" if manifest_only else ("search_snippet" if result.get("snippet") else "none")
        return result
    if not command:
        result["fetch_status"] = "snippet_only" if result.get("snippet") else "not_attempted"
        result["evidence_text"] = str(result.get("snippet") or "")
        result["evidence_source"] = "search_snippet" if result.get("snippet") else "none"
        return result
    timeout = int(os.environ.get("PPT_AGENT_RESEARCH_TIMEOUT_SECONDS") or cfg.get("research_adapter_timeout_seconds") or 25)
    try:
        code, stdout, stderr = _run_adapter(command, "{url}", url, timeout)
    except Exception as exc:  # noqa: BLE001
        result["fetch_warning"] = str(exc)
        return result
    if code != 0:
        manifest_only = result.get("evidence_source") == "manifest_source_only"
        result["fetch_warning"] = stderr.strip()[:180]
        result["fetch_status"] = "fetch_failed" if manifest_only else ("snippet_only" if result.get("snippet") else "failed")
        result["evidence_text"] = "" if manifest_only else str(result.get("snippet") or "")
        result["evidence_source"] = "manifest_source_only" if manifest_only else ("search_snippet" if result.get("snippet") else "none")
        return result
    text = re.sub(r"\s+", " ", stdout).strip()
    if tool_providers.is_valid_fetched_text(text):
        result["fetched_text"] = text[:1200]
        result["fetch_status"] = "fetched"
        result["evidence_text"] = result["fetched_text"]
        result["evidence_source"] = "fetched_text"
    else:
        manifest_only = result.get("evidence_source") == "manifest_source_only"
        result["fetch_status"] = "fetch_failed" if manifest_only else ("snippet_only" if result.get("snippet") else "failed")
        result["fetch_warning"] = f"invalid fetch text: {text[:180]}" if text else "empty fetch output"
        result["evidence_text"] = "" if manifest_only else str(result.get("snippet") or "")
        result["evidence_source"] = "manifest_source_only" if manifest_only else ("search_snippet" if result.get("snippet") else "none")
    return result


def _ensure_evidence_fields(result: dict) -> dict:
    out = dict(result)
    if _is_restricted_publisher_url(str(out.get("url") or "")):
        out["doi"] = str(out.get("doi") or "") or _extract_doi(
            str(out.get("url") or ""),
            str(out.get("snippet") or ""),
            str(out.get("title") or ""),
        )
        out["blocked_publisher"] = True
        out["fetch_status"] = out.get("fetch_status") or "blocked_fetch"
        out["fetch_warning"] = out.get("fetch_warning") or "publisher blocks automated or unauthenticated full-text fetch; metadata preserved and open-access alternatives are searched"
        out["evidence_text"] = str(out.get("evidence_text") or out.get("snippet") or "")
        out["evidence_source"] = out.get("evidence_source") or ("publisher_metadata" if out.get("evidence_text") else "none")
        return out
    fetched_text = str(out.get("fetched_text") or "")
    snippet = str(out.get("snippet") or "")
    if out.get("evidence_source") == "manifest_source_only":
        out.pop("fetched_text", None)
        out["fetch_status"] = out.get("fetch_status") or "not_attempted"
        out["evidence_text"] = ""
        return out
    if tool_providers.is_valid_fetched_text(fetched_text):
        out["fetch_status"] = "fetched"
        out["evidence_text"] = fetched_text
        out["evidence_source"] = "fetched_text"
    elif snippet:
        if out.get("fetch_status") not in {"failed", "not_attempted", "local"}:
            out["fetch_status"] = "snippet_only"
        out.pop("fetched_text", None)
        out["evidence_text"] = snippet
        out["evidence_source"] = "search_snippet" if not str(out.get("url") or "").startswith("local:") else "local_resource"
    else:
        out.pop("fetched_text", None)
        out["fetch_status"] = out.get("fetch_status") or "no_evidence"
        out["evidence_text"] = ""
        out["evidence_source"] = "none"
    return out


def write_artifacts(project_dir: Path, topic: str, language: str, research: dict, fetch_cmd: str | None = None) -> dict:
    ts = now()
    project_id = project_dir.name
    cfg = load_config()
    depth = str(research.get("depth") or ("deep" if int(research.get("web_results_count") or 0) > 12 else "light"))
    max_fetch_sources = int(os.environ.get("PPT_AGENT_MAX_FETCH_SOURCES") or _depth_value(cfg, "max_fetch_sources", depth, int(cfg.get("max_fetch_sources") or 4)))
    raw_results = [dict(item) for item in research.get("results", [])]
    raw_results = _rank_results(raw_results)
    fetch_indexes = [
        idx for idx, item in enumerate(raw_results)
        if str(item.get("url") or "").startswith("http") and not _is_restricted_publisher_url(str(item.get("url") or ""))
    ][:max_fetch_sources]
    results = [_ensure_evidence_fields(item) for item in raw_results]
    if fetch_indexes:
        workers = min(4, len(fetch_indexes))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            fetched_items = list(executor.map(
                lambda idx: fetch(dict(raw_results[idx]), fetch_cmd, project_id=project_id),
                fetch_indexes,
            ))
        for idx, item in zip(fetch_indexes, fetched_items, strict=False):
            results[idx] = _ensure_evidence_fields(item)
    results, merge_audit = _merge_paper_versions(results)
    fetched_count = sum(1 for r in results if r.get("fetch_status") == "fetched")
    external_search_ok = int(research.get("web_results_count") or 0) > 0
    external_extract_ok = any(r.get("fetch_provider") == "extract_adapter" and r.get("fetch_status") == "fetched" for r in results)
    fetch_errors = []
    for r in results:
        if r.get("fetch_warning"):
            fetch_errors.append({"url": r.get("url"), "provider": r.get("fetch_provider"), "error": r.get("fetch_warning")})
        for error in r.get("fetch_errors") or []:
            fetch_errors.append({"url": r.get("url"), "provider": r.get("fetch_provider"), "error": error})
    snippet_backed_count = sum(1 for r in results if r.get("evidence_source") == "search_snippet")
    weak_source_count = sum(1 for r in results if r.get("evidence_source") in {"search_snippet", "publisher_metadata", "manifest_source_only", "none"})
    evidence_count = sum(1 for r in results if r.get("evidence_text"))
    invalid_fetch_count = sum(1 for r in results if r.get("fetch_status") in {"failed", "fetch_failed", "snippet_only"} and r.get("fetch_warning"))
    citations = []
    for idx, item in enumerate(results, 1):
        citations.append({
            "id": f"S{idx}",
            "title": item.get("title") or f"Source {idx}",
            "url": item.get("url") or "",
            "query": item.get("query") or "",
            "snippet": item.get("evidence_text") or item.get("snippet") or "",
            "evidence_source": item.get("evidence_source") or "none",
            "evidence_tier": "full_text" if item.get("evidence_source") == "fetched_text" else (
                "snippet" if item.get("evidence_source") == "search_snippet" else "weak"
            ),
            "fetch_status": item.get("fetch_status") or "unknown",
            "fetch_warning": item.get("fetch_warning"),
            "doi": item.get("doi") or "",
            "source_variants": item.get("source_variants") or [],
            "provider": item.get("provider") or "unknown",
            "retrieved_at": ts,
        })
    source_quality_pass = fetched_count >= min(3, len(results)) and weak_source_count == 0 if results else False
    write_json(project_dir / "research-results.json", {
        "schema_version": "1.0",
        "generated_at": ts,
        "topic": topic,
        "language": language,
        "queries": research.get("queries", []),
        "results": results,
        "warnings": research.get("warnings", []),
        "web_results_count": research.get("web_results_count", 0),
        "open_alternative_query_count": research.get("open_alternative_query_count", 0),
        "max_research_results": research.get("max_research_results", 0),
        "max_search_results_per_query": research.get("max_search_results_per_query", 0),
        "manifest_fallback_count": research.get("manifest_fallback_count", 0),
        "local_fallback_count": research.get("local_fallback_count", 0),
        "fetched_count": fetched_count,
        "snippet_backed_count": snippet_backed_count,
        "weak_source_count": weak_source_count,
        "evidence_count": evidence_count,
        "invalid_fetch_count": invalid_fetch_count,
        "source_quality_pass": source_quality_pass,
        "max_fetch_sources": max_fetch_sources,
        "external_search_ok": external_search_ok,
        "external_extract_ok": external_extract_ok,
        "sources": [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "source": item.get("source") or item.get("provider") or "",
                "fetch_provider": item.get("fetch_provider") or "",
                "fetch_status": item.get("fetch_status") or "",
            }
            for item in results
        ],
        "fetch_error": fetch_errors,
        **merge_audit,
    })
    write_json(project_dir / "research-audit.json", {
        "schema_version": "1.0",
        "generated_at": ts,
        "topic": topic,
        "depth": depth,
        "web_search_provider": next((r.get("provider") for r in results if str(r.get("url", "")).startswith("http")), None),
        "web_results_count": research.get("web_results_count", 0),
        "open_alternative_query_count": research.get("open_alternative_query_count", 0),
        "max_research_results": research.get("max_research_results", 0),
        "max_search_results_per_query": research.get("max_search_results_per_query", 0),
        "manifest_fallback_count": research.get("manifest_fallback_count", 0),
        "local_fallback_count": research.get("local_fallback_count", 0),
        "fetched_count": fetched_count,
        "snippet_backed_count": snippet_backed_count,
        "weak_source_count": weak_source_count,
        "evidence_count": evidence_count,
        "invalid_fetch_count": invalid_fetch_count,
        "source_quality_pass": source_quality_pass,
        "max_fetch_sources": max_fetch_sources,
        "external_search_ok": external_search_ok,
        "external_extract_ok": external_extract_ok,
        "sources": [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "source": item.get("source") or item.get("provider") or "",
                "fetch_provider": item.get("fetch_provider") or "",
                "fetch_status": item.get("fetch_status") or "",
            }
            for item in results
        ],
        "fetch_error": fetch_errors,
        **merge_audit,
        "citation_count": len(citations),
        "fallback_used": bool(research.get("local_fallback_count", 0) or research.get("manifest_fallback_count", 0)),
        "warnings": research.get("warnings", []),
    })
    write_json(project_dir / "citations.json", {
        "schema_version": "1.0",
        "generated_at": ts,
        "citations": citations,
    })
    # Always emit research.md so the RESEARCH stage produces its declared artifact; with no
    # external sources it honestly records that (no fabricated citations).
    sources = "\n".join(
        f"- [{c['id']}] {c['title']} — {c['url']} (query: {c['query']})"
        for c in citations
    ) or "- no external sources found; deck claims rely on topic reasoning and project materials"
    facts = "\n".join(
        f"- [{c['id']}] ({c.get('evidence_source')}; tier={c.get('evidence_tier')}) {str(c.get('snippet') or '')[:260] or c['title']}"
        for c in citations
    ) or "- none"
    research_md = f'''---
schema_version: "1.0"
generated_at: "{ts}"
provenance: "app-research-adapter"
source_count: {len(citations)}
web_results_count: {research.get("web_results_count", 0)}
manifest_fallback_count: {research.get("manifest_fallback_count", 0)}
local_fallback_count: {research.get("local_fallback_count", 0)}
---

## Search Queries
{chr(10).join(f"- {q}" for q in research.get("queries", [])) or "- local project resources"}

## Sources
{sources}

## Warnings
{chr(10).join(f"- {w}" for w in research.get("warnings", [])) or "- none"}

## Extracted Facts
{facts}
'''
    (project_dir / "research.md").write_text(research_md, encoding="utf-8")
    return {"citations": citations, "research_path": str(project_dir / "research.md")}


def health_check(timeout_seconds: int = 6) -> dict:
    timeout_seconds = max(2, min(int(timeout_seconds or 6), 8))
    provider = str(os.environ.get("SEARCH_PROVIDER") or "").strip().lower()
    tavily_present = bool(os.environ.get("TAVILY_API_KEY"))
    serper_present = bool(os.environ.get("SERPER_API_KEY"))
    enabled = str(os.environ.get("ENABLE_EXTERNAL_WEBSEARCH", "true")).strip().lower() not in {"0", "false", "no", "off"}
    search_configured = enabled and (provider in {"tavily", "serper"} or tavily_present or serper_present)

    def run_routed_search_probe() -> dict:
        errors = []
        for candidate in tool_providers.resolve("web_search").get("candidates") or []:
            provider_id = candidate.get("provider")
            config = candidate.get("config") or {}
            kind = config.get("kind")
            command = str(config.get("command") or "")
            if kind == "cli":
                try:
                    code, stdout, stderr = _run_adapter_health(command, "{query}", "healthcheck", timeout_seconds)
                    ok = code == 0 and bool(tool_providers.normalize_search_results(stdout.strip()))
                    if ok:
                        return {
                            "name": "web_search",
                            "provider": provider_id,
                            "configured": True,
                            "ok": True,
                            "result_count": len(tool_providers.normalize_search_results(stdout.strip())),
                            "stdout_preview": stdout[:500],
                            "error": None,
                        }
                    errors.append(f"{provider_id}: {(stderr.strip() or stdout.strip() or f'returncode={code}')[:240]}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{provider_id}: {exc}")
            elif kind == "builtin_search":
                adapter = run_adapter_search_probe()
                if adapter.get("ok"):
                    return {"name": "web_search", **{k: v for k, v in adapter.items() if k != "name"}}
                errors.append(f"{provider_id}: {adapter.get('error')}")
        return {"name": "web_search", "provider": None, "configured": bool(tool_providers.resolve("web_search").get("candidates")), "ok": False, "error": "; ".join(errors)[:500]}

    def run_routed_fetch_probe() -> dict:
        errors = []
        for candidate in tool_providers.resolve("web_fetch").get("candidates") or []:
            provider_id = candidate.get("provider")
            config = candidate.get("config") or {}
            kind = config.get("kind")
            command = str(config.get("command") or "")
            if kind == "cli":
                try:
                    code, stdout, stderr = _run_adapter_health(command, "{url}", "https://example.com", timeout_seconds)
                    ok = code == 0 and bool(str(stdout or "").strip())
                    if ok:
                        return {
                            "name": "web_fetch",
                            "provider": provider_id,
                            "configured": True,
                            "ok": True,
                            "stdout_preview": stdout[:500],
                            "error": None,
                        }
                    errors.append(f"{provider_id}: {(stderr.strip() or stdout.strip() or f'returncode={code}')[:240]}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{provider_id}: {exc}")
            elif kind == "builtin_extract":
                adapter = run_adapter_extract_probe()
                if adapter.get("ok"):
                    return {"name": "web_fetch", **{k: v for k, v in adapter.items() if k != "name"}}
                errors.append(f"{provider_id}: {adapter.get('error')}")
            elif kind == "builtin_http":
                http = run_http_fetch_probe()
                if http.get("ok"):
                    return {"name": "web_fetch", **{k: v for k, v in http.items() if k != "name"}}
                errors.append(f"{provider_id}: {http.get('error')}")
        return {"name": "web_fetch", "provider": None, "configured": bool(tool_providers.resolve("web_fetch").get("candidates")), "ok": False, "error": "; ".join(errors)[:500]}

    def run_adapter_search_probe() -> dict:
        if not enabled:
            return {"name": "adapter_search", "provider": provider or None, "configured": False, "ok": False, "error": "disabled by ENABLE_EXTERNAL_WEBSEARCH"}
        if not search_configured:
            return {"name": "adapter_search", "provider": provider or None, "configured": False, "ok": False, "error": "set SEARCH_PROVIDER=tavily/serper and the matching API key"}
        old_timeout = os.environ.get("WEBSEARCH_TIMEOUT")
        os.environ["WEBSEARCH_TIMEOUT"] = str(timeout_seconds)
        try:
            results = search_web("edge storage optimization recent papers", max_results=1)
        finally:
            if old_timeout is None:
                os.environ.pop("WEBSEARCH_TIMEOUT", None)
            else:
                os.environ["WEBSEARCH_TIMEOUT"] = old_timeout
        return {
            "name": "adapter_search",
            "provider": provider or ("tavily" if tavily_present else "serper" if serper_present else None),
            "configured": True,
            "ok": bool(results),
            "result_count": len(results),
            "stdout_preview": json.dumps(results[:1], ensure_ascii=False)[:500],
            "error": None if results else "search_adapter returned no results; check server logs for provider error",
        }

    def run_http_fetch_probe() -> dict:
        ok, text, error = tool_providers._http_fetch("https://example.com", timeout_seconds)  # noqa: SLF001 - app health probes builtin provider
        return {
            "name": "http_fetch",
            "provider": "http_fetch",
            "configured": True,
            "ok": ok,
            "stdout_preview": text[:500],
            "error": error or None,
        }
    
    def run_adapter_extract_probe() -> dict:
        from scripts.lib.extract_adapter import extract_url

        old_timeout = os.environ.get("WEBFETCH_TIMEOUT")
        os.environ["WEBFETCH_TIMEOUT"] = str(timeout_seconds)
        try:
            result = extract_url("https://example.com")
        finally:
            if old_timeout is None:
                os.environ.pop("WEBFETCH_TIMEOUT", None)
            else:
                os.environ["WEBFETCH_TIMEOUT"] = old_timeout
        return {
            "name": "adapter_extract",
            "provider": "extract_adapter",
            "configured": bool(os.environ.get("TAVILY_API_KEY")),
            "ok": bool(result.get("ok")),
            "stdout_preview": str(result.get("content") or "")[:500],
            "error": result.get("error"),
        }

    probe_specs = [
        ("web_search", run_routed_search_probe),
        ("web_fetch", run_routed_fetch_probe),
        ("adapter_search", run_adapter_search_probe),
        ("adapter_extract", run_adapter_extract_probe),
        ("http_fetch", run_http_fetch_probe),
    ]
    pool = ThreadPoolExecutor(max_workers=len(probe_specs))
    future_specs = [(name, pool.submit(fn)) for name, fn in probe_specs]
    done, pending = wait([future for _, future in future_specs], timeout=timeout_seconds + 3)
    for future in pending:
        future.cancel()
    checks = []
    for name, future in future_specs:
        if future in done:
            try:
                checks.append(future.result())
            except Exception as exc:  # noqa: BLE001
                checks.append({"name": name, "provider": None, "configured": True, "ok": False, "error": str(exc)[:500]})
        else:
            checks.append({"name": name, "provider": None, "configured": True, "ok": False, "error": f"health probe timed out after {timeout_seconds + 3}s"})
    pool.shutdown(wait=False, cancel_futures=True)
    routed_search_ok = bool(checks[0].get("ok"))
    routed_fetch_ok = bool(checks[1].get("ok"))
    adapter_search_ok = bool(checks[2].get("ok"))
    adapter_extract_ok = bool(checks[3].get("ok"))
    http_fetch_live_ok = bool(checks[4].get("ok"))
    search_live_ok = routed_search_ok
    extract_live_ok = routed_fetch_ok
    ok = routed_search_ok and routed_fetch_ok
    return {
        "ok": ok,
        "search_live_ok": search_live_ok,
        "extract_live_ok": extract_live_ok,
        "http_fetch_live_ok": http_fetch_live_ok,
        "routed_search_live_ok": routed_search_ok,
        "routed_fetch_live_ok": routed_fetch_ok,
        "claude_search_live_ok": checks[0].get("provider") == "claude_web_search" and routed_search_ok,
        "claude_fetch_live_ok": checks[1].get("provider") == "claude_web_fetch" and routed_fetch_ok,
        "adapter_search_live_ok": adapter_search_ok,
        "adapter_extract_live_ok": adapter_extract_ok,
        "search_provider": provider or None,
        "enable_external_websearch": enabled,
        "tavily_api_key_env_present": tavily_present,
        "serper_api_key_env_present": serper_present,
        "status_message": (
            "research route is usable"
            if ok else
            "research route is not currently usable; check Claude CLI first, then SEARCH_PROVIDER/API key/network fallback"
        ),
        "checks": checks,
    }
