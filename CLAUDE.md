# CLAUDE.md — ppt-agent

This repository now uses the App-managed reuse-first V2 pipeline only. Do not run or
recreate the removed shell orchestrator.

## Runtime

- `scripts/start-app.sh` starts the browser UI/API.
- `ppt_agent_app/` owns project services, stage execution, model/tool routing, and
  API endpoints.
- `config/stages.json` is the stage graph source of truth.
- `config/agents.json` binds stages to skills, model routes, tool routes, inputs,
  outputs, and gates.
- `ppt_agent_app/template_library.py` compiles and queries `templates/`.
- `scripts/export-pptx.sh` renders/validates editable PPTX output.

## Stage Flow

```text
BRIEF -> RESOURCE_SCAN -> TEMPLATE_LIBRARY_BUILD -> TEMPLATE_LIBRARY_QUERY
-> TASK_UNDERSTANDING -> REUSE_OUTLINE -> DRAFT_ASSEMBLY -> GAP_ANALYSIS
-> GAP_RESEARCH -> SLIDE_REWRITE -> STYLE_UNIFICATION -> RENDER -> REVIEW
-> FINAL_ACCEPT
```

## Operating Rules

- Use the UI/API or `stage_runner.run_stage()` for generation.
- Build/query the template library with `python3 -m ppt_agent_app.template_library`.
- Keep project materials in `projects/<id>/sources`, `assets`, and optional
  project-local `templates`.
- Do not fabricate paper results, performance data, citations, or source figures.
- Preserve source lineage in `visual-plan.json.assets`, citations, and final review
  artifacts.
- If rendering fails, repair the earliest V2 artifact that caused the failure. Do not
  fall back to a separate topic-to-deck generator.

## Validation

```bash
bash tests/test-syntax.sh
python3 -m py_compile ppt_agent_app/stage_runner.py ppt_agent_app/services.py
python3 -m ppt_agent_app.template_library status
```

For real projects, inspect:

```text
projects/<id>/stage-state.json
projects/<id>/visual-plan.json
projects/<id>/render-audit.json
projects/<id>/final-report.json
projects/<id>/deck.pptx
```
