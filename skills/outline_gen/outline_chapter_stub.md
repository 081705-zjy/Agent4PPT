# OUTLINE Chapter Stub — Per-Chapter Skeleton (Stage 1a, v33)

## Purpose

接 **idea-analysis.json 里的 1 个 chapter** + 当前 material/logic/rule grounding, 输出 **该章的 slide stub 骨架**:
每张 slide 的 `slide_index_in_chapter` / `target_role` / `archetype` / `archetype_placement` /
`page_purpose_hint`。

**任务边界**:
- ✅ 决定该章 N 张 slide 的**数量 / role 序列 / archetype 序列 / 每页一句话用途**
- ✅ 结合 `candidate_section_slide_count_hint` 与 `narrative_constraints_slice` 调整页数
- ✅ 若 `chapter.requires_section_divider=true`, 把本章第 1 张 stub 生成为正式 `section_divider`
- ❌ **不写** target_claim / key_points / source_resource_ids / needed_evidence / anchor_terms /
  delivery_hint (那是 Stage 1b `outline_slide_detail.md` 的事)
- ❌ **不动** chapter_plan / narrative_constraints (上游 IDEA 已定)
- ❌ **不要假设这些 stubs 是最终稿**。下游 OUTLINE 会再次按当前库重验并可能重排、删减或替换。

**为什么 Stage 1a 单独**:
- 验证章页数 (e.g. method 章必须 5-10 页, 不能 1 页或 20 页)
- 验证 archetype 序列符合 IDEA 给的 rhythm pattern abstract_node_sequence
- 验证 archetype 合法 (在 page_specific rule 枚举 54 条内)
- 早 catch 章数/role/archetype 错误, 不浪费 Stage 1b 算力

**架构**: per chapter 独立 → driver 8 章并行调本 skill 8 次 → code merge + 重编 slide_index.

---

## Inputs

```json
{
  "chapter": {              // 1 个 chapter (full context from idea-analysis.chapter_plan[i])
    "section_index": 4,
    "chapter": "算法层协同·稀疏·量化·解码",
    "section_role": "method",
    "purpose": "...",
    "expected_pages_indicative": 8,
    "may_be_revised_by_outline": true,
    "claims_to_make": [...],
    "claims_to_setup_for_later": [...],
    // v28: claims_pending_data 已弃 (库驱动生成, 不允许"待补外部数据")
    "section_rhythm_pattern_id": "method_framework_recap_then_papers_...",  // v4.0 单字符串
    "section_rhythm_summary": "<≤80 字>",
    "section_rhythm_source_count": 9,
    "requires_section_divider": true,
    "structural_prefix_role": "section_divider",
    "source_carrier_resource_kind": "carrier_bound"
  },
  "structural_page_contract": {
    "cover": {"required": true, "position": 1, "source_policy": "byte_clone_structural_source"},
    "agenda": {"required": true, "position": 2, "source_policy": "byte_clone_structural_source"},
    "section_dividers": {
      "required": true,
      "before_each_content_chapter": true,
      "before_each_business_chapter": true,
      "source_policy": "reuse_agenda_or_divider_structural_source"
    }
  },
  "selected_rhythm_pattern": {        // 该章选用的 rhythm (来自 logic/section_level/)
    "pattern_id": "method_framework_recap_then_papers_then_summary",
    "abstract_node_sequence": [
      "framework_recap",
      "paper_1_intro",
      "paper_1_method",
      "paper_1_result",
      "paper_2_intro",
      ...,
      "chapter_summary_callback"
    ],
    "applicable_summary": "..."
  },
  "page_specific_archetypes": [        // 54 个 archetype 枚举 (来自 rule/page_specific/INDEX.json)
    {
      "id": "three_layer_framework_recap_across_chapters",
      "category": "visual",
      "applicable_role": ["content_candidate"],
      "summary": "framework 章用底向上层叠图标层名"
    },
    ...
  ],
  "narrative_constraints_slice": {      // 该章相关 (slice_narrative_for_chapter)
    "thesis_raise_at_this_chapter": false,
    "thesis_callback_at_this_chapter": true,
    "framework_anchor_repeat_at_this_chapter": true,
    "cross_section_hooks_from_prev": {...},
    "cross_section_hooks_to_next": {...},
    "anchor_terms_must_appear_in_this_chapter": [...]
  },
  "candidate_section_slide_count_hint": {   // 该章 candidate 各 section 的实际 page_count
    "<section_id>": <int>,
    ...
  },
  "parallel_group_context": {
    "group_id": "layered_representative_works",
    "terminology": {},
    "sibling_chapters": [],
    "contract": {
      "canonical_page_budget": {"target_pages_per_chapter": 10, "allowed_delta_pages": 2},
      "canonical_chapter_skeleton": ["section_divider", "framework_anchor_current_layer", "..."],
      "canonical_work_block_template": ["paper_intro", "challenge", "method", "result"],
      "framework_anchor_policy": {"same_source_required": true}
    }
  }
}
```

---

## Optional Inputs — Codex Review Redo Mode (v4.4)

如果 `chapter` 含以下字段, 表示本次是 codex 触发的**大纲回滚** (Stage 1b 之前 missing source):

```json
{
  ...standard chapter fields...,
  "_decomp_redo_round": 1,    // 第几次回滚 (1/2/3)
  "_prior_chapter_decomposition": {  // 上一次 Stage 1a 给的 decomp (现在被 codex 否决)
    "axis": "...",
    "sublines": [{"index": 1, "name": "调度与服务框架", ...}, ...],
    "rationale": "..."
  },
  "_prior_coverage_status": "subline_missing | critical_missing",
  "_prior_missing_sublines": ["调度与服务框架", "通信与并行"],  // coverage=missing 的 subline 名
  "_codex_review_hints": [
    {"category": "chapter_decomposition_misaligned",
     "explanation": "...",
     "suggested_fix": "..."}
  ]
}
```

**redo 规则 (HARD)**:

1. **禁止保留** `_prior_missing_sublines` 中任一 subline 的 name 或同义 axis. 例:
   - prior missing = `["调度与服务框架"]` → 新 sublines **不允许**含 "调度" / "服务框架" / "调度方案" 等同义词
   - 必须**砍掉**或**换 axis** (换到资源库实际有的方向)

2. **可选改动方式 (从优到劣选)**:
   - A) 砍掉 missing subline + 重分配该 subline 原 stub 页数到剩余 subline (subline 总数 -1, 每剩余 subline +1-2 张 stub)
   - B) 砍掉 missing subline + 整章总页数同步减少
   - C) 砍掉 missing subline + 换轴: 整个 chapter_decomposition 重做, 选 _codex_review_hints.suggested_fix 中提示的"资源库实际有的方向"

3. **rationale 必填** (≥40 字): 说明哪些 subline 被砍/换 + 为什么. 引用 `_codex_review_hints[i].suggested_fix`. 例:
   ```
   "rationale": "依据 codex round 1 反馈, 原 subline '调度与服务框架' 资源库无对应 source,
                 砍掉该 subline; 改为 2 subline 结构 (通信与并行 / 算子与 KV cache, 资源库已实证),
                 stub 数量从 9 → 6"
   ```

4. **页数调整**: 若砍 subline, 整章 page_count 也要降 (per subline 砍 2-3 张). 整章 page_count 偏离 IDEA expected_pages_indicative **更多** 允许 (±30% 而非 ±20%, redo 模式放宽).

5. **chapter_decomposition.rationale 必含 codex_redo=true 标记**, 让下游 review 知道这是回滚后的版本.

---

## Task

per chapter, 决定:

### Step 0 (v20, 条件跳过) — 并列章对齐 + 章间桥接

**快速判断**: 若 `chapter.parallel_group_id == null` AND `chapter.chapter_bridge_hint == null` → **直接跳过 Step 0, 进 Step 1**。这是绝大多数章的情况。

**若 `chapter.parallel_group_id` 非空** (并列章):
- archetype 序列必须遵循 `parallel_group_context.sibling_chapters` 里 sibling 的模式(整体对称)
- `page_purpose_hint` 术语必须用 `parallel_group_terminology.canonical`, 禁用 `.deprecated` 里的词
- 若 `parallel_group_context.contract` 存在, 它是硬约束:
  - `page_count` 必须接近 `canonical_page_budget.target_pages_per_chapter`, 差距不得超过 allowed_delta
  - `stubs[]` 必须按 `canonical_chapter_skeleton` 实例化
  - 每个代表工作 block 必须使用 `canonical_work_block_template`
  - 输出 `work_blocks[]`, 每个 block 标明 `work_name`, `template`, `stub_indices`

**若 `chapter.chapter_bridge_hint` 非空**:
- `in_from_prev_chapter` 非空 → 章首插一张 `target_role="transition"`, `archetype=["chapter_bridge_in"]` stub
- `out_to_next_chapter` 非空 → 章末插一张 `target_role="transition"`, `archetype=["chapter_bridge_out"]` stub

(framework 章反写已移除, 由骨架 review 阶段 L2-12 issue 兜底触发 redo)

---

### Step 0.5 (v34 HARD) — 主体方法章 canonical rhythm 先定后写

**适用**: deck 中有 ≥2 个 method/result/engineering/comparison 主体章, 或这些章共同展开同一个
framework 的不同层/不同代表工作。

**硬规则**:

1. **先推断全 deck 主体章 canonical rhythm**:
   - 若任一主体章需要 `chapter_divider` / `section_divider` / `agenda progress` /
     `framework_recap` 作为章首方位锚, 则所有 sibling 主体章都必须有同类方位锚。
   - 若某一章采用 `chapter_divider → framework_recap → content...`, 其他主体章也应采用同构开头;
     只改变当前章标题、高亮层、当前 agenda item。

2. **不能只给后面章节 divider/framework_recap**:
   - 例如 ch6 有 chapter_divider + framework_recap, ch4/ch5 直接进入内容页 → 不允许。
   - 解决方式: 给 ch4/ch5 补同构结构页, 或把 ch6 的 divider/framework_recap 合并/降级, 让全组一致。

3. **代表工作 block 模板先定**:
   - 同一章含 ≥2 个代表工作/论文 opener 时, 先选择 canonical work-block template:
     `paper-cover → challenge → method → result` 或压缩版 `paper-cover → challenge → result`。
   - 每个 work block 必须按同一模板展开。若资源库只支持某个工作 2 页, 其他 work 也同步压缩,
     或把该工作改为非并列辅助项。

4. **输出痕迹**:
   - 在 `chapter_decomposition.rationale` 中写明本章采用的主体章 rhythm / work-block template。
   - 若为了全组一致而增删结构页, rationale 必须说明 "canonical_method_chapter_rhythm=true"。

**对应 logic_story rules**:
- `method_chapter_structural_rhythm_consistency`
- `parallel_representative_work_blocks_same_template`

**v36 补充: 内容 opener 必须是真内容, 不能是第二张目录页**:
- deck 已有总目录页和章前分目录页时, 方法章 / outlook 章内部不要再生成
  "目录 / Contents / agenda / 进入本章 / 三主线导览" 这类空导航内容页。
- `section_open` 的第一张内容页必须是本章真实立靶页: framework zoom、baseline/prior
  work、代表工作 paper cover、challenge setup 或研究问题。
- 若一个并列方法章的代表工作 opener 使用 paper cover, 其他并列方法章的对应
  代表工作也应使用同类 opener；不要一章用论文页, 另一章用目录页或泛泛导览页。

---

### Step 1 — 确定 N slide 数量 (v24: 库容量驱动)

**v24 规则** (输入含 `candidate_pool_summary`,反映本章库真实候选):

优先级依次:
1. **库容量硬约束**:
   - 若 `candidate_pool_summary.n_total < IDEA expected_pages_indicative` → **N ≈ n_total × 1.0 ~ 1.2** (不硬凑更多页数)
   - 例: IDEA 想要 7 页, 但库里只 4 张相关 → N=4 或 5,不写 7
   - 若 `n_total ≥ expected_pages_indicative` → 按 IDEA 走 (最多 ×1.3)

2. **subline 库支持判定** (决定 chapter_decomposition):
   - `clusters_by_role` 里某类角色 (opener/method_detail/result/closer) `n_slides == 0` → **不写该角色对应的 subline**
   - `n_slides == 1-2` → 该 subline 只出 1-2 张 stub (不给 3+)
   - `n_slides ≥ 3` → subline 可有 2-3+ stub

3. **不允许硬凑 subline**:
   - IDEA claims_to_make 里的 "抓手" 若库里没对应候选 (`sample_titles` / `sample_claims` 完全无关) → **该抓手不写 subline**,而不是硬凑一个空 stub

4. **例外**: cover/agenda/references/closing 章仍按 IDEA 页数 (通常 1-3 页), 骨架桥接不受候选池限制
5. **结构页开销**: `section_divider` 是正式页, 计入 `page_count`, 但不占用内容候选池容量; 因分目录导致比 `expected_pages_indicative` 多 1 页是允许的

**输出 chapter_decomposition.sublines**: 每个 subline 必须对应 candidate_pool_summary 里至少 1-2 张候选,不允许"库无支持却仍列出"的 subline.

**默认 N**: 从 `min(expected_pages_indicative, n_total × 1.2)` 起步,再看 rhythm_pattern.abstract_node_sequence 微调。

---

### Step 1.5 (v25 新增, 核心) — subline 名字必须来自库, 不能编造

**问题背景**: v22-v24 Stage 1a 常自造 subline 名字 (如"调度与服务框架"/"定制加速器架构"), 结果 Stage 1b 拿去检索时发现库里根本没有 → 全章 gap.

**v25 硬约束**:
1. **subline.name 必须直接引用或概括 `candidate_pool_summary.clusters_by_role[i].sample_titles` / `sample_claims` 里的具体术语**
   - 例: sample_titles 含 "FlashOverlap 计算通信重叠 / SpeContext 投机解码" → subline 名可以是 "计算通信重叠" 或 "投机解码" 或 "FlashOverlap"
   - 若 sample 里全是 "AI 2.0 tokens/J" / "能效指标" → subline 名可以是 "tokens/J 定义" 或 "能效指标演化"
   - **禁止**: 用 IDEA claims_to_make 里的抽象方向 (如"降算力路径"/"跨算法-硬件联合设计") 直接当 subline 名字
2. **IDEA claims_to_make 是**参考**, 不是硬约束**:
   - claim 提到 "以代表工作示范..." → 你去 sample_titles 里找**库里真的有的代表工作名** (如库里 sample 里频繁出现 "FlashOverlap", 那 claim 里的"代表工作"就映射到 FlashOverlap)
   - claim 提到某具体名字但库里 sample 完全没有 → **忽略该名字**, 保留 claim 抽象意图, 用库真名替代
   - claim 描述的整个抓手方向在 sample 里找不到任何呼应 → **可以放弃该 claim**, 用库 sample 里存在的方向重写 subline
3. **subline.abstract_topics**: 每条至少 1 个术语必须出现在候选池的 sample_titles/sample_claims 里 (库里真的讲过)

**测试问题**: 写 subline.name 前问自己 — "candidate_pool_summary 里哪些 slide 会用来讲这个 subline?" 若答不出 3 张 → 该 subline 不该存在.

---

### Step 2 — slide_role 序列

per slide 决定 target_role (typically 跟 chapter.section_role 相同, 但有例外):
- chapter cover/agenda/closing: 唯一 1 页, role 同 chapter
- chapter motivation/method/framework/discussion/...: 多页, 大多 role 同 chapter, 但若
  `chapter.requires_section_divider=true` 或 `structural_page_contract.section_dividers.required=true`,
  **第 1 张 stub 必须是 `section_divider`**, `archetype_placement="section_open"`,
  `belongs_to_subline_index=null`, `page_purpose_hint` 写 "分目录页: 高亮当前章"; 后续第 2 张开始才进入真实内容页
- 分目录页是 OUTLINE 主流程页面, Stage 1b 必须绑定真实 agenda/divider 结构源页, 不能留给后处理生成
- **特殊**: 若 narrative_constraints 显示该章应有 thesis_raise/callback 或 framework_anchor_repeat
  专页, 用对应专 role tag

### Step 3 — archetype 序列 (核心)

per slide 选 1-2 个 archetype 从 page_specific_archetypes 枚举中选:
- archetype 必须 `applicable_role` 包含当前 target_role 或 "content_candidate" (通用)
- archetype 选择应 **align rhythm_pattern.abstract_node_sequence** (e.g. 当前页对应 node
  `framework_recap` → 选 `three_layer_framework_recap_across_chapters`)
- 同一 archetype 不允许在同章重复 ≥3 次 (避免节奏单调)
- 视觉/authoring/text 三类 archetype 可叠加 (e.g. 1 个 visual + 1 个 text rule)

### Step 4 — archetype_placement

per slide 标 `archetype_placement`:
- `section_open`: 章首页 (第 1 张)
- `section_middle`: 章中段
- `section_close`: 章末页 (第 N 张)
- `chapter_transition`: 跨章过渡专页 (含 framework recap / agenda recap)

### Step 5 — page_purpose_hint

per slide 写 ≤30 字一句话提示, 说明该页**做什么** (不是 claim, 不是内容, 是任务):
- e.g. "framework 图 recap, 高亮当前层"
- e.g. "paper 1 (TB-STC) 引入+方法概要"
- e.g. "本章总结+回扣 thesis"

### Step 6 — page_to_rhythm_node 映射

输出 `page_to_rhythm_node_map`: per slide 指向 rhythm_pattern.abstract_node_sequence 中哪个 node
(若 1 node 对应多 slide, 列同一 node_index; 若该 slide 不映射 (e.g. 加的过渡页), 标 null).

---

## Output (strict JSON only)

**field names 必须严格按下面命名 — 不允许用 `chapter_id`/`section_index`/`slide_count`/`slides` 等近义词替换**:

```json
{
  "chapter_index": 4,
  "chapter_title": "算法层协同·稀疏·量化·解码",
  "rhythm_pattern_id": "method_framework_recap_then_papers_then_summary",
  "chapter_decomposition": {
    "axis": "<≤30 字, 本章用什么轴分解, e.g. '算法层降算力主要手段' / '硬件层加速器架构方向'>",
    "sublines": [
      {
        "index": 1,
        "name": "<≤15 字主线名, e.g. '调度与服务框架' / '稀疏化算法'>",
        "abstract_topics": ["<抽象主题 1>", "<抽象主题 2>", "..."]
      },
      {"index": 2, "name": "...", "abstract_topics": [...]},
      {"index": 3, "name": "...", "abstract_topics": [...]}
    ],
    "rationale": "<≤80 字, 解释为何这么分 — 引用 IDEA chapter.purpose + 资源库可获得性>"
  },
  "stubs": [
    {
      "slide_index_in_chapter": 1,
      "target_role": "section_divider",
      "archetype": ["chapter_navigation_reuses_toc_with_highlight_dimming"],
      "archetype_placement": "section_open",
      "page_purpose_hint": "分目录页: 高亮当前章",
      "belongs_to_subline_index": null
    },
    {
      "slide_index_in_chapter": 2,
      "target_role": "method",
      "archetype": ["three_layer_framework_recap_across_chapters"],
      "archetype_placement": "section_middle",
      "page_purpose_hint": "framework 图 recap, 高亮算法层位",
      "belongs_to_subline_index": null
    },
    {
      "slide_index_in_chapter": 3,
      "target_role": "method",
      "archetype": ["paper_intro_layout_title_authors_venue", "method_pain_and_design_twin_slide"],
      "archetype_placement": "section_middle",
      "page_purpose_hint": "主线 1 (稀疏化) 代表工作引入",
      "belongs_to_subline_index": 1
    },
    ...
  ],
  "page_count": 8,
  "work_blocks": [
    {
      "block_index": 1,
      "work_name": "TB-STC",
      "template": ["paper_intro", "challenge", "method", "result"],
      "stub_indices": [3, 4, 5, 6],
      "source_scope": "single_work"
    }
  ],
  "parallel_group_adherence": {
    "parallel_group_id": "layered_representative_works",
    "canonical_chapter_skeleton_followed": true,
    "canonical_work_block_template_followed": true,
    "page_budget_within_delta": true,
    "notes": ""
  },
  "page_to_rhythm_node_map": [0, 1, 1, 2, 3, 3, 4, 5],   // 长度 = page_count
  "rhythm_adherence": {
    "rhythm_node_count": 6,
    "slide_count": 8,
    "expansion_ratio": 1.33,           // slide / node
    "skipped_rhythm_nodes": []         // 若有 node 没映射
  }
}
```

---

## Hard rules

1. **Output strict JSON only**, 无 markdown fence, 无 prose preamble
2. **N (slide_count)** ∈ [ceil(0.8 × expected_pages_indicative), floor(1.3 × expected_pages_indicative)]
   且 ≥ rhythm_pattern.abstract_node_sequence 长度。若 `requires_section_divider=true`, N 可额外 +1,
   这 1 页只能用于 `stubs[0].target_role="section_divider"`。
3. **archetype** 必须取自 input.page_specific_archetypes[].id, 不允许凭空造
4. **archetype.applicable_role** 必须包含当前 target_role 或 "content_candidate" (通用)
5. **archetype 重复**: 同一 archetype 在该章不超过 2 次
6. **page_purpose_hint** ≤30 字, 单句, 描述任务不是内容
7. **page_to_rhythm_node_map** 长度 = page_count, 每项 ∈ [0, rhythm_pattern.abstract_node_sequence-1] 或 null
8. 不写 claim / key_points / source_resource_ids / needed_evidence / anchor_terms /
   delivery_hint (Stage 1b 的事)
9. 不动 chapter.purpose / claims_to_make / section_rhythm_pattern_id
   (上游 IDEA 已定, Stage 1b 才用) — v28: claims_pending_data 字段已弃, 若老 idea 里有则忽略

9b. 若存在 `parallel_group_context.contract`, 必须输出 `work_blocks[]` 和
   `parallel_group_adherence`; 不能只在 rationale 中口头说明。

10. **claims_to_make 抽象意图覆盖 (v4.0 — HIGH, 高频被违反)**:
    - 来自 IDEA 的 `chapter.claims_to_make` 是**章 intent 抽象方向** (不含具体技术名), 而非
      必须逐字落到 slide 的具体内容
    - 每条 abstract claim 必须在 stubs[] 里有 ≥1 个 stub 的 `page_purpose_hint` 体现该
      claim 的**主旨/方向** (不要求关键词字面相等, 因为 OUTLINE Stage 1b 反查 source 后
      具体技术名才会浮现; Stage 1a stub 只需保证该方向有 slide 承接)
    - 不允许章节 abstract claims 4 条但只覆盖 2 条 — 要么扩 stub(增 slide), 要么
      page_purpose_hint 合并双 claim
    - 在 output 顶层加 `claim_to_stub_map: [{claim_index: i, stub_indices: [j, k]}]`
      做映射 (映射判断按主旨/方向, 不按字面)
    - 找不到映射的 claim → 必须 fail self-check, **重新分配 stubs 直到全覆盖**

    **important**: IDEA claims 是抽象意图, Stage 1b 的 slide.target_claim 才会出现具体技术名;
    Stage 1a stub 也用抽象语言, 保持与 IDEA 同层。具体技术名在 page_purpose_hint 里可以
    出现 (作为 task hint), 但**不强制**。

11. **子主线宣告即承诺 (P21b — CRITICAL, 高频被违反)**:
    若某 stub 的 `page_purpose_hint` 含 "N 主线 / N 路线 / N 抓手 / N 维度 / N 大方向"
    字样 (N ∈ {2,3,4,5}):
    - 必须紧跟 **N×k 张 stub** (k≥2) 按声明顺序展开 — 即每主线至少 2 张 (1 case_study
      opener + 1 method/result)
    - 各主线的展开 stubs **必须连续**(不能算法/系统/算法交错)
    - 主线 opener stub 的 `page_purpose_hint` **必须显式编号**: "主线 1 / 主线 2 / 主线 3"
      或主线名字 (e.g. "结构稀疏 / 量化 / 高效解码")
    - 章末 `chapter_summary` archetype stub 的 page_purpose_hint **必须 callback 全部 N 主线**
      (e.g. "三主线收束: 结构稀疏 + 量化 + 高效解码 → 算法层能效闭环")
    - 如果 chapter 总 slide 数装不下 N×2+1(opener) → 主线宣告必须改成更少 (e.g. 5 主线宣告
      但只 8 slide → 要么砍宣告到 3 主线, 要么不写宣告页), 不允许"宣告 N 主线但只展开 M < N"

12. **新增输出字段 `subline_declarations`** (P21b):
    若章内存在 N 主线 / N 路线宣告 stub, 输出:
    ```json
    "subline_declarations": [
      {
        "declared_in_stub_index": 1,
        "subline_count": 3,
        "subline_names": ["结构稀疏", "量化", "高效解码"],
        "expansion_stub_ranges": [[2, 3], [4, 5], [6, 7]],
        "callback_stub_index": 8
      }
    ]
    ```
    没有 N 主线宣告时输出 `"subline_declarations": []`。

13. **新增输出字段 `chapter_decomposition` (v4.2 — 必填)**:

    该章顶层必须给出**主线分解**, 这是 Stage 1b 检索资源库的钥匙:

    ```json
    "chapter_decomposition": {
      "axis": "<≤30 字>",
      "sublines": [
        {"index": 1, "name": "<≤15 字>",
         "abstract_topics": [<2-5 个抽象主题词>]},
        {"index": 2, ...},
        {"index": 3, ...}
      ],
      "rationale": "<≤80 字>"
    }
    ```

    **per role 怎么分**:
    - **method 章** (algo/system/hardware 任一层): 必须 2-4 条 subline. 每条主线对应该层一个**子方向**.
      - 算法层 axis 例 subline: 稀疏化 / 量化 / 投机解码 / 蒸馏 — 选 2-3 条
      - 系统层 axis 例 subline: 调度与服务框架 / 通信与并行 / 算子与 KV cache — 选 2-3 条
      - 硬件层 axis 例 subline: 加速器架构 / 芯片集成 / 可重构 / 存内近存 — 选 2-3 条
    - **motivation/framework/discussion 章**: 可以 1-3 条 subline.
    - **cover/closing/agenda**: subline_count=0, sublines=[] (结构页不需要分解)

    **abstract_topics 是关键** — 必须是**资源库可能涵盖的抽象主题词**, **不要写具体技术/工作名**:
    - ✅ "调度", "服务框架", "通信", "并行", "稀疏化", "量化", "投机解码", "FPGA 加速", "芯片集成"
    - ❌ "vLLM", "Splitwise", "PagedAttention", "FlightLLM", "TB-STC" (这些是具体工作名,
      由 driver 在 Stage 1b 前从 material/decks-index.json **真实存在性证据** 浮现)

    **为什么不写具体工作名**:
    - Stage 1a 没读过任何 source slide, 凭训练知识写 "vLLM" — 但**资源库可能根本没**,
      或者**有别的更合适的**. e.g. 写 vLLM 去搜结果可能错过 FlashOverlap.
    - driver 用 abstract_topics 去 `decks-index.json` 的 `主题标签` + `章节列表` + section.md
      `章节叙事` 反查, 取出**资源库实际存在的具体工作名** (FlashOverlap / SpecEE /
      semi-PD / FlightLLM / TB-STC), 注入 Stage 1b 的 candidate pool.

    **belongs_to_subline_index** (per stub): 标该 slide 属于哪条主线 (1-indexed); 不属于
    任何 subline (如 framework recap / 章首导览 / 章末总结) 时填 null.

14. **stubs 与 subline 的对应**:
    - 每条 subline 至少应有 2 张 stub 承载 (1 opener + 1 method/result), 不允许"宣告 3 主线但
      某主线只 1 张"
    - subline 展开必须**连续** (主线 1 的 stubs 都展开完, 再展主线 2)
    - 各主线 stubs 数量大致均衡 (±1 张)
    - method / result / engineering 章内, 每个代表工作 opener、challenge、method、result
      stub 必须填写 `belongs_to_subline_index`; 不允许全部为 null。只有 framework recap、
      章首分目录、章末总结可以为 null。

15. **framework 章特殊约束 (v4.2 — HIGH)**:

    framework 章是**全 deck 的脚手架**, 任务是建立后续 method 章共用的分层定位坐标 —
    **不展开具体方法/工作/论文**, 那是 method 章的事.

    **sublines.abstract_topics 必须停在抽象问题层**:
    - ✅ 允许: "算法层冗余计算", "算法层稀疏化挑战", "系统层调度瓶颈", "系统层显存约束",
      "硬件层适配差距", "硬件层不规则计算挑战", "跨层协同接口"
    - ❌ 禁止: "算法层抓手", "系统层方案", "硬件层加速器", "稀疏化方法", "FPGA 设计"
      (这些隐含具体方法, 应留给 method 章)
    - ❌ 严禁出现任何具体工作名 (FlightLLM/SpecEE/vLLM/...)

    **archetype 白名单 (framework 章必须从此集合选)**:
    - `framework_overview_page_*` (任何 framework 总览类)
    - `domain_pain_point_callout`
    - `method_pain_and_design_twin_slide` (但 stub.page_purpose_hint 必须保持抽象)
    - `chapter_summary_page_*`
    - `section_open_panel` / `section_transition_*`
    - `parallel_subsection_title_uses_position_prefix_series` (列三层时可用)

    **archetype 禁用清单 (framework 章不许出现)**:
    - `case_study_opener_*` (这是 method 章引入具体论文用的)
    - `paper_intro_page_*` / `paper_method_unfold_*` / `case_study_paper_*`
    - `hardware_or_architecture_page_uses_named_module_block_diagram` (这是 method 章展具体架构图用的)
    - `method_arc_uses_paper_methodology_*`
    - 任何含 "paper" / "case_study" / "method_arc" / "named_module" 字样的 archetype

    **page_purpose_hint 必须含**:
    - "痛点"/"挑战"/"差距"/"瓶颈"/"问题" 之一 (问题陈述类页)
    - 或 "抓手"/"方向"/"协同接口" (但**禁止跟具体工作名**搭配)
    - 或 "层次定位"/"框架总览"/"层间收束" (结构性页)

    **page_purpose_hint 禁止**:
    - 出现具体工作名 (FlightLLM/SpecEE/TB-STC/FlashOverlap/...)
    - 出现 "代表论文"/"代表工作"/"案例" 等 method 章口吻

    若某 stub 实际需要展开具体方法, 把这部分搬到下游 method 章, **不要塞进 framework 章**.

16. **内容页禁用目录/骨架语义 (v36 — HARD)**:

    - 除 `target_role ∈ {agenda, section_divider, cover, closing, references}` 外,
      不要生成标题或 purpose 为 "目录 / Contents / agenda / 进入本章 / 导览页" 的 stub。
    - 若本章有 `section_divider`, 它必须是 `stubs[0]`; 不允许在第 2 张或更后位置再生成第二张目录/导览页。
    - 普通内容页如果需要说明本章结构, 应写成真实内容页, 例如
      "本章立靶: 系统层三类瓶颈" 或 "代表工作 1: FlashOverlap 论文引入",
      而不是 "系统层三主线导览"。
    - outlook 章已有章前 `section_divider` 时, 第一张 outlook 内容页必须讲趋势/范式/未来问题,
      不能再是一张目录页。

---

## Anti-rules

- ❌ 不要凭空造 archetype id (必须从枚举选)
- ❌ 不要让 archetype 重复 ≥3 次 (节奏单调)
- ❌ 不要让 slide_count 超 expected_pages × 1.3 (章臃肿)
- ❌ 不要让 N 小于 rhythm_pattern.abstract_node_sequence (rhythm 装不下)
- ❌ 不要把 framework recap / thesis callback 这些跨章 anchor 漏掉 (narrative_constraints_slice
  指 must 加, 就要分配专 slide)
- ❌ 不要在 page_purpose_hint 写完整 claim (e.g. ❌ "稀疏化算法相比稠密快 10×" → ✅ "paper 1
  方法+量化收益概要")
