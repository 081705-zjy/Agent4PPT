# Agent Runtime Architecture

This repo now separates task instructions, agent binding, stage orchestration,
model routing, and tool routing.

## Directory Roles

```text
skills/                 stable task instructions and output contracts
agents/                 documentation for agent config conventions
config/agents.json      agent -> skills/model/tools/artifacts binding
config/stages.json      ordered stage graph and human gates
ppt_agent_app/          local App, service layer, routers, runtime loader
scripts/                generation, render, validation, and provider adapters
scripts/lib/            reusable generation/render libraries
scripts/lib/ppt_master/ vendored ppt-master template import and DrawingML export
projects/               runtime project artifacts
```

## Concept Model

```text
StageController
  -> resolves a stage from config/stages.json
  -> loads the configured agent from config/agents.json
  -> loads skill.md instructions through skill_runtime.py
  -> uses Model Router for reasoning/writing stages
  -> uses Tool Router for search/fetch/render/validation tools
  -> writes artifacts under projects/<project_id>/
  -> applies human and review gates
```

## Skill vs Agent

A skill is not a full agent. A skill is a stable instruction file.

An agent is:

```text
skill files
+ model route
+ tool routes
+ input artifacts
+ output artifacts
+ state and gates
```

This keeps prompt instructions reusable while preserving explicit runtime control.

## Current Core Agents

- `IntakeAgent`
- `ResourceAgent`
- `ResearchAgent`
- `TaskUnderstandingAgent`
- `StoryAgent`
- `OutlineAgent`
- `SlidePlannerAgent`
- `SlideCopyAgent`
- `VisualAgent`
- `TemplateStyleAgent`
- `RenderAgent`
- `ReviewAgent`
- `RevisionRouterAgent`
- `ExportAgent`
- `CodexDebugAgent`

The runtime registry is visible in the App through:

```text
GET /api/agents
```

Project-specific execution truth is visible through:

```text
GET /api/projects/<project_id>/route-summary
GET /api/projects/<project_id>/route-log
```

`/api/agents` reports configured routes. The project route log reports whether a
model or tool actually ran.

## Extension Rules

- Add or edit task behavior in `skills/<area>/...md`.
- Bind a new subtask agent in `config/agents.json`.
- Add the stage edge in `config/stages.json`.
- Put provider choices in `config/default_config.json`, not in skill files.
- Keep runtime project outputs under `projects/<project_id>/`.
- Do not place API keys, local user paths, or transient logs in skills.
