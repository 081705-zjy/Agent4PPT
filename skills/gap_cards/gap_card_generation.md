# Gap Cards Generation Skill

## v34 whole-deck scope (读此优先于 v33)

**从 v34 起, 本 skill 一次调用看整个 deck 的所有 outline slide (通常 40-60 张), 不再按
section 切分**. driver 会在 `batch_info` 里标 `{"scope": "whole_deck", "n_pages": N}`.

这样做的动机: **跨章不齐**是最常见但之前被漏掉的问题类型 (章 2 说 "CNN"、章 7 说
"卷积神经网络"、章 4 说 "深度卷积网"). 单次调用能看到全局, 才能发现并统一。

**v34 硬要求 (whole-deck 特有)**:

1. **cross-chapter term_unification 是第 1 优先级**. 扫全 50 张 slide 的
   `target_title / target_claim / key_points`, 找同一概念的不同叫法; 每对不齐都要在
   涉及的每张 slide 的 `unification_hints[]` 里写建议 (指向同一个统一名字)。
2. **metric_unification 也扩到全 deck**: Speedup / 加速比 / speedup ratio、
   tokens/J / Token/J / tokens per joule — 全 deck 统一到一种口径。
3. **title_style_unification 至少按 section 统一** (格式不齐是章内问题, 不必强求跨章)。
4. **section_coherence / transition_note / connects_from_prev / connects_to_next**
   仍按 section 局部性来判断 (章内衔接, 不必跨章)。
5. 只对 `no_supporting_material_slides` 列出的 slide 输出 `no_supporting_material:true`
   分支; 其他 slide 都出正常 unification_hints。
6. **structural/narrative audit 是硬要求**:
   - 同章内若多张 slide 复用同一个 `source_resource_id`, 必须标
     `gap_types += ["duplicate_source"]`, `rewrite_scope="full_page"` 或 `text_only`,
     并在 `must_replace/must_add` 写清楚后续如何区分两页; 不允许把重复源页当作最终可用。
   - `chapter_divider / section_divider / framework_recap / agenda / cover / closing`
     等结构页若绑定到普通内容页、论文页、结果页或方法页, 必须标
     `gap_types += ["structural_source_mismatch"]`, 并要求后续删掉源页具体内容,
     改成章节导航/框架回顾/当前位置高亮。
   - 方法章节的章首节奏要一致: 若某些章有
     `chapter_divider → framework_recap`, 其他方法章缺其中一类, 必须在该章首页
     标 `chapter_rhythm_inconsistent`, 说明后续要补结构页或把首页改成兼具结构页功能。
   - 同章并列代表工作必须同构: 例如两个 paper/work opener 后续都应采用相同节奏
     (`opener → challenge → method/solution → result` 或统一压缩版)。若一个工作缺
     method/solution 或 result, 必须标 `parallel_work_asymmetry`, 写入 `must_add`
     或 `must_replace`。
   - `matching_fallback`, `weak_match`, `weak_match_after_expansion` 必须显式标
     `semantic_gap`, `rewrite_priority="high"`, `next_action="human_intervention_required"`
     或 `slide_rewrite`; 可以 byte-clone 做草稿, 但 gap_card 必须记录它不是最终可用页。

**batch_info.scope 的两种值**:
- `"whole_deck"` (默认, v34): 一次看全 deck, 优先做 cross-chapter 统一
- `"per_section"` (fallback, v30): 只看单章, 保留 legacy 行为 (设 GAP_CARD_MODE=per_section 环境变量触发)

## v33 当前执行契约 (读此优先于下面所有 legacy 内容)

本阶段运行在 `OUTLINE_GENERATION` 之后、`DRAFT_ASSEMBLY` 之前。目标不是重新写
PPT 内容, 而是让 Claude 逐页检查: 已选源页和目标页之间有哪些**文字、术语、标题、
指标口径、讲述衔接**需要统一, 并输出后续改写/审查能直接消费的结构化卡片。

必须输出 **ONE gap_card per outline slide**, 顺序与 `outline_slides` 完全一致。

每个 gap_card 必须包含这些字段:

```json
{
  "slide_index": 1,
  "target_title": "...",
  "target_role": "...",
  "source_resource_id": "tpl.xxx.slide_03",
  "source_title": "...",
  "fit_score": 0.0,
  "reuse_fit": "direct|partial|weak|none",
  "draft_action": "copy_source_slide_as_is|placeholder|new_slide",
  "gap_required": true,
  "rewrite_scope": "none|text_only|title_only|notes_only|full_page",
  "rewrite_priority": "low|medium|high",
  "next_action": "no_action|slide_rewrite|text_rewrite|human_intervention_required",
  "gap_types": ["term_unification", "title_style_unification", "metric_unification", "semantic_gap"],
  "keep_from_source": ["full_page"],
  "must_replace": [],
  "must_remove": [],
  "must_add": [],
  "evidence_needed": [],
  "visual_needed": false,
  "unification_hints": [
    {"type": "term_unification|title_style_unification|metric_unification", "hint": "..."}
  ],
  "section_coherence": "...",
  "transition_note": "...",
  "narrative_role": "...",
  "what_this_page_says": "...",
  "how_to_present": ["...", "...", "..."],
  "connects_from_prev": "...",
  "connects_to_next": "..."
}
```

规则:

- `source_resource_id` 从当前页 rank-1 source 填; 没有 source 才为 null。
- 禁止外部检索补齐; `evidence_needed` 只记录当前 outline/source 已暴露的待确认项。
- `must_replace` / `must_remove` / `must_add` 要具体到页面元素或短句, 不要写空话。
- 对 `copy_source_slide_as_is` 页也要写清楚哪些源页元素保留、哪些文字后续需要统一。
- `narrative_role` / `what_this_page_says` / `how_to_present` / `connects_from_prev` /
  `connects_to_next` 必须可直接进入 speaker notes, 不能只写"承上启下"。

---

## v28 语义重构 (读此优先于以下所有 legacy 内容)

**v28 起 GAP 语义从"外部数据补齐"改为"多来源之间的文字/术语/风格统一化建议"**:

- 项目定位: **基于库现有资源**生成 PPT, **不允许**外部检索补齐
- gap_card 的角色不再是"发现数据缺口",而是"发现库来源多样导致的表述不统一,写出统一化建议供 SLIDE_REWRITE 消费"

**v28 gap_card 三种类型**:

1. `term_unification` — 同一概念在不同 slide 用不同名字 (如 "三层协同" vs "层次三系统"), 建议统一名字
2. `title_style_unification` — 标题格式不齐 (冒号/破折号/括号混用), 建议统一格式
3. `metric_unification` — 单位或口径不一 (Speedup vs 加速比, tokens/J vs Token/J), 建议统一

**v28 gap_card 只出 unification_hint, 不出 gap_research_hint / evidence_gap 等 legacy 字段**.

**v28 输出 schema** (简化):
```json
{
  "schema_version": "3.0",
  "gap_cards": [
    {
      "slide_index": 1,
      "target_title": "...",
      "source_resource_id": "...",
      "unification_hints": [
        {"type": "term_unification", "hint": "术语 'X' 建议统一为 'Y'"},
        {"type": "title_style_unification", "hint": "标题格式改成同章 '- 副标题' 风格"},
        {"type": "metric_unification", "hint": "'Speedup' 改成 '加速比'"}
      ],
      "next_action": "slide_rewrite"
    }
  ]
}
```

**v28 next_action 只有一个值**: `slide_rewrite` (不再有 gap_research / gap_analysis).

**扫描重点**: 对全 outline 做**全局扫描**, 找出重复概念/相似标题/口径, 汇总每张 slide 需要统一到什么规范.

---

# Legacy v2.x 内容 (以下作为**降级 fallback**, v28 环境请忽略, 优先按上方 v28 规则生成)

For each target page in outline.json, produce a structured **gap_card** that
later stages (DRAFT_REVIEW, GAP_ANALYSIS, GAP_RESEARCH, SLIDE_REWRITE) can act
on as a unified task queue.

This stage runs AFTER SLIDE_MATCHING and BEFORE SLIDE_PLAN. It synthesizes:
- the outline's expected key_points / needed_evidence per page
- the matched source slide's claim / what_this_slide_explains / text_samples
- the must_rewrite / match_reason hints from SLIDE_MATCHING
- per-chapter coverage hints from data/source-understanding.json

into ONE gap_card per page.

### v30 fix #7: no_supporting_material_slides 特殊处理

若 input 里有 `no_supporting_material_slides` 数组 (含 slide_index), 对这些 slide 走
**专属分支**, 不 fabricate 通常 gap_card:
- gap_card.no_supporting_material = true
- gap_card.unification_hints = []  (库无源, 不产生统一化 hint)
- gap_card.next_action = "human_intervention_required"
- gap_card.notes = "该 slide 库无支持材料; 已在 outline_fix_from_review 阶段建议
  (a) 删除 or (b) 改 claim 到库能支撑方向 or (c) 章级重拆. 若未处理, DRAFT_ASSEMBLY
  会渲染专属 placeholder 提示人类介入."
- 不再往这些 slide 的 gap_card 里塞任何 must_replace / must_add / evidence_needed

**为什么**: 库驱动原则要求 outline 与库对齐; 若某 slide 库无支撑, gap_card 不该假装
"缺 X 需补 Y"制造工作, 应显式承认"该 slide 需要 outline 层介入", 让人类知道要做取舍.

## Inputs

```json
{
  "outline_slides": [
    {"slide_index": 1, "target_role": "...", "target_title": "...",
     "target_claim": "...", "page_purpose": "...",
     "key_points": [...], "needed_evidence": [...],
     "anchor_terms": [...], "section_index": 1}
  ],
  "slide_matches": [
    {"target_slide_index": 1, "resource_id": "...", "source_owner": "...",
     "recommended_reuse_mode": "...", "must_rewrite": [...],
     "match_reason": "...", "confidence": 0.85}
  ],
  "source_slide_briefs": {
    "<resource_id>": {
      "title": "...", "claim": "...",
      "what_this_slide_explains": "...",
      "salient_visuals": [...], "transferable_to": [...],
      "do_not_reuse_when": [...]
    }
  },
  "section_matches": [
    {"target_section_index": 1, "resource_id": "...",
     "recommended_use": "primary_source|reference_only|style_only"}
  ],
  "project_doc_anchors": {
    "FlashOverlap": ["doc.xxx"], "KV Cache": [...]
  },
  "coverage_per_chapter": [
    {"chapter": "工程实践", "coverage_estimate": "thin",
     "gap_note": "云侧集群拓扑/SLO 实测/监控等内部材料缺失"}
  ],
  "claim_status_plan": [
    {
      "claim_or_entity": "SpecEE",
      "status": "user_claimed | inferred | external_unverified",
      "why_it_matters": "这是本组算法层代表成果, 需要数据支撑",
      "needs_later_evidence": true,
      "evidence_types_needed": ["性能加速比", "硬件平台", "对比 baseline"],
      "sensitivity_note": "未公开数据不要使用"
    }
  ]
}
```

`claim_status_plan` 来自 brief, 列出**所有命名 claim/系统/产品/方法**及其需要的证据类型。
gap_card 生成时:
- 若该 claim 出现在 page 的 key_points / claim 中 → 该 page 的 evidence_needed
  必须包含 `evidence_types_needed`, gap_types 含 `evidence_gap`
- 若 `needs_later_evidence=true` 但 page 没有可用 source → 必须开 `next_action=gap_research`

## Output: `gap-cards.json` (strict JSON)

```json
{
  "schema_version": "2.0",
  "gap_cards": [
    {
      "slide_index": 1,
      "target_title": "...",
      "target_role": "cover|agenda|motivation|...|references",
      "source_resource_id": "tpl.xxx.slide_03 | null",
      "source_title": "...",
      "fit_score": 0.72,
      "reuse_fit": "direct|partial|weak|none",
      "draft_action": "copy_source_slide_as_is|placeholder|new_slide",
      "gap_required": true,
      "rewrite_scope": "text_only|text_and_visual|restructure|find_new_source",
      "rewrite_priority": "high|medium|low",
      "next_action": "text_rewrite|gap_research|new_visual|internal_material_request|no_action",
      "gap_types": [
        "metadata_gap|agenda_gap|semantic_gap|evidence_gap|visual_gap|conflict_gap|continuity_gap|internal_material_gap"
      ],
      "keep_from_source": ["layout", "visual_rhythm", "..."],
      "must_replace": ["title", "speaker", "date"],
      "must_remove": ["old_project_name", "old_metric_X"],
      "must_add": ["current_topic", "六层框架定位"],
      "evidence_needed": ["近 3 年 token 量级统计"],
      "visual_needed": false,
      "section_coherence": "continuous|intra_section_jump|cross_deck_intentional|cross_deck_forced",
      "transition_note": "(仅 cross_deck_* 时) 与上下页 deck 不同，是否需要风格过渡 (≤40 字)",

      "narrative_role": "本页在整篇 50 页汇报中扮演什么角色 (≤80 字)",
      "what_this_page_says": "本页要讲清楚的内容 (≤140 字, 写得让讲者打开 PPT 直接照念也能讲明白)",
      "how_to_present": [
        "第 1 步: ... (≤40 字)",
        "第 2 步: ...",
        "第 3 步: ..."
      ],
      "connects_from_prev": "与上一页的逻辑衔接 (≤50 字)",
      "connects_to_next": "为下一页铺垫什么 (≤50 字)"
    }
  ]
}
```

## gap_types 取值（7 类）

- `metadata_gap` — 标题/作者/日期/机构等元信息需替换
- `agenda_gap` — 目录结构与目标大纲不一致
- `semantic_gap` — 源页主题与目标页只部分相关，标题/claim 需改写
- `evidence_gap` — 缺数据/论文/实验结果, 进 gap_research
- `visual_gap` — 缺目标图（如六层框架图、定位坐标图），需新建/重绘
- `conflict_gap` — 源页有与目标冲突的信息（错误数字/品牌/产品名）, 必须删/替
- `continuity_gap` — 单页可用但上下衔接差, 需调顺序或补过渡页
- `internal_material_gap` — 缺课题组内部材料（拓扑/监控/部署）, 走 internal_material_request

## reuse_fit 与 draft_action 取值组合

| draft_action | reuse_fit | 渲染行为 |
|---|---|---|
| copy_source_slide_as_is | direct | 1:1 整页粘贴 |
| copy_source_slide_as_is | partial | 整页粘贴 + 顶部黄色警告条 "⚠ 部分适配, 后续需改写" |
| copy_source_slide_as_is | weak | 整页粘贴 + 顶部红色警告条 "⚠ 弱相关, 仅作为参考" |
| placeholder | none | 渲染 Gap Page 卡片 |
| new_slide | none | 渲染 Gap Page 卡片 |

## narrative 字段写作规范 (重要)

`narrative_role` / `what_this_page_says` / `how_to_present[]` /
`connects_from_prev` / `connects_to_next` 这 5 个字段是讲者打开 PPT 后看到
的演讲脚本基础。必须真正展开,不要套话。

- `narrative_role`: 答 "本页为什么必须出现, 删了会缺失什么"。
  - ✅ "代表性成果第 5 页:用 SpecEE 端到端实测延时数据落地算法层投机族成果"
  - ❌ "讲一下 SpecEE 性能"

- `what_this_page_says`: 答 "如果只能看这页内容, 听众应该带走什么"。
  ≤140 字, 要够讲者直接念。
  - ✅ "SpecEE 在 A100/4060 上分别取得 2.25× / 2.17× 加速,
      展示算法层早退判定 + 投机回退在保证一致性前提下的吞吐收益, 验证算法层杠杆假设。"
  - ❌ "讲 SpecEE 的性能"

- `how_to_present[]`: 给 3 步讲解路径, 每步 ≤40 字, 必须可操作:
  - ✅ ["先指标题点出 SpecEE 名称", "解读两个加速数字与硬件档位",
        "回扣本组算法层投机族成果矩阵"]
  - ❌ ["讲清楚", "展开介绍", "总结"]

- `connects_from_prev` / `connects_to_next`: 答 "前一页/下一页是什么 + 怎么过渡"。
  - ✅ "前页讲投机解码总览, 本页给出 SpecEE 实测落地"
  - ❌ "承上启下"

## Hard rules

- Output ONE gap_card per outline page. Length must equal outline.slide_count.
- 顺序与 outline.slides[] 完全一致。
- 当 slide_match.resource_id 为空 → `draft_action="placeholder"`,
  `reuse_fit="none"`, `gap_required=true`, `source_resource_id=null`。
- `fit_score`: 0.0-1.0 你自己估算 (基于源页 claim 与目标页 key_points 的覆盖度)。
  - ≥ 0.8 → reuse_fit=direct
  - 0.6-0.8 → reuse_fit=partial
  - < 0.6 → reuse_fit=weak
- `gap_required=true` 当 reuse_fit ∈ {partial, weak, none} 或有任意非空 must_replace/must_remove/must_add/evidence_needed/visual_needed。
- `next_action` 必须对得上 gap_types:
  - 含 evidence_gap → next_action=gap_research
  - 含 visual_gap 且不含 evidence_gap → next_action=new_visual
  - 含 internal_material_gap → next_action=internal_material_request
  - 只含 metadata_gap / agenda_gap / semantic_gap → next_action=text_rewrite
  - 全 none → next_action=no_action
- `must_replace` / `must_remove` / `must_add` 必须具体, 不能写 "需要改写" 这种空话:
  - ✅ `"must_replace": ["主标题", "作者署名", "汇报日期"]`
  - ❌ `"must_replace": ["相关信息"]`
- `evidence_needed` 必须具体到能拿去 web search:
  - ✅ `["近 3 年主流大模型 token 量级统计 (Anthropic/OpenAI/Google)"]`
  - ❌ `["数据"]`
- **(Phase O, 2026-06-27): 若 outline.slides[i] 含 `gap_research_hint` (非空)**:
  把这条 hint 视作该页 evidence_gap 的种子, 优先纳入 `evidence_needed` 列表 (可加工细化, 但不要丢弃)。
- **(Phase O): 若 outline.slides[i] 含 `source_resource_ids` (非空 list)**:
  说明 OUTLINE 已为该页代码预分配资源, gap_card 应假设这些资源会被 SLIDE_REWRITE 用到 — 不要把
  它们再列为 internal_material_gap。
- 中文项目用中文, 英文项目用英文。
- Output strict JSON only — no markdown fences, no prose.
