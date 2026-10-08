# Codex Handoff

Current state:

- Runtime is reuse-first V2 only.
- System templates compile to `data/resources_library/template/`.
- Project generation queries `template-library-candidates.json`.
- `SLIDE_REWRITE` hydrates approved project/source assets into `visual-plan.json`.
- `RENDER` requires V2 artifacts and does not fall back to legacy generation.

Validation commands:

```bash
bash tests/test-syntax.sh
python3 -m ppt_agent_app.template_library status
python3 -m py_compile ppt_agent_app/stage_runner.py ppt_agent_app/services.py
```

Useful project checks:

```bash
jq '{current_stage, stages:[.stages[]|{stage,status,artifact_status,confirmed}]}' \
  projects/<id>/stage-state.json
jq '{slide_count, asset_bound_count}' projects/<id>/visual-plan.json
jq '{pass, expected_source_asset_count, bound_source_asset_count}' \
  projects/<id>/render-audit.json
```
