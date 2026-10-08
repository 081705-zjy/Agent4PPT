# PPT Agent V1

Local reuse-first PPT generation app. The runtime builds decks by scanning project
sources, querying a compiled template library, assembling a source-reuse draft,
filling gaps, rewriting slides, applying the basic template identity, and rendering an
editable PPTX.

## Start

```bash
bash scripts/start-app.sh --host 127.0.0.1 --port 8768
```

Open the printed URL, normally:

```text
http://127.0.0.1:8768
```

## V2 Stage Flow

```text
BRIEF -> RESOURCE_SCAN -> TEMPLATE_LIBRARY_BUILD -> TEMPLATE_LIBRARY_QUERY
-> TASK_UNDERSTANDING -> REUSE_OUTLINE -> DRAFT_ASSEMBLY -> GAP_ANALYSIS
-> GAP_RESEARCH -> SLIDE_REWRITE -> STYLE_UNIFICATION -> RENDER -> REVIEW
-> FINAL_ACCEPT
```

Old shell-pipeline entrypoints and old stage names are removed from the runtime.

## Template Library

System templates live under `templates/` and are compiled once into a hierarchical
library:

```text
templates/                  raw PPTX template/source decks
data/resources_library/template/       compiled deck/section/slide/component/asset profiles
```

Build or inspect it with:

```bash
python3 -m ppt_agent_app.template_library build --force
python3 -m ppt_agent_app.template_library status
python3 -m ppt_agent_app.template_library query --project <project_id>
```

Project generation does not copy the full library. It writes only project-specific
candidates:

```text
template-library-candidates.json
reuse-first-outline.json
draft-assembly-plan.json
slide-gap-plan.json
slide-composition.json
visual-plan.json
style-unification-plan.json
template-binding.json
deck.pptx
```

## Project Inputs

```text
projects/<project_id>/sources/      current project papers, PPTs, data, reports
projects/<project_id>/assets/       images, screenshots, logos, media
projects/<project_id>/templates/    optional project-local template references
```

`templates/basic` is the locked final identity shell. Topic templates are reusable
knowledge: narrative, slide logic, component relationships, figures, tables, citation
placement, and visual rhythm. Direct copying is allowed only after semantic audit.

## Useful Checks

```bash
bash tests/test-syntax.sh
python3 -m ppt_agent_app.template_library status
jq '{current_stage, stages:[.stages[]|{stage,status,artifact_status,confirmed}]}' \
  projects/<project_id>/stage-state.json
```

Final outputs are available through the UI downloads or:

```text
projects/<project_id>/deck.pptx
projects/<project_id>/render-audit.json
projects/<project_id>/final-report.json
```
