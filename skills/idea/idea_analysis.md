# IDEA Analysis — Narrative And Chapter Plan Only (v6.2)

## Purpose

生成 `idea-analysis.json`。本阶段只负责高层叙事和章节规划，不负责页级大纲，也不绑定具体 source slide。

**阶段边界**:
- ✅ 选择主叙事: `logic/deck_level` unified patterns
- ✅ 规划章节: chapter role、chapter purpose、章间关系、粗略页数
- ✅ 规划并列章节契约: 对同一 `parallel_group_id` 输出 canonical skeleton、页数范围和 work block 模板
- ✅ 每章选择一个 `logic/section_level` rhythm pattern
- ✅ 从 `material` 的 deck/section 级候选中给出 `material_section_hints`
- ✅ 遵守 `rule/logic_story` 中的叙事、章节、结构规则
- ✅ 输出 deck-level `structural_page_contract`: 明确封面、总目录、每章分目录必须在 OUTLINE 主流程中 source-backed byte-clone
- ✅ 只使用逻辑/故事规则和 section 级材料池，不使用页级 source 信息
- ❌ 不生成 `slide_stubs`
- ❌ 不输出 `chapter_page_count`
- ❌ 不使用或引用 `rule/page_specific`
- ❌ 不输出 `target_title` / `target_claim` / `key_points`
- ❌ 不输出 `source_resource_ids` / `source_slide_id`
- ❌ 不选择具体 slide

后续责任:
- `OUTLINE_GENERATION Stage 1a`: 基于本阶段的章节意图 + structural_page_contract + section hints + `logic/section_level` + `rule/page_specific` 生成每章 `slide_stubs`; 每个业务章的第一张 stub 必须是 `section_divider`
- `OUTLINE_GENERATION Stage 1b`: 加载 `material/*/slide` briefs, 为每页写 detail 并绑定真实 source slide
- `GAP_CARD_GENERATION`: 只记录 clone 后需要改写/统一的术语、风格、标题、指标口径
- `DRAFT_ASSEMBLY`: 只 byte-clone 已绑定的 material slides

本阶段必须自己把边界做对，不要依赖后面的修复环节兜底。

## Inputs

```json
{
  "intake_light": {},
  "resource_library_contract": {},
  "deck_level_patterns": [],
  "recommended_deck_task_patterns": [],
  "logic_story_hard_rules_summary": [],
  "rhythm_patterns_per_role": {
    "method": [
      {
        "pattern_id": "...",
        "source_count": 3,
        "applicable_summary": "...",
        "abstract_node_sequence_brief": "...",
        "typical_page_count": 5
      }
    ]
  },
  "library_understanding": {
    "total_relevant_slides_estimate": 120,
    "relevant_sections_count": 18,
    "hierarchy": {
      "top_decks": [
        {
          "deck_id": "...",
          "deck_title": "...",
          "报告类型": "...",
          "主题标签": [],
          "score": 8.5,
          "n_relevant_slides": 22
        }
      ],
      "sections_by_deck": {
        "<deck_id>": [
          {
            "section_id": "...",
            "section_title": "...",
            "section_role": "method",
            "n_slides_in_pool": 6,
            "score": 3.2
          }
        ]
      }
    },
    "relevant_section_ids": [],
    "cascade_keywords_used": []
  },
  "story_design_mode_hint": "AUTO|STRICT|SOFT"
}
```

## Data Usage

Use the optimized libraries this way:

- `logic/deck_level`: unified whole-deck reasoning layer.
  - `pattern_kind=deck_task`: decide the deck's thinking task, such as technical tutorial, research review, proposal, or decision memo. This is the former meta layer.
  - `pattern_kind=deck_arc`: choose the whole-deck narrative arc and chapter-role sequence.
- `logic/section_level`: choose exactly one rhythm pattern per chapter by role.
- `material/decks-index.json`, `material/decks/*/deck.json`, `material/decks/*/section.json`: choose deck/section-level material hints and estimate capacity.
- `material/decks/*/slide.*`: do not use in this stage.
- `rule/logic_story`: obey story, chapter ordering, role boundary, transition, parallel-chapter, and structural-promise rules.
- `rule/page_specific`: do not use in this stage.

## Structural Page Contract

IDEA must declare structural pages, but must not pick slide IDs.

- Slide 1 is `cover`.
- Slide 2 is `agenda`.
- Every business chapter in `chapter_plan` starts with `section_divider`, including closing.
- `cover`, `agenda`, and `section_divider` are normal OUTLINE pages, not post-processing inserts.
- OUTLINE must bind them to real structural source slides before DRAFT byte-clone.
- Agenda and section dividers should reuse one agenda/divider source template; later text recolor differentiates total agenda vs current-chapter agenda.
- Do not count cover/agenda/section_divider as content evidence pages when estimating chapter material support.

## ID Namespace Contract

Keep these ID spaces separate:

- `selected_meta_pattern.id` is a compatibility field and may use only IDs from `deck_level_patterns` where `pattern_kind == "deck_task"`.
- `provenance.referenced_meta_pattern_ids[]` is also compatibility provenance; fill it with the chosen `deck_task` ID.
- `selected_narrative_arc.primary_pattern_id`, `selected_narrative_arc.borrowed_patterns[].pattern_id`, and `provenance.referenced_pattern_ids[]` may use only IDs from `deck_level_patterns` where `pattern_kind == "deck_arc"`.
- `chapter_plan[].section_rhythm_pattern_id` and `provenance.referenced_rhythm_pattern_ids[]` may use only IDs from `rhythm_patterns_per_role`.
- Never put a `deck_task` ID into `selected_narrative_arc.borrowed_patterns[]`. If a deck task influenced the design, record it only in `selected_meta_pattern` / `provenance.referenced_meta_pattern_ids[]`.

## Required Reasoning

1. Read `intake_light` and infer the presentation task, audience, topic, expected depth, and constraints.
2. Select one `deck_task` pattern and one `deck_arc` pattern from unified `deck_level_patterns`. Borrow at most two secondary `deck_arc` patterns only when needed.
3. Use `library_understanding.hierarchy.top_decks` and `sections_by_deck` to understand what the material library can support.
4. Design chapters from the available section-level material, not from idealized training-memory structure.
5. For each chapter, pick one `section_rhythm_pattern_id` from `rhythm_patterns_per_role[section_role]`.
6. For each chapter, fill `material_section_hints` with section-level candidates only.
7. Identify parallel chapter groups when multiple method/result/engineering chapters unfold the same framework.
8. Write bridge hints when adjacent chapters need explicit narrative handoff.
9. Add `requires_section_divider=true` and `structural_prefix_role="section_divider"` to every business chapter.
10. For every parallel group, output `parallel_group_contracts[]` with comparable page budgets, canonical chapter skeleton, canonical work block template, and source-scope constraints.
11. Before output, silently run the IDEA self-check below and fix the JSON yourself.

## IDEA Self-Check Before Output

Your first output should already satisfy the stage quality gate without relying on a later Codex repair loop. Do this self-check before returning JSON:

1. **ID validity**: verify every pattern ID is in the correct namespace from `ID Namespace Contract`.
2. **Optional sections are single-axis**: every `discussion` / `outlook` / `background` optional chapter must focus on one dominant axis. Do not mix industry benchmarking, future paradigms, edge, GPU, cross-domain networking, and deployment in one outlook chapter. Pick one axis that naturally emerges from earlier method/engineering chapters.
3. **Cross-section hooks coverage**: for N chapters, `narrative_constraints.cross_section_hooks` must contain at least `N-2` useful hooks. Include adjacent handoffs for important transitions, especially framework -> method, method -> method inside a parallel group, method -> engineering/outlook, and outlook -> closing.
4. **Closing callback**: the final `closing` chapter must explicitly paraphrase the deck topic / `core_message` / cover title anchor. It may thank, sign off, and invite collaboration, but it must not be only contact information.
5. **Closing no-new-content**: closing must not introduce new methods, new results, or new data. It only summarizes, recalls the thesis, thanks, and gives contact/collaboration touchpoints.
6. **Parallel chapters same logic**: chapters in the same `parallel_group_id` must have comparable purpose logic and comparable claim structure, using the same framework terms.
7. **Parallel group contract present**: if two or more chapters share `parallel_group_id`, `parallel_group_contracts[]` must contain that group. Page budget ranges must overlap, canonical skeleton must be identical, and work block template must be identical.
8. **Framework chapter remains global**: framework chapter claims must describe the deck-level axis (e.g. algorithm-system-hardware), not a single layer, single work, or narrow technique such as sparse attention.
9. **Provenance complete enough**: fill `referenced_meta_pattern_ids`, `referenced_pattern_ids`, `referenced_rhythm_pattern_ids`, and at least five `referenced_rule_ids_followed` that you actually used.
10. **Structural contract present**: `structural_page_contract` must require cover at slide 1, agenda at slide 2, and section_divider before each business chapter. Every `chapter_plan[]` item must carry `requires_section_divider=true`.
11. **Review issue prevention**: specifically prevent the known IDEA failures: deck_task IDs leaking into deck_arc borrowed patterns, multi-axis outlook/discussion chapters, sparse transition hooks, closing chapters that only show contact info, missing structural contract, asymmetric parallel chapters, framework narrowed to one layer/work, and missing rhythm/rule provenance.

## Output Schema

Return strict JSON only:

```json
{
  "schema_version": "6.1",
  "identity": {
    "topic": "...",
    "language": "zh",
    "slide_count_target": 30,
    "duration_minutes": 30,
    "audience": {
      "primary": "...",
      "expected_depth": "...",
      "tolerance_for_jargon": "..."
    },
    "topic_tags": [],
    "anchor_terms": []
  },
  "presentation_goal": "...",
  "core_message": "...",
  "story_design_mode": "AUTO|STRICT|SOFT",
  "structural_page_contract": {
    "cover": {
      "required": true,
      "position": 1,
      "target_role": "cover",
      "source_policy": "byte_clone_structural_source"
    },
    "agenda": {
      "required": true,
      "position": 2,
      "target_role": "agenda",
      "source_policy": "byte_clone_structural_source",
      "highlight_mode": "all_chapters_black"
    },
    "section_dividers": {
      "required": true,
      "before_each_business_chapter": true,
      "target_role": "section_divider",
      "source_policy": "reuse_agenda_or_divider_structural_source",
      "highlight_mode": "current_chapter_black_others_white"
    }
  },
  "selected_meta_pattern": {
    "id": "...",
    "title": "...",
    "why_chosen": "...",
    "invariant_principles": []
  },
  "selected_narrative_arc": {
    "primary_pattern_id": "...",
    "borrowed_patterns": [
      {"pattern_id": "...", "borrowed_for": "..."}
    ],
    "narrative_arc": [],
    "abstract_node_sequence": [],
    "why_chosen": "...",
    "selection_mode": "top1_reuse|top1_with_borrowed|top5_synthesized"
  },
  "parallel_group_contracts": [
    {
      "parallel_group_id": "layered_representative_works",
      "member_section_indices": [3, 4, 5],
      "canonical_page_budget": {
        "target_pages_per_chapter": 10,
        "allowed_delta_pages": 2,
        "allowed_delta_ratio": 0.2
      },
      "canonical_chapter_skeleton": [
        "section_divider",
        "framework_anchor_current_layer",
        "chapter_scope_overview",
        "work_block_1.paper_intro",
        "work_block_1.challenge",
        "work_block_1.method",
        "work_block_1.result",
        "work_block_2.paper_intro",
        "work_block_2.challenge",
        "work_block_2.method",
        "work_block_2.result",
        "chapter_summary_to_framework"
      ],
      "canonical_work_block_template": ["paper_intro", "challenge", "method", "result"],
      "framework_anchor_policy": {
        "same_source_required": true,
        "source_scope": "global_or_chapter_framework",
        "only_change": ["current_layer_highlight", "title", "text"]
      },
      "source_scope_policy": {
        "global_or_group_recap_targets_cannot_use_single_work_summary": true,
        "work_block_sources_must_match_work_name": true
      },
      "rationale": "..."
    }
  ],
  "chapter_plan": [
    {
      "section_index": 1,
      "chapter": "...",
      "section_role": "cover|agenda|section_divider|motivation|background|problem|framework|method|comparison|result|experiment|engineering|discussion|outlook|closing|references|appendix|content",
      "purpose": "...",
      "expected_pages_indicative": 3,
      "expected_pages_range": [2, 4],
      "may_be_revised_by_outline": true,
      "requires_section_divider": true,
      "structural_prefix_role": "section_divider",
      "claims_to_make": [],
      "claims_to_setup_for_later": [],
      "section_rhythm_pattern_id": "...",
      "section_rhythm_summary": "...",
      "section_rhythm_source_count": 3,
      "material_section_hints": [
        {
          "deck_id": "...",
          "deck_title": "...",
          "section_id": "...",
          "section_title": "...",
          "section_role": "...",
          "expected_slide_capacity": 6,
          "reason": "..."
        }
      ],
      "parallel_group_id": null,
      "parallel_group_terminology": null,
      "chapter_bridge_hint": {
        "in_from_prev_chapter": null,
        "out_to_next_chapter": null
      }
    }
  ],
  "narrative_constraints": {
    "thesis_callback": {
      "raise_at_chapter": 2,
      "callback_at_chapters": [],
      "thesis": "..."
    },
    "anchor_term_trajectory": [],
    "framework_anchor_repeat": {
      "anchor": "...",
      "repeat_at_chapters": []
    },
    "cross_section_hooks": [],
    "anti_patterns_to_avoid": []
  },
  "reuse_strategy": {
    "target_reuse_rate": 0.8,
    "must_keep_terms": [],
    "scope_keywords": []
  },
  "provenance": {
    "schema_version": "6.1",
    "intake_light_path": "idea-intake-light.json",
    "referenced_meta_pattern_ids": [],
    "referenced_pattern_ids": [],
    "referenced_rhythm_pattern_ids": [],
    "referenced_rule_ids_followed": [],
    "library_pool_section_ids": [],
    "section_inclusion_rationale": {},
    "rule_relaxed_with_reason": []
  }
}
```

## Hard Rules

1. Output strict JSON only.
2. `schema_version` must be `"6.1"`.
3. Every chapter must have `section_index`, `chapter`, `section_role`, `purpose`, `expected_pages_indicative`, `section_rhythm_pattern_id`, and `material_section_hints`.
4. `section_rhythm_pattern_id` must be selected from `rhythm_patterns_per_role[section_role]`.
5. `expected_pages_indicative` is rough capacity only. Do not produce precise per-slide count.
6. `material_section_hints` may include only deck/section-level fields. Do not include slide ids, slide titles, or slide claims.
7. Chapter titles must use real domain terms from intake or material deck/section titles, not placeholders like "工作一" or "方法二".
8. Method/result/engineering chapters in the same parallel group must use consistent terminology and comparable narrative logic.
9. Framework chapters may name dimensions but must not enumerate every representative work's page-level claim.
10. Closing/outlook owns future vision; discussion owns a single discussion axis. Do not duplicate them.
11. Claims can mention concrete work names only when they are visible in deck/section-level material or intake. If unsure, use abstract direction instead.
12. Do not write meta instructions inside content fields, such as "下游再填", "由 OUTLINE 决定", or "source 反查后补".
13. `selected_narrative_arc.borrowed_patterns[]` must contain only `deck_arc` pattern IDs, never `deck_task` IDs.
14. Optional chapters must be single-axis and must naturally emerge from earlier chapter `claims_to_setup_for_later`.
15. `cross_section_hooks` must cover most chapter transitions: at least `chapter_plan.length - 2` hooks, with explicit method-chain and closing handoffs.
16. Closing `claims_to_make` must include a thesis/title callback using the same anchor terms as `identity.topic` / `core_message`, while introducing no new evidence.
17. `provenance.referenced_rule_ids_followed` must include actual `logic_story` rule IDs that influenced the design, not generic placeholders.
18. `structural_page_contract.cover.required`, `.agenda.required`, and `.section_dividers.required` must all be true.
19. Every business chapter in `chapter_plan[]` must set `requires_section_divider=true` and `structural_prefix_role="section_divider"`.
20. Do not create separate cover/agenda chapters just to satisfy structure. Cover and agenda are deck-level structural pages; content chapters remain business chapters.
21. If a `parallel_group_id` appears in two or more chapters, `parallel_group_contracts[]` must include it and every member chapter must fit its canonical skeleton and page budget.
22. Framework chapters must not narrow the deck-level framework to one concrete layer, source deck, work, or technique. They can name layer dimensions but cannot make the framework page about sparse attention, one paper, one accelerator, or one student/work stream.

## Forbidden Output

If any of these appear, the output is invalid:

- `slide_stubs`
- `chapter_page_count`
- `page_to_rhythm_node_map`
- `rhythm_adherence` at page level
- `referenced_archetype_ids`
- `page_specific_archetypes`
- `target_title`
- `target_claim`
- `key_points`
- `source_resource_ids`
- `source_slide_id`
- `slides_by_section`
- `library_pool_slide_ids`
