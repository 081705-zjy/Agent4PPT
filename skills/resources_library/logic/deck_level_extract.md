# Deck-Level Logic Extractor

你正在从**整个 PPT 语料库**里**抽取 deck-level 叙事 pattern**。每个 pattern 描述"一类整本 deck 的故事架构",
带 **carriers** 字段指向真实活体的源 deck (含具体 structural_slides + chapter_outline)。

**为什么 deck-level**: 这层 pattern 回答"整本 deck 的骨架长什么样" — 章节顺序、章节角色组合、首尾结构页位置。
后续 IDEA_ANALYSIS 阶段会从这层选用 pattern 决定整 deck 切几章、各章做什么。每个 pattern 自带的 carriers
让 OUTLINE / SLIDE_MATCHING 能直接复用源 deck 的 structural slide (cover/agenda/framework_intro/divider/closing)。

---

## Inputs (按 batch 调用)

```json
{
  "batch_index": 0,                                  // 0..N-1 (总 deck 分成 N batch, 每 batch 大小由 driver 决定)
  "decks_in_this_batch": [
    {
      // === deck.json 完整字段 ===
      "deck标识": "tpl.topic.论文分享.6b133f9d6028",
      "目录名": "1b1ffbac-b71b-4079-b990-5c9ac1af6776",
      "标题": "...",
      "源文件": "...",
      "画布尺寸": [9144000, 5143500],
      "总页数": 24,
      "章节数": 7,
      "章节列表": [...],
      "主题标签": [...],
      "目标受众": "...",
      "报告类型": "paper_share",
      "适用场景": "...",
      "论述总结": "...",
      "论述弧线": [...],
      "适合复用场景": [...],
      "不适合复用场景": [...],

      // === 全部 section.json 完整 (该 deck 的所有 section) ===
      "sections": [
        {
          "章节标识": "...sec.01",
          "章节序号": 1,
          "章节角色": "cover",
          "标题": "封面",
          "页码范围": [1, 1],
          "页数": 1,
          "页ID列表": ["slide_01"],
          "章节叙事": "...",
          "页间关系": [...],
          "在deck中的位置": "...",
          "适合复用场景": [...],
          "不适合复用场景": [...]
        },
        ...
      ],

      // === structural slide.json 完整 (仅 cover/agenda/section_divider/closing/references 这些骨架页) ===
      // 跳过 content_candidate slide; 节省 context. 但 cover_candidate / toc_candidate /
      // chapter_candidate / ending_candidate 这些 slide_role 的 slide.json **必须**全字段给
      "structural_slides_full": [
        {
          "页序号": 1,
          "页面角色": "cover_candidate",
          "所属章节": "...sec.01",
          "标题": "...",
          "核心论断": "...",
          "本页讲什么": "...",
          "关键文字": [...],
          "视觉骨架": [...],
          "上页角色": null,
          "下页角色": "..."
        },
        ...
      ]
    },
    ... × N (本 batch 的所有 deck, N = 输入中 decks_in_this_batch 长度)
  ],
  "previous_batches_patterns": [                    // ← 跨 batch dedup 用
    {"id": "research_report_works_panorama",
     "applicable_when": {...},
     "abstract_node_sequence": [...],
     "applicable_summary": "..."},
    ...
  ]
}
```

**Driver 按 batch 调用**:
- 语料库被分成 N 个 batch, batch_size 由 driver 决定 (典型 4)
- batch 0: previous_batches_patterns = []
- batch 1+: previous_batches_patterns = 前面所有 batch 输出的 pattern (id + 关键字段, 不含 carriers — carriers 由 driver 后处理跨 batch 累加)

---

## Output: `deck_level_patterns_batch_<N>.json`

```json
{
  "batch_index": 0,
  "patterns": [
    {
      "id": "research_report_works_panorama",          // ← 唯一 id, snake_case
      "title": "研究报告·多工作平行陈列",                  // 短中文标题
      "applicable_when": {
        "report_type": ["research_report", "lab_introduction"],
        "scenario_keywords": ["对外汇报展示", "课题组介绍"],
        "deck_size_range": [40, 90],
        "audience_levels": ["技术中高级", "学术同行"]
      },
      "abstract_node_sequence": [                      // ← 整本 deck 抽象骨架
        {"role": "cover",              "count": 1,        "position": "fixed_1"},
        {"role": "agenda",             "count": 1,        "position": "fixed_2"},
        {"role": "motivation_section", "section_count": 1, "page_count_range": [3, 8]},
        {"role": "framework_intro",    "count": 1,        "position": "after_motivation"},
        {"role": "method_works_panorama_section", "section_count": "N_works (3-5)",
         "page_count_per_section_range": [8, 14]},
        {"role": "discussion_section", "section_count": "0-1"},
        {"role": "closing",            "count": 1,        "position": "last"}
      ],
      "narrative_arc": ["motivation", "framework", "代表工作 1", "代表工作 2", "代表工作 3", "讨论/致谢"],
      "applicable_summary": "整本 deck 通过 N 个代表工作平行展示, 中间用 framework 总图统领",
      "anti_patterns": [
        "单工作深挖型 (paper_share 一篇论文): 用 single_paper_canonical pattern, 不要套这个",
        "工业 demo (live demo + screenshot): 节奏完全不同"
      ],

      // === carriers: 本 batch 中命中此 pattern 的全部 deck (不限数, 多就多) ===
      "carriers": [
        {
          "deck_id": "tpl.topic.对外汇报展示.戴国浩-...",
          "deck_title": "戴国浩-高效大模型推理技术与应用",
          "deck_topic_tags": ["大模型推理", "投机解码", "稀疏激活", "软硬件协同"],   // ← 从 deck.主题标签 抄
          "match_evidence": "整本 60 张 deck: 1 cover + 1 agenda + 6p motivation + 4p framework + 22p method (4 工作) + 7p outlook + 1 closing",

          // === structural_slides: 整本骨架页, 每张带具体内容 (从 slide.json 直接抄, 不改写) ===
          "structural_slides": [
            {
              "slide_index": 1,
              "role_in_deck": "cover",
              "archetype": "cover_method_name_with_authors",
              "slide_title": "高效大模型推理技术与应用",         // ← 从 slide.json.标题 抄
              "slide_claim": "",                                  // ← 从 slide.json.核心论断 抄 (cover 可为空)
              "slide_key_text": ["戴国浩", "上海交通大学", "2024.4"],  // ← 从 slide.json.关键文字 抄
              "slide_visual_skeleton": ["主标题居中", "作者署名行", "logo"]  // ← 从 slide.json.视觉骨架 抄
            },
            {
              "slide_index": 2,
              "role_in_deck": "agenda",
              "archetype": "agenda_long_deck_navigation",
              "slide_title": "目录",
              "slide_claim": "",
              "slide_key_text": ["1. 背景", "2. 框架", "3. 代表工作", "4. 未来方向"],
              "slide_visual_skeleton": ["大字编号列表", "章节标题"]
            },
            {
              "slide_index": 9,
              "role_in_deck": "framework_intro",
              "archetype": "framework_master_diagram_overview",
              "slide_title": "软硬件协同优化的 6 层框架",
              "slide_claim": "软硬件协同 = 算法层+系统层+硬件层 6 层联动",
              "slide_key_text": ["算法层", "系统层", "硬件层", "tokens/J"],
              "slide_visual_skeleton": ["6 层堆叠示意图", "层间连线"]
            },
            ... (cover/agenda/各 section_divider/framework_intro/closing, 一般 5-10 张, 每张都带 4 字段内容)
          ],

          // === chapter_outline: 整本切章表 (供 IDEA 章节切分参考) ===
          "chapter_outline": [
            {"chapter_role": "cover",      "section_id": "section_01_封面", "slide_range": [1, 1]},
            {"chapter_role": "agenda",     "section_id": "section_02_目录", "slide_range": [2, 2]},
            {"chapter_role": "motivation", "section_id": "section_03_研究背景", "slide_range": [3, 8]},
            {"chapter_role": "framework",  "section_id": "section_04_六层框架", "slide_range": [9, 13]},
            {"chapter_role": "method",     "section_id": "section_05_代表成果一", "slide_range": [14, 24]},
            ...
            {"chapter_role": "closing",    "section_id": "section_09_致谢", "slide_range": [60, 60]}
          ]
        },
        {
          "deck_id": "tpl.topic.对外汇报展示.孙广宇-...",
          ... (本 batch 中第二个命中 carrier deck, 同样字段)
        }
        // 本 batch 中所有命中此 pattern 的 deck 全都列出, 不限数. driver 后处理跨 batch 合并
      ],
      "source_count_in_this_batch": 2,                  // = len(carriers) in this batch only
      "confidence_estimate": "medium"                   // 跨 batch 合并后 driver 会重算
    },
    ... (本 batch 抽出的 deck_level patterns, 每 batch 预期 2-5 条)
  ],
  "extraction_notes": "本 batch 7 deck 中抽出 N 条 pattern, 跨 batch 已和 previous_batches_patterns 对照",
  "coverage": {
    "decks_in_batch": 7,
    "decks_assigned_to_some_pattern": 6,
    "decks_unassigned_in_this_batch": ["<deck_id 列表>"],
    "decks_assigned_to_multiple_patterns": []
  }
}
```

---

## Field semantics

- **`id`**: snake_case, 描述性, 唯一. 命名约定: `<report_type>_<distinguishing_feature>` (如 `paper_share_problem_method_results`, `lab_introduction_panorama_with_works`, `research_report_works_panorama`)
- **`applicable_when`**: 4 个匹配维度. **不**要把所有 deck 的 features 都列上,只列**这条 pattern 显著区分于其他 pattern 的特征**
- **`abstract_node_sequence`**: 从 carriers 归纳出的整 deck 骨架. `role` 用以下枚举:
  `cover / agenda / motivation_section / problem_section / framework_intro / method_section / method_works_panorama_section / result_section / discussion_section / engineering_section / outlook_section / references / closing`
- **`narrative_arc`**: 自然语言版本 (≤8 项), 给 IDEA 看 deck-level 故事弧
- **`carriers[].structural_slides`**: 限定整本 deck 的**骨架页** (cover / agenda / section_divider / framework_intro / closing / references), **不**要列 content 页. 一般 5-10 张. 每张含 7 字段:
  - `slide_index / role_in_deck / archetype` (Claude 判断)
  - `slide_title / slide_claim / slide_key_text / slide_visual_skeleton` (**直接从 input.decks_in_this_batch[i].structural_slides_full 抄, 不要改写**)
- **`carriers[].chapter_outline`**: 整本切章表 — 每章 1 行. `chapter_role` 用以下枚举:
  `cover / agenda / motivation / problem / framework / method / comparison / result / engineering / discussion / outlook / references / closing`
- **`carriers[].deck_topic_tags`**: 直接从 input.decks_in_this_batch[i].主题标签 抄 (≤8 个 tag, 给后续 brief 主题匹配用)
- **`source_count_in_this_batch`**: = len(carriers) **本 batch 内**. 跨 batch 合并由 driver 算 total source_count
- **`confidence_estimate`**: 本 batch 估算 — 3+ carrier → high, 2 → medium, 1 → low. driver 跨 batch 合并后会重新算

---

## 标准 archetype 词汇表 (优先用表内词)

为防止跨 batch 命名漂移 (e.g. `cover_with_authors` / `cover_authors_block` / `cover_team_signature` 其实是同义),
Claude 选 `archetype` 时**优先匹配下表**。表内没有的, 按命名规则 `<role_prefix>_<布局描述>` 起新名,
并在 `extraction_notes` 末尾追加 "new_archetype: <name> — <一句话定义>" 行供 driver 后处理审计。

### Cover (封面)
- `cover_method_name_with_authors` — 主标题(方法名)+作者署名+单位
- `cover_team_intro_with_logo` — 团队/课题组名+logo+成员合影
- `cover_topic_with_subtitle_tag` — 主标题+副标题+主题标签
- `cover_single_title_centered` — 仅大标题居中, 无副信息

### Agenda (目录)
- `agenda_long_deck_navigation` — 编号列表式 (1. 2. 3. ...) 通常 ≥6 章
- `agenda_outline_with_section_titles` — 章节标题列+图标/编号
- `agenda_mini_summary_per_chapter` — 每章一句话 summary 的目录

### Section divider (章节切换)
- `section_divider_chapter_label` — 大字章号+章名, 无内容
- `section_divider_mini_agenda_highlight` — 全 agenda 灰显 + 当前章高亮
- `section_divider_chapter_with_subtitle` — 章号+章名+副标题铺垫

### Framework intro (框架统领页)
- `framework_master_diagram_overview` — 整个 deck 框架总图
- `framework_layered_components_explained` — 分层结构 + 各层说明
- `framework_pipeline_or_workflow` — 流水线/工作流框架图

### Closing (收尾)
- `closing_summary_and_outlook` — 工作小结 + 展望
- `closing_thanks_and_qa` — Thanks/Q&A + 联系方式
- `closing_industrial_landing_and_vision` — 工业落地 + 远景

### References (参考文献)
- `references_paper_list_dense` — 密集 bibliography 列表
- `references_paper_thumbnails_grid` — 论文封面缩略图网格

**扩展规则**:
- 新 archetype 必须 snake_case, 全小写, `_` 分词
- 命名形如 `<role>_<distinguishing_layout>`, 例: `cover_team_intro_with_logo`
- 不要重复表内词. 不确定时优先用表内最接近词

---

## Process (按这个顺序做)

### Step 1: Cluster 本 batch 7 deck
按以下信号给本 batch 7 deck 聚类:
- 报告类型 (paper_share / research_report / lab_introduction / demo / etc.)
- 总页数桶 (≤30 / 30-60 / >60)
- 章节数桶 (≤4 / 5-7 / 8+)
- 论述弧线词的相似度
- 章节列表的 章节角色 sequence 是否相近

预期 2-5 个 cluster, 每个 cluster 对应 1 个候选 pattern.

### Step 2: 跨 batch 对照 (重要)
读 `previous_batches_patterns`:
- 本 batch 找到的某 cluster 跟 previous 中某 pattern 的 applicable_when + abstract_node_sequence 高度重合 (>80%) → 视作**同 pattern**, **用 previous 的 id**, carriers 只列本 batch 新发现的 deck (driver 后处理累加)
- 否则 → 新 pattern, 起新 id

### Step 3: 对每个 cluster 写 pattern
对该 cluster 的 deck:
- 找它们**共同**的 chapter_role sequence (abstract_node_sequence)
- 列**所有共同特征**作 applicable_when
- 选**本 batch 中命中**的 deck 全列为 carriers (**不限数**)
- 每个 carrier 填:
  - structural_slides — 该 deck 的骨架页, 每张从 structural_slides_full 抄 4 字段
  - chapter_outline — 从 sections 派生 (每 section 1 行)
  - deck_topic_tags — 从 deck.主题标签 抄
  - match_evidence — Claude 写一句话, 说该 deck 怎么体现 pattern

### Step 4: 内置 dedup (产出前自检)
扫描本 batch 抽出的所有候选 pattern, 找近义 pattern (id 不同但 applicable_when 高度重合 + abstract_node_sequence 高度相似):
- 完全等价 → 合并 (取更具描述性的 id, 合并 carriers)
- 95% 重合但有细微差异 → 看差异是否本质. 是 → 保留两条; 不是 → 合并

### Step 5: 算 coverage
统计本 batch 中:
- 多少个 deck 被分到某 pattern 的 carriers (decks_assigned_to_some_pattern)
- 多少个 deck 没被任何 pattern 收 (decks_unassigned_in_this_batch) — 列 ID 但**不**为它们硬造 pattern
- 跨多个 pattern 的 deck — 列 ID

---

## Hard rules

- **carriers ≥1 必须**: 任何 pattern 在本 batch 内至少 1 deck 命中 (跨 batch 累加由 driver 处理)
- **carriers 不限数**: 本 batch 中所有命中此 pattern 的 deck 都要列, **不要**限 top-N
- **structural_slides 4 内容字段必须从 input 抄**: slide_title / slide_claim / slide_key_text / slide_visual_skeleton 不允许 Claude 改写 — 直接 1:1 copy 自 input.decks_in_this_batch[i].structural_slides_full
- **slide_index / 页号必须真实**: 从 input.decks_in_this_batch[i].structural_slides_full[j].页序号 抄, 不可虚构
- **chapter_outline 必须真实**: 从 input.decks_in_this_batch[i].sections[j].页码范围 派生
- **abstract_node_sequence 不可超出 narrative_arc 描述的范围**: 这两个字段应该一致
- **id 唯一**: 同 batch 内不能有重复 id
- **applicable_when 不可空**: 至少含 `report_type` 或 `scenario_keywords` 之一
- **跨 batch dedup 必做**: 看 previous_batches_patterns 决定起新 id 还是用 existing id
- **batch 内 dedup 必做**: 不重复 emit 等价 pattern
- **archetype 优先用标准词汇表**: 选 archetype 字段时优先匹配 "## 标准 archetype 词汇表" 表内词. 新发明的 archetype 必须 snake_case 命名 + 在 `extraction_notes` 末追加 "new_archetype: <name> — <一句话定义>"
- **outlier structural_slide 处理**: 若某 structural slide 不属于 abstract_node_sequence 的任何 role, **仍必须列入** carrier.structural_slides, `role_in_deck` 标 `"off_pattern"` (新增枚举值), archetype 字段照常填该 slide 自己的版式. driver 后处理可选过滤
- **role_in_deck ∈ {opening, cover, agenda, self_intro, section_divider, framework_intro, appendix, closing, references, off_pattern}**: role_in_deck 的全部允许值 (含 v30 新加 opening/self_intro/appendix)
- **不要**: 自己发明 chapter_role 枚举之外的 role (opening/cover/agenda/self_intro/motivation/problem/framework/method/comparison/result/engineering/discussion/outlook/references/appendix/closing)。如果 deck 章节角色超出枚举, 用最接近的 + 在 applicable_summary 里说明

---

## Output format

- Strict JSON only, no markdown fences, no prose preamble
- 顶层只有 `batch_index` + `patterns` + `extraction_notes` + `coverage`
- patterns[] 按 source_count_in_this_batch desc 排序
