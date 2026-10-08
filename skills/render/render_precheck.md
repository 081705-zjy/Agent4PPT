# Render Precheck Skill

Last-chance audit before the deterministic RENDER tool runs. Catches issues
the renderer cannot recover from (missing assets, empty pages, copy that won't
fit, broken citation refs).

## Inputs

- `manuscript.md` — final on-slide copy.
- `visual-plan.json` — per-page visual spec and asset bindings.
- `template-binding.json` — chosen layout/style profile.
- `citations.json` — citation table.

## Output: `render-precheck.json`

```json
{
  "ok": true,
  "checks": {
    "no_empty_pages": true,
    "copy_within_budget": true,
    "all_visual_specs_present": true,
    "all_bound_assets_exist_on_disk": true,
    "citations_closed_loop": true,
    "template_binding_usable": true
  },
  "issues": [
    {
      "kind": "empty_page|copy_overflow|missing_visual_spec|missing_asset_file|dangling_citation|template_layout_missing",
      "slide_index": null,
      "detail": "..."
    }
  ],
  "recommended_action": "proceed|fix_and_rerun|escalate"
}
```

## Hard rules

- Set `ok=false` if ANY of the 6 checks fails. `recommended_action` must be
  `fix_and_rerun` or `escalate` when ok=false.
- "Copy within budget" uses cover/closing 0.32 fill and body 0.58 fill as the
  baseline (matches `quality_requirements.content_fill_target`).
- "All bound assets exist on disk" must verify the file path under
  `data/resources_library/template/` or `projects/<id>/assets/` actually exists.
- "Citations closed loop" means every `[cite:ID]` marker in manuscript.md has a
  matching entry in citations.json AND every citation in citations.json is
  referenced somewhere.
- Output strict JSON only.
