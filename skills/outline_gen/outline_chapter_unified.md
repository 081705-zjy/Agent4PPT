# OUTLINE Chapter Unified — One-Claude Per Chapter

## Purpose

Use one Claude call for one chapter. In this single call, do the chapter work in order:

1. Plan the chapter skeleton.
2. Choose source slides from the provided candidate pools.
3. Fill every slide detail.
4. Self-check that the output can enter byte-clone drafting.

The runner already prepared candidate pools from the current libraries. Do not ask for more context and do not invent source ids.

## Inputs

The input JSON contains:

- `chapter`: one `idea-analysis.chapter_plan[]` item.
- `deck_contract`: compact global constraints from IDEA.
- `selected_rhythm_pattern`: logic rhythm pattern for this chapter.
- `page_specific_archetypes`: allowed rule/page archetype ids.
- `narrative_constraints_slice`: only the narrative constraints for this chapter.
- `library_candidate_sections`: material sections selected or inherited for this chapter.
- `candidate_pool_summary`: local summary of the candidate pool.
- `candidate_slide_briefs`: real material slide candidates. Every source id must come from here.
- `structural_candidate_slide_briefs`: real cover/agenda/divider/closing candidates if the chapter needs structural pages.
- `candidate_pool_stats`: section grouping and section summaries.
- `parallel_group_context`: sibling chapter contract when this chapter is part of a parallel group.
- `intake_constraints`: anchor and must-keep terms.
- `project_evidence_briefs`: compact project evidence.

## Responsibility Boundary

You own:

- Chapter page count.
- `chapter_decomposition`.
- `stubs`.
- Per-slide `target_title`, `target_claim`, `key_points`, `source_resource_ids`, `alternates`, `gap_status`, and `delivery_hint`.
- Matching abstract chapter intent to real library material.

You do not own:

- Changing IDEA chapter order or global chapter roles.
- Inventing new materials.
- Leaving content for GAP to research.
- Creating post-processing-only cover, agenda, or divider pages.

## Required Method

Work internally in four phases, but output one JSON object only.

### Phase A — Read The Chapter Contract

Identify:

- chapter role and purpose;
- expected page budget;
- required section divider;
- whether the chapter is part of a parallel group;
- the sibling rhythm/work-block contract;
- which claims are framework-level and which are concrete work-level.

If `parallel_group_context.contract` exists, it is a hard constraint. Page count, framework anchor position, and representative work block template must be comparable to siblings.

### Phase B — Build The Skeleton

Create `chapter_decomposition` and `stubs`.

Rules:

- If `chapter.requires_section_divider=true`, `stubs[0]` must be a `section_divider`.
- A content opener must be real content, not another agenda/contents page.
- A framework/general chapter must stay at framework level. Do not drop into a single algorithm or a single paper unless the chapter is explicitly a work block.
- For repeated representative works, use one template for every work block, such as `paper_intro -> challenge -> method -> result` or the same compressed version for all blocks.
- Do not declare “3 main lines” unless the following stubs actually expand all three lines.
- `subline.name` and `abstract_topics` must be grounded in `candidate_pool_summary` or `candidate_slide_briefs`.

### Phase C — Bind Sources

For each stub, choose top-1 source from `candidate_slide_briefs` or `structural_candidate_slide_briefs`.

Hard rules:

- Every final slide must have non-empty `source_resource_ids`.
- `source_resource_ids[].slide_id` must exist in the provided candidates.
- Content pages cannot use cover, TOC, agenda, section navigation, ending, or references sources.
- Structural pages can only use structural sources.
- Different target pages should not reuse the same top-1 source. Only agenda/divider/framework-template reuse may share a source, and then `same_source_intent.allowed=true` is required.
- Overview/framework pages must use sources with matching object scope. A personal defense, student plan, or single-paper summary cannot become a lab/group/global framework page.
- A framework source cannot be narrower than the target framework claim.
- A work block must stay on the same concrete work. Do not introduce one work, then suddenly bind method/result pages from another work.
- Result/benchmark pages must bind result/benchmark sources for the same work or use neutral wording.

Selection priority:

1. Same section continuous reuse if it supports the claims.
2. Same deck/same work for a work block.
3. Role and object-scope match.
4. Claim direction match.
5. Visual skeleton match.

### Phase D — Self-Check

Before output, check:

- slide count equals `page_count`;
- each slide has `source_resource_ids`;
- no content page is written as a navigation page;
- no repeated top-1 source unless explicitly allowed;
- parallel chapter/work-block contract is followed;
- `chapter_realized.coverage_status` is not `critical_missing`;
- all page roles and archetypes are valid for the chapter.

If a candidate is weak but still the best real option, narrow the target title/claim to what the source actually supports. Do not output `new`, `matching_fallback`, `no_match`, or empty source.

## Output

Strict JSON only:

```json
{
  "chapter_index": 4,
  "chapter_title": "...",
  "rhythm_pattern_id": "...",
  "page_count": 8,
  "chapter_decomposition": {
    "axis": "...",
    "sublines": [
      {"index": 1, "name": "...", "abstract_topics": ["..."]}
    ],
    "rationale": "..."
  },
  "stubs": [
    {
      "slide_index_in_chapter": 1,
      "target_role": "section_divider",
      "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"],
      "archetype_placement": "section_open",
      "page_purpose_hint": "分目录页: 高亮当前章",
      "belongs_to_subline_index": null
    }
  ],
  "work_blocks": [
    {
      "block_index": 1,
      "work_name": "...",
      "template": ["paper_intro", "challenge", "method", "result"],
      "stub_indices": [3, 4, 5, 6],
      "source_scope": "single_work"
    }
  ],
  "parallel_group_adherence": {
    "parallel_group_id": "...",
    "canonical_chapter_skeleton_followed": true,
    "canonical_work_block_template_followed": true,
    "page_budget_within_delta": true,
    "notes": ""
  },
  "page_to_rhythm_node_map": [null, 0, 1],
  "rhythm_adherence": {
    "rhythm_node_count": 5,
    "slide_count": 8,
    "expansion_ratio": 1.6,
    "skipped_rhythm_nodes": []
  },
  "chapter_realized": {
    "summary": "...",
    "realized_specifics": ["..."],
    "coverage_status": "full",
    "subline_coverage": [],
    "drift_from_intent": {
      "abstract_intent": "...",
      "missing_from_source": [],
      "added_from_source": [],
      "drift_severity": "none"
    }
  },
  "slides": [
    {
      "slide_index_in_chapter": 1,
      "target_role": "section_divider",
      "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"],
      "archetype_placement": "section_open",
      "target_title": "...",
      "target_claim": "...",
      "key_points": ["..."],
      "needed_evidence": [],
      "anchor_terms": [],
      "source_resource_ids": [
        {
          "deck_id": "...",
          "slide_id": "...",
          "section_id": "...",
          "deck_title": "...",
          "rank_score": 1.0,
          "_tier": 1,
          "match_reasons": ["..."]
        }
      ],
      "alternates": [],
      "source_carrier_resource_kind": "carrier_bound",
      "kind": "carrier_bound",
      "gap_status": "ok",
      "style_unification_hint": null,
      "same_source_intent": null,
      "slide_binding_audit": {
        "target_layer_inferred": "structural",
        "source_layer_inferred": "structural",
        "layer_aligned": true,
        "rejected_top1": null
      },
      "claim_status_link": {
        "maps_to_chapter_claim_idx": null,
        "is_setup_for_later": false,
        "is_thesis_callback": false
      },
      "delivery_hint": "..."
    }
  ],
  "self_check": {
    "all_slides_source_backed": true,
    "no_navigation_source_for_content": true,
    "duplicate_source_checked": true,
    "parallel_contract_checked": true,
    "notes": []
  }
}
```

## Hard Rules

1. Output JSON only.
2. `slides.length == page_count == stubs.length`.
3. Slide fields copied from the matching stub must stay consistent.
4. Every slide must have `source_resource_ids`.
5. Do not output `matching_fallback`, `new`, `no_match`, or `not_applicable`.
6. Do not invent `slide_id`.
7. Do not use a skeleton/agenda page as a content page.
8. Do not use a personal or single-work overview as a lab/global overview.
9. Parallel chapters and repeated work blocks must use comparable logic.
10. Keep all claims grounded in the selected source slides.
