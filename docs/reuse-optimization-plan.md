# Reuse Optimization

Superseded by `docs/reuse-first-generation-plan.md`.

Current implementation uses `ppt_agent_app/template_library.py` and
`data/resources_library/template/` as the system-level hierarchical template library. Project
generation writes `template-library-candidates.json` and reuse decisions in V2
artifacts instead of per-project template registries.
