from __future__ import annotations

import os
import shutil

from .models import ROOT
from .research import load_config


DEFAULT_PROVIDERS = {
    "claude_cli": {
        "kind": "cli",
        "label": "Claude CLI",
        "command": "claude",
        "env_any_keys": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
        "capabilities": ["research", "web_search", "web_fetch", "reasoning"],
        "web_search_cmd": "bash scripts/claude-search.sh",
        "web_fetch_cmd": "bash scripts/claude-fetch.sh",
    },
    "native_svg": {
        "kind": "local_script",
        "label": "Native editable PPTX renderer",
        "command": "bash scripts/export-pptx.sh",
        "capabilities": ["render", "pptx", "editable_shapes"],
    },
}

DEFAULT_ROUTES = {
    "intake": "claude_cli",
    "research": "claude_cli",
    "outline": "claude_cli",
    "slide_rewrite": "claude_cli",
    "render": "native_svg",
    "review": "claude_cli",
}


def _command_exists(command: str) -> bool:
    first = command.split()[0] if command else ""
    if not first:
        return False
    if first.startswith("./") or "/" in first:
        return (ROOT / first).exists() if not first.startswith("/") else os.path.exists(first)
    return shutil.which(first) is not None


def _provider_status(provider_id: str, provider: dict) -> dict:
    command = str(provider.get("command") or "")
    env_keys = [str(k) for k in provider.get("env_keys") or []]
    env_any_keys = [str(k) for k in provider.get("env_any_keys") or []]
    all_keys = list(dict.fromkeys(env_keys + env_any_keys))
    env_present = {key: bool(os.environ.get(key)) for key in all_keys}
    command_present = _command_exists(command)
    required_env_ok = all(env_present.values()) if env_keys else True
    any_env_ok = any(env_present.get(key) for key in env_any_keys) if env_any_keys else True
    return {
        "provider_id": provider_id,
        "label": provider.get("label") or provider_id,
        "kind": provider.get("kind") or "unknown",
        "capabilities": provider.get("capabilities") or [],
        "command": command,
        "command_present": command_present,
        "env_present": env_present,
        "configured": command_present and required_env_ok and any_env_ok,
    }


def registry() -> dict:
    cfg = load_config()
    providers = {**DEFAULT_PROVIDERS, **(cfg.get("providers") or {})}
    routes = {**DEFAULT_ROUTES, **(cfg.get("model_routes") or {})}
    # Keep backwards compatibility with older config keys.
    if cfg.get("web_search_cmd"):
        providers.setdefault("claude_cli", {})["web_search_cmd"] = cfg.get("web_search_cmd")
    if cfg.get("web_fetch_cmd"):
        providers.setdefault("claude_cli", {})["web_fetch_cmd"] = cfg.get("web_fetch_cmd")
    return {"providers": providers, "routes": routes}


def provider(provider_id: str) -> dict:
    return registry()["providers"].get(provider_id, {})


def route_provider(stage: str) -> tuple[str, dict]:
    reg = registry()
    route = reg["routes"].get(stage) or ""
    if isinstance(route, dict):
        provider_id = str(route.get("primary") or "")
    else:
        provider_id = str(route or "")
    return provider_id, reg["providers"].get(provider_id, {})


def adapter_commands(stage: str = "research") -> dict:
    _, item = route_provider(stage)
    cfg = load_config()
    return {
        "search_cmd": os.environ.get("PPT_AGENT_SEARCH_CMD") or item.get("web_search_cmd") or cfg.get("web_search_cmd"),
        "fetch_cmd": os.environ.get("PPT_AGENT_FETCH_CMD") or item.get("web_fetch_cmd") or cfg.get("web_fetch_cmd"),
    }


def status() -> dict:
    reg = registry()
    providers = {
        provider_id: _provider_status(provider_id, item)
        for provider_id, item in reg["providers"].items()
    }
    route_status = {}
    for stage, route in reg["routes"].items():
        if isinstance(route, dict):
            provider_id = str(route.get("primary") or "")
            fallback = route.get("fallback") or []
        else:
            provider_id = str(route)
            fallback = []
        route_status[stage] = {
            "provider": provider_id,
            "primary": provider_id,
            "fallback": fallback,
            "configured": bool(providers.get(provider_id, {}).get("configured")),
            "capabilities": providers.get(provider_id, {}).get("capabilities", []),
        }
    return {"routes": route_status, "providers": providers}
