# OUTLINE Slide Detail — Per-Chapter Detail Filler (Stage 1b, v4.2 two-pass)

## Purpose

接 **Stage 1a 输出的 chapter stubs** + chapter context + 该章 slide-level carrier brief, 输出
**该章每张 slide 的完整 detail**: target_claim / key_points / needed_evidence / anchor_terms /
source_resource_ids + alternates / source_carrier_resource_kind / style_unification_hint /
claim_status_link / delivery_hint.

**v4.2 两遍 Pass 模式 (driver 控制)**:

| pass_mode | 输入 candidate 池 | 任务 | 输出 |
|---|---|---|---|
| `carrier_only` (PASS-1) | tier1: rhythm.carriers 反查的 slide briefs | 用 rhythm 优先匹配, 找不到的标 gap_status | 完整 slide detail + per slide gap_status |
| `fill_gaps` (PASS-2) | per gap slide 给 cascade 检索的扩展 candidate | **仅**重写 gap_slides 的 source_resource_ids/target_claim, 其他保留 PASS-1 结果 | 更新后的 slides |

driver 流程:
```
detail_v1 = call(pass_mode=carrier_only)
gap_slides = [s for s in detail_v1.slides if s.source_carrier_resource_kind in {matching_fallback, new}]
if gap_slides:
    detail_v2 = call(pass_mode=fill_gaps, with extended candidates)
else:
    detail_final = detail_v1
```

**任务边界**:
- ✅ 拿 Stage 1a 给的 stub (slide_index/role/archetype/placement/purpose_hint), **每页填全 detail**
- ✅ per slide 选 source_resource_ids (top-1) + alternates (top-2/3), 从 candidate_slide_briefs 里挑
- ✅ per slide 标 `gap_status` (carrier_only mode) 让 driver 判断要不要走 PASS-2
- ✅ 把 chapter.claims_to_make 分配到具体 slide.target_claim (claim_status_link)
- ✅ (v28) 检测多来源风格不一致 → 填 `style_unification_hint` (供 SLIDE_REWRITE 统一术语/标题/口径)
- ❌ **不动** stub schema (slide_index/role/archetype/placement/purpose_hint 不改, stub 错就回 Stage 1a)
- ❌ **不动** chapter_plan / narrative_constraints (上游 IDEA 已定)
- ❌ **不重写** `chapter.section_rhythm_pattern_id` (v4.0 IDEA 已选的 rhythm)

**为什么 Stage 1b 两 Pass**:
- PASS-1 carrier-only: 让 rhythm 真正起优先复用作用, 不被全局检索稀释
- 检测 gap (carrier 池里**真**没合适的): 标 gap_status, 而非硬塞 fallback
- PASS-2 fill_gaps: 只对 gap slide 跑 deck → section → slide 三层级扩展, 既不浪费 token, 也不动已找到 carrier 的 slide

---

## Inputs

```json
{
  "chapter": {              // 1 个 chapter (full context from idea-analysis.chapter_plan[i])
    "section_index": 4,
    "chapter": "...",
    "section_role": "method",
    "purpose": "...",
    "claims_to_make": ["..."],
    "claims_to_setup_for_later": ["..."],
    // v28: claims_pending_data 已弃 (库驱动生成, 不允许待补外部数据)
    "section_rhythm_pattern_id": "method_framework_recap_...",  // v4.0 IDEA 选的 rhythm
    "source_carrier_resource_kind": "carrier_bound"
  },
  "chapter_stubs": [          // ← Stage 1a 输出, 此处 read-only
    {
      "slide_index_in_chapter": 1,
      "target_role": "method",
      "archetype": ["three_layer_framework_recap_across_chapters"],
      "archetype_placement": "section_open",
      "page_purpose_hint": "framework 图 recap, 高亮算法层位"
    }, ...
  ],
  "candidate_slide_briefs": [    // 该章候选 section 下面所有 slide 的 brief, 从 slide_NN.md 加载
    {
      "deck_id": "tpl.topic.开题报告与考核汇报.49b348d602c5",
      "deck_title": "稀疏计算助力人工智能算力平台构建",
      "section_id": "tpl....sec.03",
      "section_role": "framework",
      "slide_index_in_source": 8,
      "slide_id": "tpl....sec.03.slide_08",
      "页面角色": "content_candidate",
      "标题": "研究思路: 软硬件协同 (分层框架图)",
      "核心论断": "...",
      "本页讲什么": "...",
      "关键文字": [...],
      "视觉骨架": ["分层框架图", "底向上层叠"],
      "资源ID列表": [...],
      "适合复用场景": [...],
      "不适合复用场景": [...],
      "上页角色": "...",
      "下页角色": "..."
    }, ...
  ],
  "intake_constraints": {        // anchor terms, must_keep terms, audience
    "must_keep_terms": [...],
    "anchor_terms": [...],
    "audience_expected_depth": "deep"
  },
  "narrative_constraints_slice": {   // 该章相关 thesis/framework/anchor (slice_narrative_for_chapter)
    "thesis_callback_at_this_chapter": {"thesis": "...", "slide_hint": "末页"},
    "framework_anchor_repeat_at_this_chapter": {"anchor": "...", "slide_hint": "首页"},
    "anchor_terms_must_appear_in_this_chapter": [...],
    "cross_section_hooks_from_prev": {"hook_type": "...", "content": "..."},
    "cross_section_hooks_to_next": {"hook_type": "...", "content": "..."}
  },
  "project_evidence_briefs": [        // 项目 PDF/img/excel briefs 该章相关 (filter by 适合章节)
    {
      "resource_id": "pdf.xxxxx",
      "类型": "pdf",
      "标题": "FlashAttention paper",
      "核心论断": "...",
      "适合章节": ["method/算法层"]
    }, ...
  ]
}
```

---

## Task

per slide (按 chapter_stubs 顺序), 填:

### Step 1 — target_title (≤30 字, 1 句)

- 基于 page_purpose_hint + chapter context, 写正式 slide title
- 命名风格: 用 archetype 暗示的格式 (e.g. `paper_intro_layout_title_authors_venue`
  archetype 暗示用论文全标题+作者)
- 应该包含 intake.must_keep_terms / anchor_terms 相关 keyword (若该页是该 term 首次出现)

### Step 2 — target_claim (≤50 字, 1 句判断句)

- 该页**单一**核心论断, 必须是判断句 (有 predicate)
- **v4.0 关键**: IDEA 给的 `chapter.claims_to_make` 是**抽象意图** (e.g. "硬件加速器主要
  方向"), Stage 1b 在反查 source slide briefs 后, 把抽象意图**实例化为具体技术名**
  写到 target_claim (e.g. "本章覆盖 FPGA / ASIC / 可重构 / 3D 集成 4 类硬件加速主流方向")
- **允许 drift**: 若 source 实际只有 3 类 (无 3D 集成), target_claim 应忠实改写为
  "本章覆盖 FPGA / ASIC / 可重构 3 类主流方向", **不必硬塞** IDEA 抽象意图里 enumerate 的
  类目 — 这正是 OUTLINE 阶段 realize 抽象意图的关键
- 若该页对应 chapter.claims_to_make 的某条 abstract intent, 在
  `claim_status_link.maps_to_chapter_claim_idx` 标 (按**主旨对齐**, 不按字面)
- **v28: claim 库支撑不了具体数字时不要 fabricate 也不要"待补外部"**:
  - claim 改写为**能力性描述** (e.g. "稀疏化降低算力需求" 而非 "稀疏化 3× 加速")
  - 不填 `gap_research_hint` (已弃); 若属于多来源风格不一致 → 填 `style_unification_hint`

### Step 3 — key_points (≤3 条, 每条 ≤30 字)

- 该页正文要点 (bullet), 不超 3 条 (per rule `claim_max_length_p95`)
- 每条应该是支持 target_claim 的子证据/子论点

### Step 4 — needed_evidence

- 该页需要的视觉/数据/引用 (图/表/数字/论文 cite)
- 类型: `{type: "chart|figure|table|citation|quote", content: "...", source: "..."}`
- source 可以是: 项目 PDF (project_evidence_briefs.resource_id) / source slide 的 asset_id /
  已绑定 material source; 不允许写 "GAP_RESEARCH 待补"

### Step 5 — anchor_terms

- 该页必须出现的 anchor 术语 (来自 intake_constraints.anchor_terms +
  narrative_constraints_slice.anchor_terms_must_appear)
- 若 narrative_constraints 指该 anchor 必须在该章某页首次出现 (anchor_trajectory.first_appearance),
  本 slide 应当承担 first_appearance + 含定义提示

### Step 5.5 (v22 修 D — 撤销 v21 的骨架/内容二分) — 统一严格 subject 匹配

**v21 的错**: 曾经允许骨架页低 alignment 视觉承载, 结果 byte-clone 出的 draft 里视觉图**内容与 target 完全不符** (例: motivation "对偶路径 A/B" 绑到 UNet-diffusion 图, 无法通过文字修改救回).

**v22 正确 mental model**:

- byte-clone 决定了 source slide 里画的**具体图/表**会**原封不动**进 draft
- SLIDE_REWRITE 只能改文字, **无法重画视觉框架**
- 所以每张 target **必须**绑到能承载它 claim 的具体图/表, 而不是相似 layout 的任意图

**统一选源规则** (v22, 所有 slide 一律适用):

1. `_claim_alignment ≥ 0.4` **且** subject scope 精确匹配 (source 讲的东西跟 target claim 是同一个主题, 不是相似 layout)
2. 找不到 → kind = `new` + source_resource_ids=[]; 这会触发 OUTLINE review/fix, 不是最终结果
3. **不要**因为"骨架页"就放宽标准 — 骨架页视觉图错了下游没法救
4. **不要**因为 layout 相同就硬绑 — layout 相同但内容不同的 source 会误导观众

driver OUTLINE review/final gate 阶段:
- kind=new + candidates 里有严格匹配 → 绑
- kind=new + 无严格匹配 → **hard remove** (砍大纲页 — 库不支持讲这个, 就不讲)

**判定原则**: 每张 target 应该问自己 "库里真的有讲这个的 slide 吗?" 而不是 "库里有相似 layout 的 slide 吗?".

---

### Step 6 — source_resource_ids + alternates (v17 section-first)

per slide 从 input.candidate_slide_briefs 中找最合适的 source slide.

**v34 HARD: 不同目标页默认不得复用同一 top-1 source**:

- 相邻两页 (slide_index_in_chapter=N 和 N+1) 的 top-1 `source_resource_ids[0].slide_id`
  **必须不同**。同章内非相邻但目标标题/claim 不同的页面也应避免复用同一 source slide。
- 若确实需要同源, 必须在两个 slide 都输出:
  ```json
  "same_source_intent": {
    "allowed": true,
    "reason": "agenda/framework 模板复用, 只改变当前项高亮",
    "paired_slide_indices_in_chapter": [1, 2]
  }
  ```
  且只允许以下情况:
  - agenda/framework/chapter_divider/section_divider 结构模板复用
  - 一页是同一图的总览, 另一页是局部解释, target_claim 明确不同且 source 视觉能支撑两者
- 若重复 source 是因为没有更贴合 candidate, 不得硬绑. 应改选 alternate/cascade candidate;
  仍没有则标为需要 outline 回滚/删减, 不能把重复源留给 gapcard 事后修。
- alternates **至少 2 个**; 若不足, `_pick_rationale` 必须说明 "alternate_insufficient=true"。

**v17 candidate 池新增**: `candidate_pool_stats.candidate_sections_grouped` — 按 (deck_id, section_id) 分组的 candidate 列表, 每组含 slide_ids_ordered (按原 source slide_index 排序). 用来找**整段连续复用**机会.

**v20 candidate 池新增**: `candidate_pool_stats.candidate_section_summaries` — 每个 (deck_id, section_id) 的 section.md 摘要, 含 `narrative` (章节叙事) + `intra_flow_hint` (章内 slide 间关系 prose). **必须先读这个**再决定挑哪几张 slide:
- 若 intra_flow_hint 说 "slide N 是方法, slide N+1 是结果, slide N+2 是能效对比" — 而本章 subline 需要"方法+结果"两页 → **必须**挑 slide N 和 N+1 (相邻), 不允许挑 slide N 和另一 section 某张
- section.narrative 提供了这一 section 在原 deck 中的角色 — 若该 section 是"背景/相关工作"性质, 而本章 target 是"代表工作展开" → **禁用**该 section (即使 keyword 命中)

**v17 段级选择优先 (Section-first)** ⭐ 核心新规则:

1. **先看 candidate_sections_grouped**: 哪些 section 覆盖当前章多张 stub? 优先"整段连续复用" (同 section 相邻 slide 用到相邻 target 页):
   - 若某 section 有 3+ 张 slide 跟本章 3+ 张 target 主题匹配 → **强制**这些 target 按 source section 顺序取 slide, 保持相邻页视觉+叙事连贯
   - 例: 若某章要 6 张 method 页, candidate 里某 section 有 5 张连续 method slide 都匹配, 应该 5 张 target 全用同 section 的 slide (按 source slide_index 升序), 而不是从 5 个 section 各选 1 张
2. **对当前 target 找不到同 section 上下页时才 cherry-pick** 单张
3. **不允许跨 section 频繁跳** (章内应尽量集中在 2-3 个 source section 内)

**tier1/2/3 分级** (v4.1 保留):
- `_tier=1`: rhythm.carriers 池, 同节奏 sibling section (driver 已粗筛 top-15)
- `_tier=2`: 全局按本章 layer + sublines.keywords 检索 (跨 rhythm, 跨 deck, top-20)
- `_tier=3`: 全局仅按 keywords (兜底, top-10)

**v4.3 claim 对齐 — 硬指标**:

driver 已给每个 brief 注入 `_claim_alignment` (0-1, LLM 评判的 source.核心论断 vs 该章 target 判断方向对齐度) — **必须优先用这个字段**, 不要用 keyword score 当首要标准.

**判定流程 (从硬到软)**:

0. **v20 角色/布局硬 filter (最高优先, 早于 claim alignment)**:

   目的: 消除"关键词命中但语义错位"的错配 (v19 slide 11/15/21/35 混入具体工作结果; slide 45/46 混入目录骨架页/未来趋势页; slide 23/30 混入不相关算法页).

   规则 1 — **总览/收束 slide 禁止绑定"细节/结果"页**:
   - 若 target_role ∈ {framework, framework_recap} OR target.archetype 含 overview/summary/recap/收束 → **禁止**绑定 source.brief 里以下类型:
     - 页在section中的作用 ∈ {result, method_detail}
     - slide_role ∈ {result}
     - 视觉骨架/layout 是 dense_data_chart, benchmark_table, curve_chart_with_numbers
   - 应绑定 layout ∈ {block_diagram, flowchart, layer_hierarchy_diagram, bullet_list_conceptual}

   **v34 结构源硬约束**:
   - 若 target_role ∈ {chapter_divider, section_divider, agenda, framework_recap, cover,
     closing, references} 或 archetype 含 divider/navigation/framework_recap/closing,
     source 必须是结构型源页: source.section_role / 页在section中的作用 / 视觉骨架 应体现
     agenda、导航、框架总览、当前章节高亮、closing 或 references。
   - `cover`、`agenda`、`section_divider` 是 IDEA/OUTLINE 主流程页面, 不是后处理装饰;
     Stage 1b 必须在本阶段给它们绑定真实结构 source slide, 让 DRAFT 可直接 byte-clone。
   - 禁止绑定普通 method_detail/result/worker_intro/论文封面/具体实验图作为结构页 source。
   - 结构页 source 不满足时, 不要用 layout 相似作为理由; 应换结构型 alternate, 或回 Stage 1a
     删除/合并该结构页。

   **v36 内容页禁用导航源 (HARD)**:
   - 若 target_role ∉ {cover, agenda, chapter_divider, section_divider, closing, references},
     source 不能是目录/导航/封面/致谢/references 源页。
   - 直接 reject 以下 source:
     - `页面角色 ∈ {toc_candidate, cover_candidate, ending_candidate, references}`
     - source.`标题` / `本页讲什么` / `适合复用场景` 含 "目录" / "Contents" /
       "agenda" / "章节切换" / "进度导航" / "高亮当前章"
   - 不允许把目录页改写成 method/framework/outlook 内容页；如果需要章内导航, 应由
     target_role=`section_divider` 承担。

   **v36 总领页对象一致 (HARD)**:
   - 若 target 是全 deck / 课题组 / 团队 / 组织 / 章节总纲页, source deck 不能是
     个人考核、博士资格考试、学生个人研究计划、单篇论文封面或单个学生工作总纲。
   - 这些 source 可以作为具体代表工作页, 不能直接成为课题组主线或全局框架页。
   - 判断信号: source.deck_title/deck_id/报告类型/本页讲什么 含 "个人" / "博士资格" /
     "资格考试" / "开题" / "论文分享" 且 target_claim 含 "课题组" / "本章" /
     "全 deck" / "三层协同框架" / "总纲"。

   **v36 framework 覆盖范围一致 (HARD)**:
   - target_role ∈ {framework, framework_recap} 或 target_title/claim 含 "总纲/框架/主线/三层"
     时, source 的核心论断必须覆盖同等范围。
   - 只讲一个技术点或一个工作 (稀疏计算、SpecEE、FlashOverlap、FPGA 场景等) 的 source
     不能被提升为整章/整 deck framework 页。
   - 窄 source 只能绑定到对应子内容页; framework 页应选 layer_hierarchy/framework/overview
     类型且对象范围匹配的 source。

   规则 2 — **closing 章硬禁止**:
   - target_role = closing → **禁止**绑定 source.brief.slide_role ∈ {opener, agenda, section_divider, cover}
   - target_role = closing + archetype 含 outlook/future → 应绑定 slide_role = closer 或 outlook, 禁止绑定 result

   规则 3 — **同 subline 聚焦同一工作**:
   - 若同 subline 内有 2+ 张 slide 且要展开一个"代表工作", 这些 slide **必须**挑同一个 source deck 的连续 slide (方法→架构→结果), **禁止**跨 deck 拼凑
   - 例外: subline 明确是"多工作 comparison" (chapter_decomposition.sublines[i].name 含"对比/横评") 时允许跨 deck

   规则 4 — **result 页对应 result source**:
   - target_role = result OR archetype 含 result/benchmark/效果 → 应绑定 slide_role = result 或 页在section中的作用 = result
   - 禁止绑定"某个具体工作的方法页"作为整章 result

   违反以上 4 条 → 该 slide 强制标 `source_carrier_resource_kind=new` + `source_resource_ids=[]`, driver 会在 OUTLINE review/final gate 阻断并要求修复.

1. **claim 方向硬约束 (顶级 filter)** — v18 阈值放松:
   - top-1 候选必须 `_claim_alignment ≥ 0.3`, 否则该 slide 标 kind=new, source_resource_ids=[]
   - 若候选池里 ≥3 个 `_claim_alignment ≥ 0.5` → 必须从这些里选, 不允许选 alignment 低但 keyword 高的
   - 即使 keyword 重叠很高, 若 `_claim_alignment < 0.25` 且 candidate 池有 ≥1 高 alignment 候选 → **必须 reject 低 alignment, 选高 alignment**

2. **同 alignment 区间内, 按以下排序选 top-1**:
   - layer 对齐 (target_claim 层位 ↔ source.inferred_layer) → 大权重 +2.0
   - 页面角色 family 一致 → +1.0
   - 视觉骨架 跟 stub.archetype 暗示一致 → +1.0
   - 适合复用场景 含本章 keyword → +0.5
   - 不适合复用场景 命中 → -1.0
   - tier_bonus: tier1 +0.3, tier2 +0.1, tier3 0

3. **subline 对齐** (v4.1): 若该 slide stub 有 `belongs_to_subline_index=k`, top-1 source 应当语义贴近 sublines[k-1].name (无强 enforce, 因为 subline 跨 source 可能不严)

**rank score 计算 (v27 加 role_position_match)**:
```
final_score = 4.0 * _claim_alignment            # claim 方向是主导
            + 3.0 * role_position_match         # v27 新: role 位置匹配 (强权重)
            + 1.5 * (核心论断关键词匹配)         # 词面只是辅助
            + 1.0 * (视觉骨架对应)
            + 0.5 * (适合复用场景命中)
            + 2.0 * (layer 对齐)
            - 2.0 * (不适合复用场景命中)         # v27 加大惩罚 1.0→2.0
            - 2.0 * (layer mismatch)
            + tier_bonus  (1: +0.3, 2: +0.1, 3: 0)
```

**role_position_match 计算规则 (v27 新)**:

看 target_role vs source.`页在section中的作用` (库 brief 里的字段):

| target_role | 期望 source 页在section中的作用 | 命中 | 错配 |
|---|---|---|---|
| cover | opener (且 source.slide_index_in_source ≤ 3) | +3 | 若 source=method_detail/result/closer → -3 |
| agenda / section_divider | opener / mixed | +3 | 其他 → -2 |
| motivation (章内中间/结尾页) | worker_intro / method_detail / result / closer | +2 | 若 source=opener 且视觉写死具体主题 → -3 |
| framework (总览/回顾/收束) | opener / mixed | +2 | 若 source=method_detail/result → -3 |
| method (代表工作/方法/机制展开) | method_detail / mixed | +3 | **若 source=worker_intro (论文封面/工作引入页) → -3** |
| result | result / mixed | +3 | 若 source=opener/worker_intro → -3 |
| closing / recap / outlook | closer / mixed | +3 | 若 source=opener/worker_intro/result → -3 |

**特别规则 (v27 硬扣分, 加到 -3 分)**:

1. **视觉写死具体主题不能跨主题复用**:
   - source 标题含 "层次 N" / "第 N 层" (如 "层次二: 算法优化") → **只能**绑到讲同一层次的 target;target 讲别的层 → **role_position_match = -3**
   - source 标题是 "论文封面 / 引用 / 技术报告" (worker_intro) → **只能**绑到讲同一论文/工作的 opener target;target 是"某工作方法展开" → **-3**
   - source 是"某特定工作结果" (如 "VGAcc 加速比") → 只能绑到讲同一工作 result 的 target → **-3**

2. **deck 首页只能给 cover target**:
   - source.slide_index_in_source == 1 且 source.页在section中的作用=opener → 仅 target=cover (且 slide_index_in_chapter=1) 可绑,其他一律 **-3**

3. **参考文献页只能给 references target**:
   - source 标题含"参考文献" 或 page_role=references → 非 references target 一律 **-3**

**核心原则**: keyword 匹配不能凌驾于 role/context 之上。宁可选一个 alignment 稍低但 role 正确的 source, 也不选一个 keyword 高分但 role 完全错配的 source. 相邻页禁止同 source 已在 Step 6 dedup 阶段处理.

**tier 优先但不锁死**: tier1 默认优先 (+0.3 bonus), 但若 tier2/3 某 slide claim alignment 明显更高 (+0.2 以上), **必须选 tier2/3**.

**取 top-1 为 source_resource_ids, top-2/3 为 alternates** (最少 2 个 alternate, 优先 cross-tier 多样性).

**kind 判定 (v34 final-outline gate)**:
- top-1 _claim_alignment ≥ 0.5 + final_score > 1.0 → `carrier_bound` (强复用, SLIDE_REWRITE 调整陈述方式即可)
- top-1 _claim_alignment 0.3-0.5 → 临时可标 `matching_fallback`, 但这**不是最终可接受状态**;
  必须在本轮输出 `_pick_rationale` 说明 weak 原因, 并期待 OUTLINE review 触发改绑/改 claim/删页。
- top-1 _claim_alignment < 0.3 或无候选 → `new` + `source_resource_ids=[]`;
  driver 会阻断最终 outline, 不允许进入 DRAFT_ASSEMBLY。
- 最终 outline 的目标是每页 `carrier_bound` + `gap_status ∈ {ok, needs_style_unification}`。

输出 schema (v4.3 加 _claim_alignment 字段):
```json
"source_resource_ids": [
  {"deck_id": "...", "slide_id": "...",
   "rank_score": 5.4, "_tier": 1, "_claim_alignment": 0.85,
   "match_reasons": ["claim 方向一致: 都讲算法层降算力主要手段",
                      "layer 算法层匹配", "页面角色 method-opener 一致"]}
],
"alternates": [
  {"deck_id": "...", "slide_id": "...", "rank_score": 4.1, "_tier": 2,
   "_claim_alignment": 0.72, "match_reasons": [...]}
],
"source_carrier_resource_kind": "carrier_bound"
```

### Step 6.5 — gap_status (v28 — 简化为 3 类) **carrier_only/fill_gaps 都必填**

**v28 关键变化**: 项目定位是**基于库现有资源**生成 PPT, 所有"待补外部数据"逻辑已弃. gap 语义从"缺什么内容"改为"多来源之间需要什么统一化修正".

**gap_status 3 类** (原 5 类 ok/weak/no_match/needs_gap_data/not_applicable 已简化):

| gap_status | 含义 | 触发条件 |
|---|---|---|
| `ok` | source 跟 target_claim **judgment direction 一致** + 主题匹配, 直接可用 | top-1 `_claim_alignment ≥ 0.5` + role_position 匹配 |
| `needs_style_unification` | source 主题对 + role 对, 但**表述/术语/标题/口径**与本 outline 其他 slide 不统一, 下游 SLIDE_REWRITE 需要做统一化改写 | 库来源多样 (跨 deck) / 术语命名不一致 / 标题风格不一致 / 口径漂移 |
| `not_applicable` | legacy/异常值；当前 pipeline 不允许最终页使用 | 不应主动输出 |

**没有** `no_match` / `weak_match` / `needs_gap_data` — 找不到就 kind=`new` 交 OUTLINE review/final gate 阻断修复; 找到但不完全对齐一律 `needs_style_unification`.

**判定优先级**:
1. structural slide (opening/cover/agenda/section_divider/closing/references) → 也必须从 candidate_slide_briefs 中选真实 source; 不能标 `not_applicable`
2. 候选最高 `_claim_alignment ≥ 0.5` + role_position 对齐 + 术语/标题/口径基本一致 → **ok**
3. 候选最高 `_claim_alignment ≥ 0.5` + role_position 对齐, 但术语/标题/口径与本 outline 其他 slide 不一致 → **needs_style_unification** (仍标 carrier_bound, 让 SLIDE_REWRITE 统一)
4. 都对不上 → kind=`new`, source_resource_ids=[], 由 driver fail-fast 阻断并要求回滚/重选；不要继续假装可生成

**术语/标题/口径不一致的判定** (LLM 逐条检查):
- 术语: 同一概念在不同 slide 用不同名字 (如"三层协同" vs "层次三系统")
- 标题风格: 有的用冒号有的用破折号有的用括号, 不齐
- 口径: 同一指标称呼不一 (Speedup vs 加速比 vs 提速)
- 单位: 同一量纲写法不一 (tokens/J vs Token/J vs 能效比)

**fill_gaps mode (PASS-2)**: 收到的 `extended_candidate_slide_briefs` 已按 `_claim_alignment` 降序. 挑完后 gap_status 沿用 3 类, 不再有 `_after_expansion` 后缀.

### PASS-2 三层挑选纪律 (v30 fix, HARD)

**问题**: 之前 PASS-2 直接从 flat `extended_candidate_slide_briefs` 挑 slide, LLM 可能跨 deck cherry-pick, 导致同章 slide 来自 5+ 个不同 deck, 语义混乱 (e.g. 系统层章 clone 了华为 deck slide 22 + 交大 deck slide 15 + 组会 deck slide 8, 上下页术语/风格不齐).

**PASS-2 fill_gaps 时必须按 `cascade_hierarchy` 三层挑选**:

1. **先选 deck**: 看 `cascade_hierarchy.top_decks`, 选 1 个**主 deck** (owner/主题/报告类型与 target chapter claim 最匹配的). 若某 deck 的 `deck_title` 或 `报告类型` 明显匹配 target claim (e.g. target = FlightLLM 代表工作 → 选 `报告类型=paper_share` 且 deck_title 含 FlightLLM 的 deck), 强优先.
2. **再选 section**: 从 `cascade_hierarchy.sections_by_deck[主deck_id]` 里选 1-2 个 section (section_role 与 target_role 对齐, section_title 与 subline_name 语义呼应).
3. **最后选 slide**: 从 `cascade_hierarchy.slides_by_section[section_id]` 里挑 slide, 优先 `_claim_alignment >= 0.5` 且 `核心论断` 与 target_claim 有 ≥3 实体词重叠.

**跨 deck 允许**: 若主 deck 里的 section/slide 明显不够或不匹配, 可以从 top_decks[1..2] 里再选 1 个副 deck 补 1-2 张 slide, 但**同章内不允许来自 ≥3 个 deck**.

**优先级冲突处理**:
- `_claim_alignment >= 0.6` 的 slide 即便来自 top_decks[2..4], 也允许优先选 (语义 > 结构)
- `_claim_alignment < 0.3` 的 slide 即便来自 top_decks[0], 也**不允许**选 (视觉相似 ≠ 内容合适)

**输出 provenance 增强**: PASS-2 挑完后 per slide 附上 `_picked_deck_id` / `_picked_section_id` / `_pick_rationale` (≤60 字, 说明"从 X deck 的 Y section 里挑, 因为...")

### PASS-1/PASS-2 通用: 同章内 sibling slide 格式一致性 (v30 fix C, HARD)

**问题**: 同章内多个 slide 承担相似角色 (e.g. 一章有 3 个"代表工作 opener"), 但各自独立挑 source 时 archetype 不一致 —— slide 17 clone 了"论文封面版式", slide 19 clone 了"背景介绍版式", slide 31 又 clone 了"方案示意版式", 视觉上完全不像同一类页, 观众混乱.

**HARD 规则**: 每次挑完某 slide 的 source 后, 必须**扫描本章已挑完的 sibling slides**, 若:
- **角色相同 (same target_role)** 且
- **stub.archetype_placement 相同 (都是 section_middle 且都是"代表工作引入" 类型)** 或
- **stub.page_purpose_hint 语义相似 (都含"代表工作 / paper opener / case_study_opener")**

那本 slide 挑的 source 的 **archetype 应与 sibling 保持一致**:
- 若 sibling 已挑 `paper_intro_layout_title_authors_venue` (论文封面), 本 slide 也应从候选池里挑同 archetype 的 slide, 而不是挑 `method_pain_and_design_twin_slide` (方案示意)
- 若候选池没有相同 archetype 的 slide → **rebind sibling 也换成本 slide 能找到的 archetype** (让全组统一到"能找到的最一致版式")
- 若整章找不到统一版式 → 至少 archetype 大类要一致 (都用 `case_study_*` 类 或 都用 `paper_intro_*` 类)

**输出**: 每个 slide 加 `_sibling_consistency_status`: `"consistent" | "diverged (sibling: <sibling slide_index_in_chapter>)"`
- `consistent`: 与所有 sibling 用同一或同类 archetype
- `diverged`: 检测到不一致, 说明原因

**为何 HARD**: 用户明确反馈 "针对代表工作的第一页, 要么全部用论文介绍页, 要不然全部用具体方案或背景页, 必须统一". 观感一致性是 deck 质量核心.

### result / experiment 页归属验证 (v30 fix E, HARD)

**问题**: result / experiment role 的 slide (含"性能提升 / 加速比 / 能效对比 / 前后收益")
target_claim 通常写"本组/我们/本项目 XX 工作在 YY 场景取得 ZZ 提升", 但如果 clone 了别人的
benchmark 表 (如"创智学院 v2.2.6 slide 23"), 展示的数据不属于本项目, 造成学术不端 / 归属混淆.

**HARD 规则**: 对 target_role ∈ {result, experiment, benchmark} 或 target_claim 含
"本组 / 我们 / 本项目 / 本工作 / 本文" 语气的 slide, 挑 source 时必须验证:

1. **同 owner/lab 优先**: source deck.owner 或 deck.主题标签 中的 lab/team 标识
   必须与项目 owner 匹配 (从 idea-analysis.identity 或 chapter.owner 反查)
2. **同 paper/工作**: source 出自的 deck 报告类型 = `paper_share` 时, deck 标题必须
   含 target_claim 中提到的具体工作名 (e.g. target 讲 FlightLLM 结果 → source 出自
   讲 FlightLLM 的 deck)
3. **不满足以上任一**: 该 slide 视同"库里无归属正确的支持材料":
   - kind 标 `new` 或 `no_supporting_material`
   - source_resource_ids = []
   - gap_status = `attribution_mismatch_no_owner_match`
   - 附 `_attribution_check` 说明"target claim 归属 X, 库里未找到 X 的 result slide"

**逃生舱**: 若 target_claim 用中性语气 (e.g. "该场景通常有 3-5x 加速"), 而非明确归属,
可以放宽到"报告类型 ∈ {paper_share, research_report} 且主题标签匹配"即可.

**为何 HARD**: 用户反馈 "针对结果成效页, 一定要检查该结果是否是本章的工作带来的结果,
是谁带来的还是共同带来的性能优化, 必须说清楚".

### Step 7 — style_unification_hint (v28 新, 替代 gap_research_hint)

**只在 gap_status = needs_style_unification 时填**, 其他情况 null.

内容: 描述该 slide 需要做的**文字/术语/标题/口径统一化**, 供下游 SLIDE_REWRITE 消费.

**格式**: 每条 hint ≤ 40 字, 多条用 " / " 分隔.

**示例**:
- "术语统一: source 用'层次三系统', outline 统一改'系统层' / 标题统一为冒号格式"
- "术语统一: Speedup → 加速比 / 单位统一: token/J → tokens/J"
- "标题风格统一: '(续)' 改成同章其他页的 '- 方案 II'"

**禁止填的情况**:
- ❌ gap_status = ok (无需统一)
- ❌ gap_status = not_applicable (当前项目不允许无来源骨架页)
- ❌ 只是"内容需要写文字" (那是 SLIDE_PLAN 的事, 不是 unification)

**v28 已弃**: `gap_research_hint` 字段. 老版 outline 里若存在, 视为 legacy, 忽略.

### Step 8 — delivery_hint (≤40 字, 1 句)

该页**演讲提示**: 给汇报人提示, 该页讲什么节奏 / 怎么过渡到下一页:
- e.g. "1 分钟讲完 framework 图, 高亮算法层后过渡到 paper 1"
- e.g. "稍停顿强调'相比 baseline'数字, 等观众反应再翻页"

---

## Output (strict JSON only)

```json
{
  "chapter_index": 4,
  "chapter_realized": {
    "summary": "<≤60 字, 该章 slides realize 后实际承载的具体方向, e.g. '本章实际覆盖 FPGA / ASIC / 可重构 3 类硬件加速方向, 与 IDEA intent 一致 (3D 集成因 source 缺失放弃)'>",
    "realized_specifics": ["FPGA 加速器", "ASIC 设计", "可重构架构"],
    "drift_from_intent": {
      "abstract_intent": "硬件加速器与芯片集成主要方向",
      "missing_from_source": ["3D 集成"],
      "added_from_source": [],
      "drift_severity": "none|minor|major"
    }
  },
  "slides": [
    {
      "slide_index_in_chapter": 1,
      "target_role": "method",
      "archetype": ["three_layer_framework_recap_across_chapters"],
      "archetype_placement": "section_open",
      "target_title": "算法层在软硬件协同框架中的位置",
      "target_claim": "算法层是软硬件协同框架的最上层抓手, 负责降算力需求与硬件友好化",
      "key_points": [
        "对应 framework 图的算法层位",
        "本章 3 个 paper 都属于此层",
        "为后续 paper detail 铺垫"
      ],
      "needed_evidence": [
        {"type": "figure", "content": "framework 三层图, 高亮算法层", "source": "candidate slide tpl.....sec.03.slide_08 asset.01"}
      ],
      "anchor_terms": ["软硬件协同", "算法层"],
      "source_resource_ids": [
        {"deck_id": "tpl.topic.开题报告与考核汇报.49b348d602c5", "slide_id": "tpl...sec.03.slide_08", "rank_score": 1.62, "match_reasons": ["framework recap archetype 一致", "底向上层叠视觉骨架 match"]}
      ],
      "alternates": [
        {"deck_id": "tpl.topic.对外汇报展示.8d5c637af9e6", "slide_id": "tpl...sec.04.slide_15", "rank_score": 1.15}
      ],
      "source_carrier_resource_kind": "carrier_bound",
      "gap_status": "ok",
      "style_unification_hint": null,
      "claim_status_link": {"maps_to_chapter_claim_idx": null, "is_setup_for_later": true, "is_thesis_callback": false},
      "delivery_hint": "30 秒 recap 框架, 重点指算法层在最上"
    },
    ...
  ]
}
```

---

## Hard rules

1. **Output strict JSON only**, 无 markdown fence, 无 prose preamble
2. **slide_count** 必须 = input.chapter_stubs 长度 (不增不减, stub 错就回 Stage 1a)
3. **slide_index_in_chapter / target_role / archetype / archetype_placement** 必须等于 stub 同字段
   (Stage 1b 不动 stub 决策)
4. **source_resource_ids[i].slide_id** 必须从 input.candidate_slide_briefs 中选
5. **source_carrier_resource_kind** 按 top-1 rank_score 决策 (>1.0 carrier_bound /
   0.5-1.0 matching_fallback / <0.5 new); 但 matching_fallback/new 只是临时 review 信号,
   不得作为最终 OUTLINE 状态进入 DRAFT_ASSEMBLY
6. **anchor_terms** 必须从 intake_constraints.anchor_terms +
   narrative_constraints_slice.anchor_terms_must_appear 选, 不允许凭空造
7. **target_claim** 必须是判断句 (含 predicate, per rule `claim_is_judgment_sentence_with_predicate`)
8. **v28: claim 含具体数字但库无支撑** → 改写成能力性描述, **不 fabricate**, 也不再填 `gap_research_hint` (字段已弃)
9. **key_points** ≤3 条, 每条 ≤30 字
10. **空字段必须用 null 或 []**, 不要省略
11. **delivery_hint** ≤40 字, 1 句
12. 不动 chapter.purpose / claims_to_make / section_rhythm_pattern_id (read-only)

13. **source.slide_claim 必须语义对齐 target_claim (P21c — HIGH, 高频被违反)**:

    选 `source_resource_ids` 时, 候选 slide 的 `slide_claim` (从 candidate_slide_briefs 拿)
    必须与本页 `target_claim` 在以下**全部 3 个维度**对齐, **不允许只对齐 archetype/role 就选**:

    **a. layer 维度** (最关键, layer mismatch 直接 reject):
    - 算法层(算法/模型/解码/稀疏化/量化) ↔ 算法层
    - 系统层(系统软件/调度/通信/服务框架/算子/KV cache) ↔ 系统层
    - 硬件层(加速器/FPGA/ASIC/PE 阵列/可重构架构) ↔ 硬件层
    - 跨层 mismatch:e.g. target 讲"细粒度算子优化(系统层)" 但 source slide_claim 是
      "稀疏 PE 阵列设计(硬件层)" → **必须 reject**, 即使 role=method + archetype 一致

    **b. 方法类型维度**:
    - target 讲设计/方法 → source 不能只是性能数字图
    - target 讲架构/系统 → source 不能是单纯算法理论
    - target 讲对比/选型 → source 不能是单点介绍

    **c. 结果性质维度**:
    - target 讲速度对比 → source 必须含可比对的速度数字
    - target 讲能效 → source 必须含能效维度数据(非纯延迟)

    **判定方法**:
    - 拿 candidate.slide_claim / slide_key_text / slide_visual_skeleton 三个字段
      + carrier 所在 section.section_title / section_narrative
    - 推断该 slide 实际讲的 layer (扫关键词: 算法/系统/硬件/PE/调度/算子/服务/集群)
    - 跟 target_claim 推断的 layer 比对
    - 不一致 → reject

    **找不到对齐的怎么办 (v34)**:
    - 候选池里**没有**任何 candidate 全 3 维度对齐 → 留空 source_resource_ids: [] +
      `source_carrier_resource_kind: "new"`,**不要硬塞**
    - 这不是交给 GAP 补内容, 而是触发 OUTLINE review/fix: 优先改绑 cascade/alternate,
      其次把 target_claim 改到库能支撑的方向, 最后删页或回 Stage 1a 重拆章节

14. **跨章 source deck 平衡 (P21c — HIGH, 防 single-deck dominance)**:

    全 deck 一张表里(注:Stage 1b 是 per-chapter 调用,这个规则需配合 Stage 2 review,
    Stage 1b 单章内尽力做到):
    - 单个 source deck_id 占用页数不能 > 总页数的 25%
    - 单章内,**不允许** > 3 张 slide 全绑到同一个 source deck_id 的连续 slide_index
      (e.g. ch5 不允许 5 张 slide 全绑到 deck_X 的 slide_40/41/42/43/44 — 这是把原 deck
      拆碎了)
    - 当 candidate top-1 来自一个已经被本章引用 ≥3 次的 deck → 跳到 top-2/3 找其他 deck 的候选,
      即使 rank_score 略低也优先 cross-deck 多样性

15. **新增输出字段 `slide_binding_audit`** (P21c):
    每张 slide 选完 source 后, 输出审计字段:
    ```json
    {
      "slide_binding_audit": {
        "target_layer_inferred": "algorithm | system | hardware | structural | other",
        "source_layer_inferred": "algorithm | system | hardware | structural | other | unknown",
        "layer_aligned": true,
        "rejected_top1": null  // 若 top-1 因 layer mismatch 被 reject, 记录其 slide_id 和 reason
      }
    }
    ```

16. **chapter_realized 必填 (v4.4 — coverage 严格化)**: 每章 detail 输出顶层必须有 `chapter_realized` 字段:
    - `summary` ≤60 字 — 该章 realize 后**实际承载的具体方向** (用具体技术名)
    - `realized_specifics` — 该章实际 cover 的具体技术/工作/方法名数组 (从 source 反查
      后浮现的, e.g. ["FPGA", "ASIC", "可重构"])

    - **`subline_coverage` (v4.4 严格)** — per subline 必填以下字段:
      ```json
      [
        {
          "subline_index": 1,
          "subline_name": "调度与服务框架",
          "stub_indices_in_chapter": [3, 4],
          "carrier_count": 2,           // 真正 carrier_bound 数 (kind=carrier_bound)
          "matching_fallback_count": 0,
          "new_count": 0,
          "claim_aligned_count": 2,     // _claim_alignment ≥ 0.6 的 source 数
          "coverage": "full"            // full | partial | missing  ← v4.4 必填
        },
        {
          "subline_index": 2,
          "subline_name": "通信与并行",
          "stub_indices_in_chapter": [5, 6],
          "carrier_count": 0,
          "matching_fallback_count": 1,
          "new_count": 1,
          "claim_aligned_count": 0,
          "coverage": "missing"
        },
        ...
      ]
      ```

    - **coverage 判定规则 (v4.4)**:
      - `"full"`: 所有 stub 都 kind=carrier_bound + claim_aligned ≥ 0.6 (该 subline 资源库支撑充足)
      - `"partial"`: 部分 stub carrier_bound 部分 fallback/new, 或 claim_aligned 在 0.4-0.6 间
      - `"missing"`: 全部 stub 是 new 或 claim_aligned < 0.4 (该 subline 资源库**真的**没对应内容)

    - **整章 `coverage_status` (v4.4 必填)** — chapter_realized 顶层加字段:
      - `"full"`: 所有 subline coverage=full (理想)
      - `"partial"`: ≥1 subline coverage=partial, 0 subline missing (可接受)
      - `"subline_missing"`: ≥1 subline coverage=missing, 但 < 50% subline (建议下游回滚)
      - `"critical_missing"`: ≥ 50% subline coverage=missing OR 整章 ≥ 60% slide kind=new (**触发大纲回滚**)
      - `"structural_source_backed"`: opening/cover/closing/agenda 等结构章已全部绑定真实 source

    - **section_role 与 coverage_status 强约束 (v4.4 修正, v30 加 3 结构 role)**:
      - `chapter.section_role` ∈ {"opening", "cover", "closing", "agenda", "self_intro", "appendix", "references"} → sublines 可空 [], 但每个 slide 仍必须有 `source_resource_ids`; coverage_status 用 `"structural_source_backed"` 或 `"full"`, **不允许**因为结构页而空 source
        - 理由: 当前 pipeline 是库驱动 byte-clone, 结构页也必须复制真实 material slide (cover/toc/chapter/ending candidate), 不能由下游 placeholder 生成
      - `chapter.section_role` ∈ {"motivation", "method", "discussion", "outlook", "case_study", "background", "problem", "result", "experiment", "engineering", "comparison"} → 才按 carrier_count / new_count 判定 coverage_status
      - **`carrier_count=0 + new_count=0`** 这种组合不允许出现 — 任何 stub 必有归属 (要么 carrier_bound, 要么 fallback, 要么 new). 若全是 0, 必须重新检查 stubs/source 绑定, 不得用 not_applicable 掩盖

    - `drift_from_intent` — 跟 IDEA chapter.claims_to_make 抽象 intent 的偏移:
      - `abstract_intent` — IDEA 那条 abstract claim 原文 (≤30 字)
      - `missing_from_source` — **仅在三层 candidate 全空才填** (e.g. subline_coverage 中某项
        carrier_count=0 且 found_in_tier=null). e.g. ["3D 集成"]; none 时为 []
      - `added_from_source` — source 里 cover 了 IDEA 没 imply 的方向 (e.g. ["近存计算"]); none 时为 []
      - `drift_severity`: "none" / "minor" (missing/added ≤1 项) / "major" (≥2 项)

    - **重要 (v4.4)**: 不允许把"找不到 carrier"伪装成"GAP 待补". 当 coverage_status ∈
      {subline_missing, critical_missing} 时, **必须如实标 missing**, 让 codex review 触发
      Stage 1a 大纲回滚 (砍 subline / 换 axis), 而不是硬塞 kind=new 让下游 SLIDE_REWRITE 凭空写.

    - **重要**: 不允许 missing_from_source 标"调度"/"FPGA" 等 candidate_slide_briefs 里**已有**
      的 keyword — 那是 LLM 没认真匹配, 不是 source 真缺. 标 missing 前必须验证 candidate_pool
      文本搜过没命中

    - **major drift 时**, summary 简要说明 (不当 issue 报, 由下游 review 决定是否需 user 介入)

17. **framework 章特殊约束 (v4.2, v30 更新)**:

    若 chapter.section_role == "framework", 整章必须停在**抽象层**, 但 **v30 允许 grounded
    具体工作名** (若在 IDEA 阶段的 `full_library_inventory` 里能找到):

    **target_claim 必须**:
    - 描述层痛点/挑战/差距 (e.g. "算法层在大模型推理中存在大量稠密计算冗余, 是协同优化首要切入点")
    - 描述层抓手抽象方向 (e.g. "硬件层以可重构与定制加速器为抓手面向稀疏与低比特任务")
    - 描述跨层接口/协同关系
    - **允许**引用 grounded 具体工作名作 anchor (若在 IDEA `provenance.library_grounded_works`
      里出现, 或 chapter.claims_to_make 里已有), e.g. "以 FlashOverlap 为代表的通信重叠优化"
      是允许的 (若 inventory 里有 FlashOverlap).
    - **禁止**引用未 grounded 的具体工作名 (若在 IDEA provenance / inventory 里查不到, 就是幻觉).
      凡在 framework 章 target_claim 出现的具体工作名, 必须验证 grounded 来源.

    **source_resource_ids 必须**:
    - 优先选 source.section_role ∈ {framework, motivation, structural} 的 slide
    - 避免选 method/case_study/paper_share 类 source (那些是具体方法展开, 不适合 framework 复用)
    - 若 candidate_slide_briefs 里只有 method 类 source, 标 kind=matching_fallback 或 new,
      不要硬塞 method 内容到 framework 章; 但最终 outline 仍必须由 driver 绑定到真实 source 或回滚重写

    **chapter_realized.realized_specifics 必须**:
    - 列**层抽象方向** (e.g. "算法层稀疏化方向" / "系统层调度方向" / "硬件层可重构方向")
    - 也可列 **grounded 具体工作名** (v30 更新, 若 inventory 里有)

    **typical framework 章结构** (参考):
    - 1 张 framework_overview (三层叠加图)
    - 3 对 (痛点 + 抓手) per layer, 共 6 张
    - 1 张 chapter_summary 汇总跨层 + thesis 回扣
    - 总 ≤8 张, framework 章不应超 10 张

    framework 章违例会导致 method 章 (后面的 ch4/5/6) 失去"先抽象总览再具体展开"的层次感.

18. **v34 source-binding hard rules (对应 logic_story/source_binding)**:

    - `structural_pages_require_structural_sources`: 结构页只能绑定结构型源页; 普通内容页不能作为
      chapter_divider/framework_recap/agenda 的最终 source。
    - `distinct_neighbor_slides_require_distinct_sources`: 不同目标页默认不得复用同一 top-1 source;
      只有显式 `same_source_intent.allowed=true` 且为结构模板/总览局部解释时才允许。
    - `matching_fallback_not_final_outline_source`: `matching_fallback` / `weak_*` 是 review 信号,
      不是最终 outline 状态. 输出时必须暴露弱绑定原因, 让 OUTLINE review 能修, 不能把它隐含到
      gapcard 阶段。
    - `content_pages_do_not_use_navigation_sources`: 普通内容页不能绑定 TOC/Contents/目录/章节导航源页。
    - `overview_source_identity_matches_deck_owner`: 总领页 source 的叙述对象层级必须与 target 一致。
    - `framework_claim_not_narrower_than_target`: framework source 的覆盖范围不能窄于 target。
    - `work_block_stays_on_same_work`: 同一代表工作 block 内不能突然切到另一个工作。

---

## Anti-rules

- ❌ 不要 fabricate 具体数字 (v28: 库无支撑就写能力性描述, **不再走 gap_research 补齐路径**; 若属于风格不统一填 style_unification_hint)
- ❌ 不要硬塞 source_resource_ids: 若候选都不合适 (rank_score ≤ 0.5), 标 source_carrier_resource_kind=new
- ❌ 不要重写 stub 字段 (slide_index/role/archetype/placement — 那是 Stage 1a 的决策)
- ❌ 不要让多张 slide 的 target_claim 完全重复 (claim_quality 重复 ≥3 章)
- ❌ 不要让 anchor_terms 在该章首次出现页缺失 (违反 anchor_trajectory)
- ❌ 不要忘 thesis_callback / framework_recap 在 narrative_constraints_slice 指定的页落实
