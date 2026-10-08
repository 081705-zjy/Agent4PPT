from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from .models import ROOT, read_json
from .route_log import append as append_route_log


# ---------------------------------------------------------------------------
# Per-provider circuit breaker (in-memory): after N consecutive failures a
# provider is "open" (skipped fast) for a cooldown window, so a rate-limited or
# unreachable HTTP endpoint cannot stall every request that routes through it.
# ---------------------------------------------------------------------------
_BREAKER_THRESHOLD = 3
_BREAKER_COOLDOWN_SECONDS = 60.0
_BREAKER_LOCK = threading.Lock()
_BREAKER: dict[str, dict] = {}


def _breaker(provider_id: str) -> dict:
    with _BREAKER_LOCK:
        return _BREAKER.setdefault(provider_id, {"fails": 0, "open_until": 0.0})


def _breaker_is_open(provider_id: str) -> bool:
    return _breaker(provider_id)["open_until"] > time.time()


def _breaker_record(provider_id: str, ok: bool) -> None:
    st = _breaker(provider_id)
    with _BREAKER_LOCK:
        if ok:
            st["fails"] = 0
            st["open_until"] = 0.0
        else:
            st["fails"] += 1
            if st["fails"] >= _BREAKER_THRESHOLD:
                st["open_until"] = time.time() + _BREAKER_COOLDOWN_SECONDS
                st["fails"] = 0


def _provider_enabled(provider: dict) -> bool:
    return bool(provider.get("enabled", True))


def _call_mode(provider: dict) -> str:
    kind = str(provider.get("kind") or "")
    if kind == "openai_chat":
        return "http"
    if kind in {"cli", "coding_agent"}:
        return "cli"
    return kind or "unknown"


def _classify_error(message: str) -> str:
    m = (message or "").lower()
    if "qps" in m or "tpm" in m or "rate" in m or "429" in m:
        return "rate_limit"
    if "timed out" in m or "timeout" in m:
        return "timeout"
    if (
        "network is unreachable" in m
        or "temporary failure in name resolution" in m
        or "name or service not known" in m
        or "connection refused" in m
        or "connection reset" in m
        or "failed to establish a new connection" in m
        or "failedtoopensocket" in m
        or "unable to connect to api" in m
        or "operation not permitted" in m
        or "error sending request" in m
        or "stream disconnected before completion" in m
        or "failed to connect to websocket" in m
    ):
        return "network_unavailable"
    if "http 4" in m or "http 5" in m or "httperror" in m:
        return "http_error"
    if "not present" in m or "unset" in m or "unavailable" in m or "missing env" in m or "insufficient account balance" in m:
        return "not_configured"
    if "choices" in m or "invalid" in m or "json" in m:
        return "invalid_response"
    if "circuit" in m:
        return "circuit_open"
    return "error"


def _fallback_policy() -> dict:
    policy = load_config().get("model_fallback_policy") or {}
    fallback_types = policy.get("fallback_on_error_types")
    stop_types = policy.get("stop_on_error_types")
    return {
        "fallback_on_error_types": set(fallback_types or ["not_configured", "circuit_open", "network_unavailable"]),
        "stop_on_error_types": set(stop_types or ["timeout", "invalid_response", "rate_limit", "http_error", "error"]),
        "description": str(policy.get("description") or "fallback only on unavailable providers"),
    }


def load_config() -> dict:
    return read_json(ROOT / "config/default_config.json", {})


def _providers() -> dict:
    return load_config().get("providers") or {}


def _routes() -> dict:
    return load_config().get("model_routes") or {}


def _command_exists(command: str) -> bool:
    first = command.split()[0] if command else ""
    return bool(first and shutil.which(first))


def _provider_model(provider: dict, fallback: str | None = None) -> str | None:
    model = str(provider.get("model") or fallback or "").strip()
    return model or None


def _resolve_base_url(provider: dict) -> str | None:
    """Return the chat endpoint URL: a static ``base_url``, or ``base_url_env`` (an env var
    holding the API root) joined with an optional ``path`` suffix. None if unresolvable."""
    base = provider.get("base_url")
    if base:
        return str(base)
    env_name = provider.get("base_url_env")
    if env_name:
        root = (os.environ.get(str(env_name)) or "").rstrip("/")
        if root:
            return root + str(provider.get("path") or "")
    return None


def _provider_config_status(provider: dict) -> tuple[bool, str | None]:
    kind = str(provider.get("kind") or "unknown")
    command = str(provider.get("command") or "")
    if kind in {"openai_chat"}:
        missing = [str(k) for k in provider.get("env_keys") or [] if not os.environ.get(str(k))]
        if missing:
            return False, f"missing env: {', '.join(missing)}"
        if not _resolve_base_url(provider):
            return False, f"base url unavailable ({provider.get('base_url_env') or 'base_url'} unset)"
        return True, None
    if command and command != "builtin" and not _command_exists(command):
        return False, f"command not found: {command.split()[0]}"
    return True, None


def _route_candidates(stage: str) -> list[str]:
    route = _routes().get(stage)
    if isinstance(route, str):
        return [route]
    if isinstance(route, dict):
        return [p for p in [route.get("primary"), *(route.get("fallback") or [])] if p]
    return []


def resolve(stage: str) -> dict:
    providers = _providers()
    candidates = [
        {"provider": provider_id, "config": providers.get(provider_id, {})}
        for provider_id in _route_candidates(stage)
    ]
    return {"stage": stage, "candidates": candidates}


def health() -> dict:
    providers = _providers()
    out = {}
    for provider_id, provider in providers.items():
        kind = str(provider.get("kind") or "unknown")
        env_keys = [str(k) for k in provider.get("env_keys") or []]
        env_any_keys = [str(k) for k in provider.get("env_any_keys") or []]
        all_keys = list(dict.fromkeys(env_keys + env_any_keys))
        env_present = {key: bool(os.environ.get(key)) for key in all_keys}
        required_ok = all(env_present.values()) if env_keys else True
        any_ok = any(env_present.get(key) for key in env_any_keys) if env_any_keys else True
        command = str(provider.get("command") or "")
        command_ok = kind == "openai_chat" or command == "builtin" or _command_exists(command)
        provider_ok, reason = _provider_config_status(provider)
        enabled = _provider_enabled(provider)
        configured = provider_ok and command_ok and required_ok and (any_ok or kind in {"cli", "coding_agent"})
        breaker_open = _breaker_is_open(provider_id)
        # 4-state status: disabled > not_configured > degraded(circuit open) > available
        if not enabled:
            status = "disabled"
        elif not configured:
            status = "not_configured"
        elif breaker_open:
            status = "degraded"
        else:
            status = "available"
        out[provider_id] = {
            "provider_id": provider_id,
            "label": provider.get("label") or provider_id,
            "kind": kind,
            "call_mode": _call_mode(provider),
            "enabled": enabled,
            "status": status,
            "circuit_open": breaker_open,
            "model": _provider_model(provider),
            "capabilities": provider.get("capabilities") or [],
            "command": command,
            "command_present": command_ok,
            "env_present": env_present,
            "configured": configured,
            "unavailable_reason": reason if status != "available" else None,
        }
    route_status = {}
    for stage, route in _routes().items():
        candidates = _route_candidates(stage)
        route_status[stage] = {
            "primary": candidates[0] if candidates else None,
            "fallback": candidates[1:],
            "configured": any(out.get(p, {}).get("configured") for p in candidates),
            "available": any(out.get(p, {}).get("status") == "available" for p in candidates),
        }
    return {"routes": route_status, "providers": out}


def _run_claude(prompt: str, timeout: int, provider: dict | None = None) -> str:
    args = ["claude", "-p", "--output-format", "text", "--no-session-persistence"]
    model = _provider_model(provider or {})
    if model:
        args[1:1] = ["--model", model]
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        input=prompt,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        detail = stderr or stdout or f"claude exited {proc.returncode}"
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise RuntimeError(f"claude exited {proc.returncode}: {detail}")
    return proc.stdout.strip()


def _run_codex(prompt: str, timeout: int, provider: dict | None = None, cfg: dict | None = None) -> str:
    runtime_home = ROOT / ".codex-runtime"
    runtime_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "HOME": str(runtime_home),
        "CODEX_HOME": str(runtime_home),
        "XDG_CONFIG_HOME": str(runtime_home / "config"),
        "XDG_CACHE_HOME": str(runtime_home / "cache"),
        "XDG_DATA_HOME": str(runtime_home / "data"),
    })
    for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        os.makedirs(env[key], exist_ok=True)
    args = ["codex", "exec"]
    model = _provider_model(provider or {}, (cfg or {}).get("codex_model"))
    if model:
        args.extend(["--model", model])
    args.extend(["--skip-git-repo-check", "--sandbox", "workspace-write", "--", "-"])
    proc = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        text=True,
        input=prompt,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"codex exited {proc.returncode}")
    return proc.stdout.strip()


def _run_openai_chat(provider: dict, prompt: str, timeout: int) -> str:
    key_name = str((provider.get("env_keys") or ["INFINI_API_KEY"])[0])
    api_key = os.environ.get(key_name)
    if not api_key:
        raise RuntimeError(f"{key_name} is not present")
    url = _resolve_base_url(provider)
    if not url:
        raise RuntimeError(f"base url unavailable ({provider.get('base_url_env') or 'base_url'} unset)")
    payload = {"model": provider.get("model"), "messages": [{"role": "user", "content": prompt}]}
    if provider.get("max_tokens"):
        payload["max_tokens"] = int(provider["max_tokens"])
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - configured provider URL
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # surface proxy error body -> fast fallback
        detail = exc.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    data = json.loads(raw)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        # OpenAI-compatible proxies return errors as 200 + {"error": ...} (e.g. rate limit)
        raise RuntimeError(str(data.get("error") or data)[:300])
    return str(choices[0].get("message", {}).get("content") or "").strip()


def _provider_timeout(provider: dict, default_timeout: int) -> int:
    try:
        return int(provider.get("timeout_seconds") or default_timeout)
    except (TypeError, ValueError):
        return default_timeout


def generate(project_id: str, stage: str, prompt: str, context: dict | None = None, timeout: int | None = None) -> dict:
    cfg = load_config()
    stage_timeouts = cfg.get("stage_model_timeouts") or {}
    stage_timeout = (
        timeout
        or os.environ.get(f"PPT_AGENT_MODEL_TIMEOUT_SECONDS_{stage.upper()}")
        or os.environ.get("PPT_AGENT_MODEL_TIMEOUT_SECONDS")
        or stage_timeouts.get(stage)
    )
    default_timeout = int(
        stage_timeout
        or cfg.get("model_timeout_seconds")
        or 90
    )
    fallback_policy = _fallback_policy()
    context = context or {}
    providers = _providers()
    errors = []
    candidates = _route_candidates(stage)

    def _log(index: int, provider: dict, provider_id: str, *, success: bool, skipped: bool,
             latency_ms: int, error: str | None, error_type: str | None) -> None:
        append_route_log(project_id, {
            "stage": stage,
            "route_type": "model",
            "selected_provider": provider_id,
            "provider_type": str(provider.get("kind") or "unknown"),
            "call_mode": _call_mode(provider),
            "fallback_provider": candidates[index + 1] if index + 1 < len(candidates) else None,
            "fallback_used": index > 0,
            "attempted_providers": candidates[:index + 1],
            "success": success,
            "skipped": skipped,
            "latency_ms": latency_ms,
            "error": error,
            "error_type": error_type,
        })

    def _should_continue_after(index: int, error_type: str) -> bool:
        return index + 1 < len(candidates) and error_type in fallback_policy["fallback_on_error_types"]

    def _suppress_fallback(error_type: str) -> None:
        errors.append(
            "fallback suppressed by model_fallback_policy: "
            f"{error_type}; {fallback_policy['description']}"
        )

    for index, provider_id in enumerate(candidates):
        provider = providers.get(provider_id, {})
        kind = str(provider.get("kind") or "")

        # Skip-fast conditions (disabled / not configured / circuit open) — never block.
        if not _provider_enabled(provider):
            errors.append(f"{provider_id}: skipped (disabled)")
            _log(index, provider, provider_id, success=False, skipped=True, latency_ms=0,
                 error="provider disabled", error_type="disabled")
            if not _should_continue_after(index, "disabled"):
                _suppress_fallback("disabled")
                break
            continue
        provider_ok, unavailable_reason = _provider_config_status(provider)
        if not provider_ok:
            errors.append(f"{provider_id}: skipped ({unavailable_reason})")
            _log(index, provider, provider_id, success=False, skipped=True, latency_ms=0,
                 error=unavailable_reason, error_type="not_configured")
            if not _should_continue_after(index, "not_configured"):
                _suppress_fallback("not_configured")
                break
            continue
        if _breaker_is_open(provider_id):
            errors.append(f"{provider_id}: skipped (circuit open)")
            _log(index, provider, provider_id, success=False, skipped=True, latency_ms=0,
                 error="circuit breaker open", error_type="circuit_open")
            if not _should_continue_after(index, "circuit_open"):
                _suppress_fallback("circuit_open")
                break
            continue

        full_prompt = prompt
        if context:
            full_prompt += "\n\nContext JSON:\n" + json.dumps(context, ensure_ascii=False, indent=2)
        # Stage-specific timeouts must win over provider defaults. Otherwise a
        # light stage routed to a slow CLI provider can block for the provider's
        # generic timeout, while heavy stages cannot opt into a longer budget.
        call_timeout = default_timeout if stage_timeout else _provider_timeout(provider, default_timeout)
        start = time.time()
        try:
            if kind == "openai_chat":
                output = _run_openai_chat(provider, full_prompt, call_timeout)
            elif provider_id == "codex_cli" or kind == "coding_agent":
                output = _run_codex(full_prompt, call_timeout, provider, cfg)
            elif provider_id == "claude_cli" or kind == "cli":
                output = _run_claude(full_prompt, call_timeout, provider)
            else:
                raise RuntimeError(f"unsupported provider kind: {kind}")
            _breaker_record(provider_id, ok=True)
            _log(index, provider, provider_id, success=True, skipped=False,
                 latency_ms=int((time.time() - start) * 1000), error=None, error_type=None)
            return {"ok": True, "stage": stage, "provider": provider_id, "output": output, "errors": errors}
        except Exception as exc:  # noqa: BLE001
            error_type = _classify_error(str(exc))
            _breaker_record(provider_id, ok=False)
            errors.append(f"{provider_id}: {exc}")
            _log(index, provider, provider_id, success=False, skipped=False,
                 latency_ms=int((time.time() - start) * 1000), error=str(exc)[:500],
                 error_type=error_type)
            if not _should_continue_after(index, error_type):
                _suppress_fallback(error_type)
                break
    return {"ok": False, "stage": stage, "provider": None, "output": "", "errors": errors}
