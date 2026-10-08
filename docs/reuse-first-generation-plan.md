# Reuse-First PPT Generation V2 Plan

## 0. Non-Negotiable Direction

This version replaces the old generation path. The app should no longer treat
source/template reuse as a late visual-planning option. It should build a deck by
first reusing existing narrative structures, pages, figures, tables, and slide
logic, then identify gaps, then rewrite and unify style.

Old behavior to remove as a fallback:

- Do not silently continue with deterministic outline fallback when model output
  fails.
- Do not use "generate an abstract new deck first, bind assets later" as the
  primary path.
- Do not let RENDER regenerate missing planning artifacts through legacy
  topic-autogen or fixed components.
- Do not use project-local full template KB copies.
- Do not treat topic templates as only style inspiration.

Compatibility rule:

- Runtime execution has no old-pipeline fallback. Historical/manual scripts may
  exist for reference, but app stages, UI buttons, API stage execution, and
  render preflight consume V2 artifacts only.
- Existing render backend code can remain as an implementation detail, but it
  must render from reuse-first manuscript, visual, lineage, and style artifacts.

## 1. New Stage Graph

Target stage order:

1. `BRIEF`
   - User provides topic, audience, slide count, duration, citation policy,
     reuse policy, and optional user outline.
   - Output: `question-state.json`, `project-outline-input.json`.

2. `RESOURCE_SCAN`
   - Scan only current project `sources/` and `assets/`.
   - Build source digest, asset catalog, visual reference index.
   - Output: `resource-index.json`, `source-digest.json`,
     `asset-catalog.json`, `visual-reference-index.json`,
     `chart-candidates.json`.

3. `TEMPLATE_LIBRARY_BUILD`
   - Compile `templates/basic` and `templates/topic` into a system-level
     hierarchical library.
   - Only templates in the repo are handled in this first version. Feishu sync
     roots are deferred.
   - Output: `data/resources_library/template/*`.

4. `TEMPLATE_LIBRARY_QUERY`
   - Query the hierarchical library using topic, audience, deck type,
     user outline, source digest, and reuse policy.
   - Output: `template-library-candidates.json`.

5. `TASK_UNDERSTANDING`
   - Interpret the user task, source boundaries, confidentiality constraints,
     citation policy, and reuse aggressiveness.
   - Output: `task-analysis.json`, `material-selection.json`.

6. `REUSE_OUTLINE`
   - Generate the target deck outline with source/template lineage for every
     planned page.
   - If user outline exists, it has priority. The system may clean structure and
     fill gaps, but must not replace the user's outline with a new story.
   - Output: `reuse-first-outline.json`, `story-strategy.md`,
     `model-routed-plan.json`.

7. `DRAFT_ASSEMBLY`
   - Create a draft deck plan and draft artifacts by copying or partially
     reusing existing slides/assets/components where appropriate.
   - This draft may have placeholders and mixed styles.
   - Output: `draft-assembly-plan.json`, `draft-manuscript.md`,
     `draft-visual-plan.json`, `draft-deck.pptx`.

8. `GAP_ANALYSIS`
   - Audit the draft per slide.
   - Identify missing evidence, misleading copied content, needed rewrites,
     citation gaps, sensitive content, and target research queries.
   - Output: `slide-gap-plan.json`.

9. `GAP_RESEARCH`
   - Run targeted research only for gaps.
   - Output: `gap-research-results.json`, `research.md`, `citations.json`,
     `research-audit.json`, `per-slide-evidence-pack.json`.

10. `SLIDE_REWRITE`
    - Rewrite slide copy and composition from draft lineage + gaps + evidence.
    - Preserve source lineage and reuse decisions.
    - Output: `slide-composition.json`, `manuscript.md`, `visual-plan.json`.

11. `STYLE_UNIFICATION`
    - Apply `templates/basic` as the identity shell and normalize typography,
      footer, citations, title rules, and layout rhythm.
    - Do not erase approved source figures/tables/slides.
    - Output: `style-unification-plan.json`, `template-binding.json`,
      `style-profile.json`.

12. `RENDER`
    - Render final deck from reuse-first artifacts.
    - Output: `deck.pptx`, `render-log.md`, `structural-validation.md`,
      `render-audit.json`.

13. `REVIEW`
    - Review content, source lineage, citation policy, visual quality, and
      structural validation.
    - Output: `deck-review.md`, `review-report.json`.

14. `FINAL_ACCEPT`
    - Final acceptance report.
    - Output: `final-report.json`.

## 2. Template Library Schema

System directory:

```text
data/resources_library/template/
  manifest.json
  deck-profiles.json
  section-profiles.json
  slide-profiles.json
  component-profiles.json
  asset-profiles.json
  citation-profiles.json
  narrative-patterns.json
  search-index.json
  imports/
  assets/
```

Deck profile:

```json
{
  "deck_id": "tpl.topic.paper_share.hash",
  "source_path": "templates/topic/paper_share/example.pptx",
  "template_scope": "topic",
  "template_type": "paper_share",
  "topic_summary": "...",
  "audience": ["..."],
  "scenario": "...",
  "deck_type": "...",
  "narrative_arc": ["motivation", "gap", "method", "result", "takeaway"],
  "sections": ["section_id"],
  "slides": ["slide_id"],
  "reuse_policy": {
    "direct_slide_reuse_default": "semantic_audit_required",
    "asset_copy_default": "semantic_audit_required",
    "style_copy_default": "allowed"
  }
}
```

Section profile:

```json
{
  "section_id": "tpl.xxx.sec.02",
  "deck_id": "tpl.xxx",
  "section_index": 2,
  "role": "method",
  "summary": "...",
  "narrative_function": "turn problem framing into technical mechanism",
  "slide_ids": ["tpl.xxx.slide_07"]
}
```

Slide profile:

```json
{
  "slide_id": "tpl.xxx.slide_07",
  "deck_id": "tpl.xxx",
  "section_id": "tpl.xxx.sec.02",
  "slide_index": 7,
  "slide_role": "mechanism_explanation",
  "claim": "...",
  "what_this_slide_explains": "...",
  "visual_logic": "...",
  "component_ids": ["cmp_id"],
  "asset_ids": ["asset_id"],
  "citation_ids": ["citation_id"],
  "reuse_modes": [
    "direct_slide_reuse",
    "partial_slide_reuse",
    "redraw_from_source",
    "adapt_structure",
    "style_only",
    "reject"
  ],
  "reuse_risks": ["..."]
}
```

Component profile:

```json
{
  "component_id": "tpl.xxx.slide_07.cmp.01",
  "slide_id": "tpl.xxx.slide_07",
  "component_type": "diagram",
  "meaning": "what this diagram/table/text block explains",
  "relations": ["supports claim", "contrasts with right panel"],
  "reuse_policy": "redraw_or_direct_after_audit",
  "asset_ids": ["asset_id"]
}
```

Asset profile:

```json
{
  "asset_id": "tpl.xxx.slide_07.asset.image157",
  "slide_id": "tpl.xxx.slide_07",
  "asset_type": "raster_image",
  "path": "data/resources_library/template/assets/...",
  "meaning": "what the image proves or illustrates",
  "caption_or_ocr": "...",
  "direct_reuse_risk": "low|medium|high",
  "reuse_policy": "direct_if_same_topic_claim_object_caption_context"
}
```

## 3. Build Command

New command:

```bash
python3 -m ppt_agent_app.template_library build
python3 -m ppt_agent_app.template_library status
python3 -m ppt_agent_app.template_library query --project <id>
```

First implementation:

- Sources: repo-local `templates/**/*.pptx`.
- Hash-based incremental rebuild.
- Import artifacts from existing template import/KB functions when possible.
- Deterministic structural extraction first.
- Claude semantic analysis skill can be added as a second pass, but the schema
  and command must exist now.

## 4. User Outline Contract

New artifact: `project-outline-input.json`.

```json
{
  "schema_version": "1.0",
  "user_outline": "",
  "required_sources": [],
  "forbidden_sources": [],
  "reuse_preference": "aggressive",
  "allow_draft_style_mismatch": true,
  "citation_policy": "",
  "direct_slide_reuse_policy": "allowed_with_audit"
}
```

Rules:

- User outline has priority over template-derived story.
- Template library can suggest missing sections, ordering, and source matches.
- If user outline conflicts with sources, emit a gap/risk instead of silently
  changing the outline.

## 5. Reuse-First Outline Contract

Artifact: `reuse-first-outline.json`.

Every slide must include:

- `slide_index`
- `target_title`
- `target_role`
- `target_claim`
- `outline_source`: `user_outline|template_library|project_sources|model`
- `source_candidates`
- `selected_reuse`
- `gap`
- `research_needed`

Allowed `selected_reuse.mode`:

- `direct_slide_reuse`
- `partial_slide_reuse`
- `direct_asset_reuse`
- `redraw_from_source`
- `adapt_structure`
- `new_slide_placeholder`

## 6. Draft Assembly Contract

Artifact: `draft-assembly-plan.json`.

Every slide must include:

- `draft_action`
- `source_lineage`
- `copied_slide_refs`
- `copied_asset_refs`
- `placeholder_slots`
- `rewrite_instructions`
- `gap_notes`
- `speaker_note_feedback`

Outputs:

- `draft-manuscript.md`
- `draft-visual-plan.json`
- `draft-deck.pptx`

The draft deck is allowed to be incomplete and visually inconsistent.

## 7. Gap Analysis Contract

Artifact: `slide-gap-plan.json`.

Every slide must include:

- `current_state`
- `narrative_gaps`
- `evidence_gaps`
- `visual_gaps`
- `citation_gaps`
- `sensitivity_risks`
- `reuse_risks`
- `research_queries`
- `rewrite_plan`

Research must be driven by these gaps.

## 8. Final Artifacts Must Preserve Lineage

Final `visual-plan.json`, `manuscript.md`, and `model-routed-plan.json` must
preserve:

- `source_lineage`
- `reuse_decisions`
- `approved_assets`
- `rejected_assets`
- `gap_resolution`

The final deck should still pass structural validation, but a high-quality deck
is not allowed to hide where its content came from.

## 9. UI Changes

Main buttons:

1. Confirm Brief
2. Scan Project Resources
3. Build Template Library
4. Query Template Library
5. Understand Task
6. Generate Reuse-First Outline
7. Assemble Draft Deck
8. Analyze Gaps
9. Research Gaps
10. Rewrite Slides
11. Unify Style
12. Render Final PPT
13. Review

Remove old UI actions:

- "旧入口：异步生成 PPT"
- old "生成页面计划/证据包" as a main action
- old "模板组件 / 复用确认" text that says images are not directly copied

New panels:

- User outline input.
- Template library candidates.
- Reuse-first outline viewer/editor.
- Draft deck download and draft gap notes.
- Slide lineage / reuse decision table.

## 10. Iteration Strategy

Implementation is complete only when:

1. The new stage graph is the active graph.
2. `run_stage()` recognizes all new stages.
3. `RESOURCE_SCAN` no longer queries any old template cache as the main path.
4. `template_library build/status/query` works on repo `templates`.
5. A project can produce `reuse-first-outline.json`.
6. A project can produce `draft-assembly-plan.json` and `draft-deck.pptx`.
7. Gap analysis produces per-slide research queries.
8. Final render consumes the new artifacts and passes validation.

## 11. Detailed Implementation Checklist

This checklist is the active migration plan for replacing the old generation
path. The first release only analyzes repo-local `templates/`; Feishu/cloud-disk
sync is deliberately deferred.

### Phase A. Lock the V2 Contract

- `config/stages.json` and `stage_controller.DEFAULT_STAGES` use only:
  `BRIEF -> RESOURCE_SCAN -> TEMPLATE_LIBRARY_BUILD ->
  TEMPLATE_LIBRARY_QUERY -> TASK_UNDERSTANDING -> REUSE_OUTLINE ->
  DRAFT_ASSEMBLY -> GAP_ANALYSIS -> GAP_RESEARCH -> SLIDE_REWRITE ->
  STYLE_UNIFICATION -> RENDER -> REVIEW -> FINAL_ACCEPT`.
- Normal UI buttons call only these stages.
- Legacy stage names from the pre-V2 workflow are not default workflow stages
  and are rejected by stage execution unless they are explicitly reintroduced
  into the V2 stage graph.
- `skill_runtime` fallback gates, API helpers, and UI labels must use V2 names
  even when config files are missing.
- Render preflight validates missing artifacts and fails; it must not synthesize
  an old deck plan.

### Phase B. Hierarchical Template Library

- `python3 -m ppt_agent_app.template_library build` scans
  `templates/**/*.pptx`.
- Each source PPT is imported once into `data/resources_library/template/imports/`.
- The library writes deck, section, slide, component, asset, citation, narrative
  pattern, and search-index artifacts.
- Every profile keeps stable ids, source path, slide index, text samples,
  visual logic, assets, and reuse policy.
- Incremental rebuild is driven by PPT hash, schema version, importer version,
  and analyzer version.
- Current first-pass analyzer is deterministic and repo-local. A later semantic
  analyzer/Claude skill can enrich summaries, but the build command must be
  useful without Feishu or external network.

### Phase C. Reuse-First Outline

- User outline has priority. It can be normalized, but not silently replaced.
- Candidate selection ranks project source pages/images/charts and template
  slides in one queue.
- Project sources receive priority when they match the page title, claim,
  scenario, or required source hints.
- Template slides contribute deck narrative, page role, layout logic, and visual
  rhythm. They are not automatically chosen ahead of project evidence.
- The same template slide should not be selected repeatedly unless the page is
  cover/closing or the user explicitly requires it.
- Non-cover pages should penalize cover/closing examples; role-specific pages
  should prefer motivation/problem/method/result/visual-evidence matches.
- Every planned slide must carry `selected_reuse`, `source_candidates`,
  `outline_source`, and gap/research hints. A slide with a suitable local source
  should not degrade to a generic generated layout.

### Phase D. Draft Assembly

- The draft deck is allowed to mix styles, contain placeholders, and show TODO
  notes.
- Each slide must keep `source_lineage`, selected reuse mode, copied slide refs,
  copied asset refs, placeholder slots, and rewrite instructions.
- Project source figures and source slide SVGs can be bound directly to draft
  visual plans after semantic audit fields are present.
- Template pages are normally `adapt_structure`; direct template page copy
  requires the same topic/object/claim/caption/source-context audit.
- `draft-visual-plan.json` must preserve source asset metadata: path,
  asset_type, source deck, source slide index, caption/context, approval status,
  and intended slide.
- If a source PPT page is selected, the draft should show it as a page-level
  evidence visual instead of replacing it with a generic matrix.

### Phase E. Gap-Driven Research

- `GAP_ANALYSIS` decides what is missing per slide after the draft exists.
- `GAP_RESEARCH` uses only those gap queries plus user citation policy.
- Existing teacher PPTs, public papers, reports, and group results keep their
  source lineage. Internal/cooperation practice is labeled conservatively.
- Research is supplemental; it should not replace already suitable local
  sources.
- Gaps distinguish narrative gap, evidence gap, visual gap, citation gap, and
  sensitivity risk. Research queries are generated only for unresolved gaps.

### Phase F. Rewrite and Final Style Pass

- `SLIDE_REWRITE` rewrites visible text, claims, labels, citations, and speaker
  notes from the draft and gap plan.
- `STYLE_UNIFICATION` applies `templates/basic` as the identity shell only:
  typography, title rule, footer, page number, citation format, and cover/ending
  shell.
- Approved source figures/tables/PPT page visuals must remain traceable through
  `source_lineage` and `reuse_decisions`.
- `SLIDE_REWRITE` must hydrate approved assets from either the draft visual plan
  or the outline `selected_reuse`; running this stage must not drop source
  images/pages.
- The final `visual-plan.json` should include `assets`, `image_decision`,
  `asset_request`, `source_lineage`, and `reuse_decisions` per slide.

### Phase G. Quality Gates

- `RENDER` must fail if required V2 artifacts are missing.
- `REVIEW` routes V2 issue dimensions to V2 stages:
  fact/citation -> `GAP_RESEARCH`, source usage/content -> `SLIDE_REWRITE`,
  layout/style -> `STYLE_UNIFICATION`, structural -> `RENDER`,
  outline/story -> `REUSE_OUTLINE`, draft/gaps -> `DRAFT_ASSEMBLY` or
  `GAP_ANALYSIS`.
- `FINAL_ACCEPT` requires a real PPTX, structural validation, acceptable
  editability, and render audit pass.
- Render audit checks source reuse coverage, repetitive layout risk, missing
  approved assets, and basic PPTX existence/editability.

### Phase H. Cleanup Rules

- Project directories no longer receive full template KB copies.
- Old registry artifacts and old API aliases are removed from the app runtime.
  Historical scripts/docs can stay only if clearly marked manual/reference and
  not called by app code.
- UI labels and panels should talk about "层级模板库 / 复用大纲 / 草稿 /
  gap / 风格统一", not old component picking.
- Redundant buttons that trigger old stages are removed from the default UI.

### Phase I. Validation and Iteration

- Run `python3 -m ppt_agent_app.template_library build/status`.
- Run Python syntax checks for changed app modules and render helpers.
- Run a deterministic V2 smoke project through:
  `RESOURCE_SCAN -> TEMPLATE_LIBRARY_BUILD -> TEMPLATE_LIBRARY_QUERY ->
  TASK_UNDERSTANDING -> REUSE_OUTLINE -> DRAFT_ASSEMBLY -> GAP_ANALYSIS ->
  GAP_RESEARCH -> SLIDE_REWRITE -> STYLE_UNIFICATION -> RENDER -> REVIEW ->
  FINAL_ACCEPT`.
- Verify the smoke deck has a real `deck.pptx`, `draft-deck.pptx`, `final-report`
  ready status, and at least one approved source asset when project sources
  contain reusable PPT/images.
- For the real onboarding project, verify `reuse-first-outline.json` source
  counts and final `visual-plan.json.asset_bound_count` before rendering.
