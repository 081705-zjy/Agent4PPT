from __future__ import annotations

import json
from pathlib import Path

from . import model_providers, route_log
from .models import now, project_dir, read_json, write_json


MAX_TEXT_CHARS = 6000


def _read_text(path: Path, max_chars: int = MAX_TEXT_CHARS) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _optional_json(pdir: Path, filename: str):
    return read_json(pdir / filename, {})


def collect_failure_context(project_id: str) -> dict:
    pdir = project_dir(project_id)
    if not pdir.exists():
        raise FileNotFoundError(project_id)
    return {
        "project_id": project_id,
        "collected_at": now(),
        "app_state": _optional_json(pdir, "app-state.json"),
        "stage_state": _optional_json(pdir, "stage-state.json"),
        "research_audit": _optional_json(pdir, "research-audit.json"),
        "run_manifest": _optional_json(pdir, "run-manifest.json"),
        "last_route_log": route_log.read(project_id, limit=80),
        "structural_validation": _read_text(pdir / "structural-validation.md"),
        "research_md_tail": _read_text(pdir / "research.md", max_chars=4000),
        "reuse_first_outline": _optional_json(pdir, "reuse-first-outline.json"),
        "model_routed_plan": _optional_json(pdir, "model-routed-plan.json"),
        "last_generation": (_optional_json(pdir, "app-state.json").get("last_generation") or {}),
    }


def _build_prompt(context: dict, apply_fix: bool) -> str:
    mode = "可以修改代码并运行必要的轻量验证" if apply_fix else "只做诊断报告，不要修改任何文件"
    return (
        "你是 ppt-agent-v1 的工程调试 Agent。请基于下面的项目失败/运行上下文定位问题。\n"
        f"执行模式：{mode}。\n"
        "要求：\n"
        "1. 判断失败属于 provider 配置、联网搜索、生成脚本、PPTX 渲染、质量审查还是 App 路由问题。\n"
        "2. 明确指出证据来自哪个 artifact 字段或文件。\n"
        "3. 如果不允许修改文件，输出可执行修复步骤和建议 patch 摘要。\n"
        "4. 如果允许修改文件，只做与本次失败直接相关的最小修改，并说明验证命令。\n"
        "5. 输出中文 Markdown，包含 Verdict、Evidence、Root Cause、Fix Plan、Verification。\n\n"
        "Failure Context JSON:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
    )


def run_codex_debug(project_id: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    apply_fix = bool(payload.get("apply_fix"))
    stage = "code_repair" if apply_fix else "pipeline_debug"
    pdir = project_dir(project_id)
    context = collect_failure_context(project_id)
    prompt = str(payload.get("prompt") or "").strip() or _build_prompt(context, apply_fix)
    result = model_providers.generate(
        project_id,
        stage,
        prompt,
        context={"failure_context": context, "apply_fix": apply_fix},
        timeout=int(payload.get("timeout") or 180),
    )
    out_dir = pdir / "devops"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "project_id": project_id,
        "generated_at": now(),
        "stage": stage,
        "apply_fix": apply_fix,
        "result": result,
        "context": context,
    }
    write_json(out_dir / "codex-debug-report.json", report)
    if result.get("output"):
        (out_dir / "codex-debug-report.md").write_text(str(result["output"]) + "\n", encoding="utf-8")
    return {
        "ok": bool(result.get("ok")),
        "project_id": project_id,
        "stage": stage,
        "apply_fix": apply_fix,
        "provider": result.get("provider"),
        "report": str(out_dir / "codex-debug-report.md"),
        "json_report": str(out_dir / "codex-debug-report.json"),
        "errors": result.get("errors") or [],
        "output": result.get("output") or "",
    }
