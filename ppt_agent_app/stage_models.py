"""Per-stage model execution layer.

Wraps the existing model router so any stage can run "skill-injected prompt -> model ->
parsed artifact" with a uniform result shape. Every call is routed through
``model_providers.generate`` (so it is mockable in tests and reports unavailable providers
uniformly). Callers decide whether ``ok=False`` is recoverable; the core planning/copy/
visual stages treat it as a hard stop so low-quality local fallbacks do not silently
replace model reasoning.
"""

from __future__ import annotations

import os

from . import model_providers, skill_runtime, stage_controller
from .models import ROOT, read_json


def model_routing_enabled() -> bool:
    """Whether stages should call the model router. Env var ``PPT_AGENT_MODEL_ROUTING``
    (1/0) overrides the config default — used to force deterministic, credential-free runs
    (e.g. test suites, sandboxes without working providers) regardless of config."""
    override = os.environ.get("PPT_AGENT_MODEL_ROUTING")
    if override is not None and override.strip() != "":
        return override.strip().lower() in {"1", "true", "yes", "on"}
    cfg = read_json(ROOT / "config/default_config.json", {})
    return bool(cfg.get("enable_model_routed_generation", False))


def _model_route(project_id: str, stage: str) -> str | None:
    spec = stage_controller.stage_item(project_id, stage)
    route = spec.get("model_route")
    return str(route) if route else None


def generate_artifact(
    project_id: str,
    stage: str,
    base_prompt: str,
    context: dict | None = None,
    parse: str = "text",
) -> dict:
    """Run ``stage`` through its configured model route with its skills injected.

    Returns ``{"ok": True, "text"/"data": ..., "provider": ...}`` on success, or
    ``{"ok": False, "reason": ...}`` when the route is missing, the model is unavailable,
    or (for ``parse="json"``) the output is not a JSON object.
    """
    stage = stage.upper()
    # Opt-in gate: when model routing is disabled, model-authored stages should stop or
    # use an explicit legacy path chosen by the caller.
    if not model_routing_enabled():
        return {"ok": False, "reason": "model routing disabled"}
    route = _model_route(project_id, stage)
    if not route:
        return {"ok": False, "reason": "stage has no model route"}

    prompt = skill_runtime.stage_prompt(stage, base_prompt)
    result = model_providers.generate(project_id, route, prompt, context=context or {})
    if not result.get("ok"):
        return {"ok": False, "reason": "model unavailable", "errors": result.get("errors") or []}

    output = str(result.get("output") or "").strip()
    provider = result.get("provider")
    if parse == "json":
        from .services import _extract_json_object  # lazy: avoid import cycle

        data = _extract_json_object(output)
        if not isinstance(data, dict) or not data:
            return {"ok": False, "reason": "model output was not a JSON object", "raw": output, "provider": provider}
        return {"ok": True, "data": data, "provider": provider, "raw": output}
    return {"ok": True, "text": output, "provider": provider, "raw": output}
