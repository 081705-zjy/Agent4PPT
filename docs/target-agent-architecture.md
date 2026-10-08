# Target Agent Architecture

The target architecture is the active reuse-first V2 pipeline.

| Stage | Agent | Primary Outputs |
| --- | --- | --- |
| BRIEF | IntakeAgent | `question-state.json`, `project-outline-input.json` |
| RESOURCE_SCAN | ResourceAgent | `resource-index.json`, `source-digest.json`, `asset-catalog.json` |
| TEMPLATE_LIBRARY_BUILD | TemplateLibraryBuildAgent | `data/resources_library/template/manifest.json` |
| TEMPLATE_LIBRARY_QUERY | TemplateLibraryQueryAgent | `template-library-candidates.json` |
| TASK_UNDERSTANDING | TaskUnderstandingAgent | `task-analysis.json`, `material-selection.json` |
| REUSE_OUTLINE | ReuseOutlineAgent | `reuse-first-outline.json`, `model-routed-plan.json` |
| DRAFT_ASSEMBLY | DraftAssemblyAgent | `draft-assembly-plan.json`, `draft-deck.pptx` |
| GAP_ANALYSIS | GapAnalysisAgent | `slide-gap-plan.json` |
| GAP_RESEARCH | GapResearchAgent | `gap-research-results.json`, `citations.json` |
| SLIDE_REWRITE | SlideRewriteAgent | `slide-composition.json`, `manuscript.md`, `visual-plan.json` |
| STYLE_UNIFICATION | StyleUnificationAgent | `style-unification-plan.json`, `template-binding.json` |
| RENDER | RenderAgent | `deck.pptx`, `render-log.md`, `structural-validation.md`, `render-audit.json` |
| REVIEW | ReviewAgent | `review-report.json` |
| FINAL_ACCEPT | ExportAgent | `final-report.json` |

The app rejects removed stage names. The renderer does not call a separate
topic-to-deck generator as fallback.
