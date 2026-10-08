# Reuse-First Outline Skill (v3 — matched-pack only)

Generate a deck outline by reusing resources that the matching cascade
(DECK_MATCHING / SECTION_MATCHING / SLIDE_MATCHING) has already approved. **You may not invent or retrieve resources here** — every
candidate must come from `matched-resource-pack.json`.

## Inputs

- `story-strategy.json` — narrative arc, section purposes, reuse_sources per section.
- `matched-resource-pack.json` — the only place library resource_ids may come from.
- `idea-analysis.json` — deck purpose, audience, must_have_pages, expected_sections.
- `data/source-understanding.json` — must_use_materials / forbidden_resources.
- `question-state.json` — original intake; read `answers.user_outline` for
  the user's free-form outline (highest priority).

## Output: `reuse-first-outline.json`

```json
{
  "schema_version": "3.0",
  "user_outline_priority": true,
  "topic": "...",
  "slide_count": 10,
  "slides": [
    {
      "slide_index": 1,
      "target_title": "封面",
      "target_role": "cover|agenda|motivation|problem|comparison|method|result|risk|closing|content",
      "target_claim": "本页要论证的判断句（cover/agenda/closing 可为空）",
      "outline_source": "user_outline|project_sources|template_library|new_slide_placeholder",
      "source_candidates": [
        {"resource_id": "slide.<id>|asset.<id>|component.<id>|deck.<id>", "reuse_mode": "..."}
      ],
      "selected_reuse": {
        "resource_id": "slide.<id>",
        "reuse_mode": "direct_slide_reuse|partial_slide_reuse|direct_asset_reuse|redraw_from_source|adapt_structure|new_slide_placeholder",
        "allowed_use": "full|chart_structure_only|layout_only|caption_pattern_only|none",
        "forbidden_use": ["original_numbers", "original_conclusion"],
        "why_match": "..."
      },
      "gap": ["..."],
      "research_needed": ["..."]
    }
  ]
}
```

## Hard rules

- Slide count = `brief-analysis.slide_count` (also matches story-strategy length expectations).
- Every `source_candidates[*].resource_id` and `selected_reuse.resource_id` MUST appear in
  `matched-resource-pack` (any of the 5 levels). If no match exists for a page,
  set `selected_reuse.reuse_mode="new_slide_placeholder"` and `resource_id=null`.
- `selected_reuse.reuse_mode` must respect the matched-pack's `recommended_reuse_mode`
  for that resource (e.g. if matched-pack says `style_only`, you cannot pick
  `direct_slide_reuse`).
- Candidates from the user's own uploads carry `source_owner="project"` in the
  matched-pack. Prefer them over `source_owner="library"` candidates when both
  fit the same page — the project's own slides already match the topic so they
  should be reused whole whenever the matched-pack permits `direct_slide_reuse`
  or `partial_slide_reuse`.
- `selected_reuse.forbidden_use` must include everything from the matched-pack's
  `forbidden_use` array for that resource.
- If `question-state.answers.user_outline` is non-empty, slides[] order and titles
  must follow it. Set `user_outline_priority=true`.
- `gap` enumerates what this page still lacks; `research_needed` feeds
  GAP_ANALYSIS query plan.
- Output strict JSON only — no markdown fences.
