# Draft Assembly Plan Skill

Decide HOW each slide gets physically assembled in the draft pass. This is the
Claude planning step before the deterministic DRAFT_ASSEMBLY tool runs.

The DRAFT pass is FULL-COPY-FIRST: when a slide is a `direct_slide_reuse`, the
draft deck must paste the original source slide verbatim so the user can visually
confirm the reuse decision. Only later rewrite stages remove or replace any of the
copied content.

## Inputs

- `slide-plan.json` — per-page intent.
- `reuse-decision-audit.json` — what reuse is approved with what constraints.
- `matched-resource-pack.json` — resource locations and metadata.
- `project-asset-catalog.json` — project-side assets available.
- `project-slide-units.json` (optional) — slide-level units extracted from the
  user's uploaded PPTs for the current project.

## Output: `draft-assembly-plan.json`

```json
{
  "slides": [
    {
      "slide_index": 8,
      "draft_action": "direct_slide_reuse|partial_slide_reuse|direct_asset_reuse|redraw_from_source|adapt_structure|new_slide_placeholder",
      "source_resource_id": "slide.<id>|asset.<id>|null",
      "source_slide_svg_ref": "svg/slide_05.svg",
      "source_asset_refs": [
        {"asset_resource_id": "asset.<id>", "asset_path": "assets/image91.png", "source_bbox_emu": [914400, 1828800, 4572000, 2743200]}
      ],
      "keep": ["overall_layout", "right_side_chart_position", "annotation_style"],
      "replace": ["title", "claim", "chart_data", "caption"],
      "placeholder_slots": [
        "updated_evidence_source",
        "new_chart_values"
      ],
      "asset_bindings": [
        {"asset_resource_id": "...", "intended_position": "left_pane|right_pane|hero|inset"}
      ],
      "rewrite_instructions": [
        "verify topic/claim/object/caption/context",
        "rewrite visible text for current project"
      ]
    }
  ]
}
```

## Field guidance

- `source_slide_svg_ref` — REQUIRED when `draft_action` is `direct_slide_reuse`
  or `partial_slide_reuse`. Path is relative to the resource import dir, e.g.
  `svg/slide_05.svg` for a template-library slide, or
  `decomposed/<deck_id>/svg/slide_03.svg` for a project upload. The renderer
  uses this to paste the source slide directly.
- `source_asset_refs` — REQUIRED when `draft_action` is `direct_asset_reuse`.
  Each entry must include `asset_path` (relative to the same import dir) and
  ideally `source_bbox_emu` `[x, y, width, height]` in EMU units so the
  renderer can drop the asset at its source position.
- `draft_action` cardinality:
  - `direct_slide_reuse`: paste source slide verbatim (DRAFT only). Later
    SLIDE_REWRITE may replace text regions.
  - `partial_slide_reuse`: source slide is the base, but DRAFT will already
    overlay project-specific title/body in `replace` regions.
  - `direct_asset_reuse`: keep one or more source assets, redraw the rest.
  - `redraw_from_source` / `adapt_structure` / `new_slide_placeholder`: no
    direct paste — the renderer composes from scratch.

## Hard rules

- `source_resource_id` must appear in `reuse-decision-audit.approved_resource_ids`
  (or be null for `new_slide_placeholder`).
- `keep` items must respect `reuse-decision-audit.allowed_use` for the
  resource; `replace` items must include everything in
  `reuse-decision-audit.not_allowed`.
- Asset bindings must point to either approved library assets or
  `project-asset-catalog` entries.
- `placeholder_slots` enumerates what DRAFT_ASSEMBLY tool must mark as TODO
  for the later evidence/rewrite passes.
- For `direct_slide_reuse` / `partial_slide_reuse` the DRAFT pass copies the
  full source slide. Do NOT pre-strip text in the plan — that is the rewrite
  stage's job. The plan only declares INTENT.
- Output strict JSON only.
