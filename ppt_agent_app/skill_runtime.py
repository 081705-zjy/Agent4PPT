from __future__ import annotations

from pathlib import Path

from .models import ROOT, read_json


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def agent_config() -> dict:
    return read_json(ROOT / "config/agents.json", {})


def stage_config() -> dict:
    return read_json(ROOT / "config/stages.json", {})


def agents() -> dict:
    return agent_config().get("agents") or {}


def get_agent(name: str | None) -> dict:
    if not name:
        return {}
    return dict(agents().get(name) or {})


def load_skill(path: str) -> dict:
    skill_path = ROOT / path
    return {
        "path": path,
        "exists": skill_path.exists(),
        "content": _read_text(skill_path),
    }


def load_agent(name: str | None) -> dict:
    cfg = get_agent(name)
    loaded = [load_skill(str(path)) for path in cfg.get("skills") or []]
    return {
        "name": name,
        **cfg,
        "loaded_skills": loaded,
        "skill_prompt": "\n\n".join(item["content"] for item in loaded if item.get("content")),
    }


def stage_specs() -> list[dict]:
    cfg = stage_config()
    specs = []
    for item in cfg.get("stages") or []:
        spec = dict(item)
        agent = load_agent(spec.get("agent"))
        spec.setdefault("model_route", agent.get("model_route"))
        spec.setdefault("tool_routes", agent.get("tool_routes") or [])
        spec.setdefault("output_artifacts", agent.get("outputs") or spec.get("outputs") or [])
        spec.setdefault("human_gate", bool(agent.get("human_gate", False)))
        spec.setdefault("review_gate", bool(agent.get("review_gate", False)))
        spec["agent_config"] = {
            "name": agent.get("name"),
            "skills": agent.get("skills") or [],
            "inputs": agent.get("inputs") or [],
            "outputs": agent.get("outputs") or [],
        }
        specs.append(spec)
    return specs


def confirmation_gates() -> list[str]:
    cfg = stage_config()
    gates = cfg.get("confirmation_gates")
    if isinstance(gates, list) and gates:
        return [str(item).upper() for item in gates]
    return ["BRIEF", "REUSE_OUTLINE", "DRAFT_ASSEMBLY", "GAP_ANALYSIS", "FINAL_ACCEPT"]


def generation_gates() -> list[str]:
    cfg = stage_config()
    gates = cfg.get("generation_gates")
    if isinstance(gates, list) and gates:
        return [str(item).upper() for item in gates]
    return ["BRIEF", "REUSE_OUTLINE", "DRAFT_ASSEMBLY", "SLIDE_REWRITE", "STYLE_UNIFICATION"]


def stage_prompt(stage: str, base_prompt: str = "") -> str:
    stage = stage.upper()
    for spec in stage_specs():
        model_route = str(spec.get("model_route") or "").upper()
        if str(spec.get("stage") or "").upper() == stage or model_route == stage:
            agent_name = spec.get("agent")
            agent = load_agent(agent_name)
            skill_prompt = agent.get("skill_prompt") or ""
            if skill_prompt:
                return f"{skill_prompt}\n\n## Runtime Task\n{base_prompt}".strip()
    return base_prompt
