# Section-Level Logic Extractor

你正在从**整个 PPT 语料库**里**抽取 section-level 叙事 pattern**。每个 pattern 描述"一类章节内部
的节奏 + 章内每张 slide 的角色 + 上下页关系", 带 **carriers** 字段指向真实活体的源 section
(含 slide-level 每张标 role_in_pattern + archetype + **具体讲解内容**)。

**为什么 section-level**: 这层 pattern 回答"某种 chapter_role 的章节内部怎么展开" —
motivation 章的痛点漏斗节奏、method 章的 problem→solution 对、result 章的数字头条 + 前后对比 等。
后续 IDEA_ANALYSIS 用这层 pattern 决定每章 page_archetype 节奏 + 拿 carriers 给 OUTLINE
用作 slide bound (每页直查 carrier slide 复用)。后续 brief 阶段会基于 pattern 的**逻辑** + carrier 的
**具体讲解内容** 双维度检索匹配项目主题的 slide,所以每张 carrier slide 必须带具体内容。

---

## Inputs

```json
{
  "batch_index": 0,                              // 0..3 (4 个 batch)
  "decks_in_this_batch": [
    {
      "deck标识": "tpl.topic.论文分享.6b133f9d6028",
      "标题": "...",
      "报告类型": "paper_share",
      "适用场景": "...",
      "主题标签": [...],
      "sections": [
        {
          "章节标识": "tpl.topic.论文分享.6b133f9d6028.sec.02",
          "章节序号": 2,
          "章节角色": "motivation",
          "标题": "大模型推理的内存算力挑战",
          "页码范围": [2, 4],
          "页数": 3,
          "章节叙事": "deck 的问题引入章, 承接封面后为后续压缩方法立靶...",
          "页间关系": [
            "slide 2 → slide 3: 由章节封面页过渡到 LLM 受关注的背景铺陈",
            "slide 3 → slide 4: 由 LLM 普及引出 attention/softmax 的内存算力开销"
          ],
          "适合复用场景": [...],
          "在deck中的位置": "第 2 章 motivation, 紧跟封面, 为方法章节铺垫",
          "slides": [
            {
              "页序号": 2, "页面角色": "content_candidate",
              "标题": "背景与挑战: 技术综述导引页",
              "核心论断": "大模型推理面临内存与算力双重挑战, 需系统性技术应对",
              "本页讲什么": "本页是「背景与挑战」章节的导引页...",
              "关键文字": [...],
              "视觉骨架": ["章节标题文字块", "多图卡片网格", "项目符号引导列表"],
              "上页角色": "content_candidate",
              "下页角色": "content_candidate"
            },
            ... (该 section 的全部 slides — 完整 slide.json)
          ]
        },
        ... (该 deck 的全部 sections)
      ]
    },
    ... × N (本 batch 的所有 deck, N = 输入中 decks_in_this_batch 长度)
  ],
  "previous_batches_patterns": [                 // ← 跨 batch dedup 用
    {"id": "motivation_funnel_macro_to_pain",
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
- batch 1+: previous_batches_patterns = 前面所有 batch 输出的 pattern (id + 关键字段, 不含 carriers)

---

## Output: `section_level_patterns_batch_<N>.json`

```json
{
  "batch_index": 0,
  "patterns": [
    {
      "id": "motivation_funnel_macro_to_pain",        // ← 唯一 id, snake_case
      "title": "动机·宏观漏斗至痛点",                    // 短中文标题
      "applicable_when": {
        "chapter_role": ["motivation", "background"],   // 哪类章节
        "report_type": ["all"],                          // 哪类 deck 通用, 或具体
        "page_count_range": [3, 8],                      // 章内页数
        "must_have_in_chapter_purpose": ["背景", "挑战", "动机"]
      },
      "abstract_node_sequence": [                      // ← 章内 archetype 节奏 (抽象, 从 carriers 归纳)
        {"archetype": "macro_trend_chart", "count": 1, "position": "start", "purpose": "macro 趋势铺陈"},
        {"archetype": "domain_pain_point_callout", "count": "1-2", "position": "middle", "purpose": "把宏观 → 落到本领域痛点"},
        {"archetype": "quantitative_gap_chart", "count": "0-1", "position": "before_end", "purpose": "用数据放大痛感"},
        {"archetype": "transition_to_method", "count": 1, "position": "end", "purpose": "立靶, 引出后续方法章"}
      ],
      "page_transitions_pattern": [                    // ← 章内上下页关系 (抽象)
        {"from_archetype": "macro_trend_chart", "to_archetype": "domain_pain_point_callout",
         "hook_type": "from_general_to_specific"},
        {"from_archetype": "domain_pain_point_callout", "to_archetype": "quantitative_gap_chart",
         "hook_type": "amplify_with_data"},
        {"from_archetype": "quantitative_gap_chart", "to_archetype": "transition_to_method",
         "hook_type": "pain_to_solution_bridge"}
      ],
      "applicable_summary": "由 macro 趋势 (token 量爆炸 / 模型规模等) 漏斗到本领域具体痛点的 motivation 章 pattern",
      "anti_patterns": [
        "纯 problem-only 无 macro 铺垫 (3 页都谈痛点, 上下文跳跃) — 用 problem_only_direct pattern",
        "纯 background 无 pain (3 页都讲历史无落点) — 用 background_only_chronology pattern"
      ],

      // === carriers: 本 batch 中命中此 pattern 的全部 section (不限数) ===
      "carriers": [
        {
          "deck_id": "tpl.topic.论文分享.6b133f9d6028",
          "deck_title": "SpAct-NDP：稀疏激活近数据计算加速大模型推理",
          "deck_topic_tags": ["大模型推理", "稀疏激活", "近数据计算"],   // ← 从 deck.主题标签 抄
          "section_id": "tpl.topic.论文分享.6b133f9d6028.sec.02",
          "section_title": "大模型推理的内存算力挑战",                    // ← 从 section.标题 抄
          "section_role": "motivation",                                  // ← 从 section.章节角色 抄
          "section_narrative": "deck 的问题引入章, 承接封面后为后续压缩方法立靶, 由 LLM 崛起切入...",  // ← 从 section.章节叙事 抄
          "section_topic_tags": ["大模型推理", "内存算力挑战", "attention 开销"],  // ← Claude 综合 section 内容总结 ≤5 tag, 给 brief 主题匹配用
          "match_evidence": "3 页节奏: 导引(macro_trend) + LLM 普及(domain_pain) + attention 开销数据(quantitative_gap)",

          // === slides: 每张 slide 标 role_in_pattern + archetype + 带具体讲解内容 ===
          "slides": [
            {
              "slide_index": 2,
              "role_in_pattern": "macro_trend_chart",                  // ← 该 slide 在 pattern 中担任的角色 (必 ∈ abstract_node_sequence[].archetype 集合)
              "archetype": "intro_panel_with_image_cards",             // ← 该 slide 的版式 archetype
              // ↓ 4 内容字段, 直接从 input slide.json 抄, 不要改写
              "slide_title": "背景与挑战: 技术综述导引页",                 // ← 从 slide.标题 抄
              "slide_claim": "大模型推理面临内存与算力双重挑战, 需系统性技术应对",  // ← 从 slide.核心论断 抄
              "slide_key_text": ["Background and Challenge Techniques"],   // ← 从 slide.关键文字 抄
              "slide_visual_skeleton": ["章节标题文字块", "多图卡片网格", "项目符号引导列表"]  // ← 从 slide.视觉骨架 抄
            },
            {
              "slide_index": 3,
              "role_in_pattern": "domain_pain_point_callout",
              "archetype": "single_text_centric_pain_statement",
              "slide_title": "LLM 普及与算力开销",
              "slide_claim": "大模型在产业大规模铺开, 推理负担激增",
              "slide_key_text": ["GPT", "Claude", "deployment scale"],
              "slide_visual_skeleton": ["大字标题", "趋势图", "数字标注"]
            },
            {
              "slide_index": 4,
              "role_in_pattern": "quantitative_gap_chart",
              "archetype": "single_chart_with_callout_number",
              "slide_title": "Attention/Softmax 开销拆解",
              "slide_claim": "Attention/Softmax 操作占推理时间 30-40%, 内存带宽是瓶颈",
              "slide_key_text": ["Attention", "Softmax", "memory bandwidth", "30-40%"],
              "slide_visual_skeleton": ["柱状图", "数字头条", "组件拆解"]
            }
          ]
        },
        {
          "deck_id": "tpl.topic.对外汇报展示.戴国浩-...",
          ... (本 batch 中第二个命中 section, 同样字段)
        }
        // 本 batch 中所有命中此 pattern 的 section 全列, **不限数**
      ],
      "source_count_in_this_batch": 2,                // = len(carriers) in this batch only
      "confidence_estimate": "medium"                 // driver 跨 batch 合并后会重算
    },
    ... (本 batch 抽出的 section_level patterns, 预期每 batch 8-15 条)
  ],
  "extraction_notes": "本 batch 7 deck 共 N section, 抽出 M patterns, 跨 batch dedup K patterns 合并到 previous_batches",
  "coverage": {
    "sections_assigned_to_some_pattern": <count>,
    "sections_unassigned_in_this_batch": ["<section_id 列表>"]
  }
}
```

---

## Field semantics

- **`id`**: snake_case, 描述性, 唯一. 命名约定: `<chapter_role>_<distinguishing_pattern>` 例如:
  - `motivation_funnel_macro_to_pain`, `motivation_problem_only_direct`, `motivation_background_chronology`
  - `method_works_panorama_paper_pair`, `method_single_method_deep_dive`, `method_pipeline_step_by_step`
  - `result_callout_then_compare`, `result_table_systematic`, `result_ablation_grid`
- **`abstract_node_sequence`**: 章内**抽象** archetype 序列. archetype 命名 snake_case (`macro_trend_chart` / `domain_pain_point_callout` / `single_paper_title_authors` / etc.). count 可以是数字或 "1-N" 或 "0-1"
- **`page_transitions_pattern`**: 章内每两张相邻 slide 的过渡 hook_type. 枚举:
  `from_general_to_specific / amplify_with_data / pain_to_solution_bridge / parallel_continuation /
   problem_to_solution / before_to_after / cause_to_effect / overview_to_detail / detail_to_overview /
   data_then_implication / claim_then_evidence / method_then_result / chapter_handoff`
- **`carriers[].deck_topic_tags`**: 直接从 input.decks_in_this_batch[i].主题标签 抄 (≤8 tag)
- **`carriers[].section_topic_tags`**: Claude 综合该 section 全部 slide 的 标题/核心论断/关键文字, 总结 ≤5 个主题 tag (给后续 brief 主题匹配用). **不是**从 deck 整体 tag 抄, 而是该 section **具体**讲什么主题
- **`carriers[].section_narrative`**: 直接从 input section.章节叙事 抄 (不改写)
- **`carriers[].section_title / section_role`**: 直接从 input section.标题 / 章节角色 抄
- **`carriers[].slides[].role_in_pattern`**: 该 slide 在 pattern 抽象节奏里担任哪个 archetype. **必须**取自 abstract_node_sequence[].archetype 集合
- **`carriers[].slides[].archetype`**: 该 slide 自己的版式分类 (页面级 archetype, 不必和 role_in_pattern 同名). 命名规则: `single_<内容类型>_<布局描述>` 例如 `single_chart_with_callout_number`, `single_paper_title_authors_only`, `architecture_overview_dense_diagram`
- **`carriers[].slides[].slide_title / slide_claim / slide_key_text / slide_visual_skeleton`**:
  **直接从 input slide.json 抄 (1:1)**, 不允许 Claude 改写. 来源映射:
  - `slide_title` ← `slide.标题`
  - `slide_claim` ← `slide.核心论断`
  - `slide_key_text` ← `slide.关键文字`
  - `slide_visual_skeleton` ← `slide.视觉骨架`
- **`source_count_in_this_batch` / `confidence_estimate`**: 同 deck_level (driver 跨 batch 合并后重算)

---

## 标准 archetype 词汇表 (优先用表内词)

为防止跨 batch 命名漂移 (e.g. `single_chart_with_callout_number` / `chart_with_big_number` / `single_number_callout` 其实是同义),
Claude 选 `archetype` / `role_in_pattern` 时**优先匹配下表**。表内没有的, 按命名规则
`<role_prefix>_<布局描述>` 起新名, 并在 `extraction_notes` 末尾追加
"new_archetype: <name> — <一句话定义>" 行供 driver 后处理审计。

### Trend / data archetype (趋势数据)
- `macro_trend_chart` — 宏观时序趋势 (年份×指标 曲线/柱)
- `domain_pain_point_callout` — 本领域痛点陈述 + 大字数字
- `quantitative_gap_chart` — 差距/缺口可视化 (柱对比/箭头标注)
- `time_series_line_chart` — 一般时序折线图
- `comparison_bar_chart` — 横/纵向对比柱图
- `pie_or_distribution_chart` — 占比/分布饼图或环图

### Paper / work title (论文 / 工作扉页)
- `single_paper_title_authors_only` — 大字论文标题 + 作者署名
- `single_method_name_with_one_line_tagline` — 方法名 + 一句话定位
- `work_intro_with_thumbnail_and_metadata` — 工作缩略图+ 标题/作者/会议
- `paper_cover_grid_overview` — N 个论文封面缩略图栅格

### Pain / problem statement (痛点 / 问题)
- `single_text_centric_pain_statement` — 大字文本陈述痛点
- `single_text_centric_definition_box` — 定义/术语解释方框
- `problem_breakdown_three_pillars` — 痛点拆解成 2-4 个维度
- `industry_pain_specific_callout` — 工业落地痛点 + 实例

### Framework / overview (框架 / 总览)
- `single_framework_recall_5layer_diagram` — 多层框架总图 (3-7 层)
- `framework_layered_components_explained` — 分层 + 每层说明
- `pipeline_step_by_step_diagram` — 流水线/工作流分步图
- `intro_panel_with_image_cards` — 多图卡片网格章节导引

### Method / architecture (方法 / 架构)
- `single_method_problem_then_solution_pair` — 同页问题→方案双栏
- `architecture_overview_dense_diagram` — 完整架构密集图
- `algorithm_block_diagram` — 算法/数据流方框图
- `equation_centric_derivation` — 公式推导核心
- `before_after_optimization_compare` — 优化前后对比 (有/无 method)

### Result / experiment (结果 / 实验)
- `single_experiment_result_speedup_callout` — 关键加速比头条 + 数字
- `result_table_systematic` — 实验表格 (横/纵向多组)
- `ablation_grid_systematic` — 消融实验栅格
- `case_study_screenshot_with_caption` — case study 截图 + 说明

### Transition / structure (过渡 / 结构页)
- `transition_chapter_handoff` — 章末过渡到下章的桥页
- `single_section_intro_panel` — 章首导引页
- `image_only_background_visual` — 单图视觉/背景图
- `breaker_inspirational_quote` — 引文/警句 breaker

**扩展规则**:
- 新 archetype 必须 snake_case, 全小写, `_` 分词
- 命名形如 `<role_prefix>_<distinguishing_layout>`, 例: `single_paper_title_with_qr_code`
- 不要重复表内词. 不确定时优先用表内最接近词

---

## Process (按这个顺序做)

### Step 1: Index 输入 sections by chapter_role
扫描本 batch 7 deck 的全部 sections, 按 `章节角色` 分桶:
- motivation 桶: [...]
- problem 桶: [...]
- method 桶: [...]
- ...

每桶内 section 数预期 5-15 个 (语料库平均 ~6 section/deck × batch_size deck)

### Step 2: 对每桶找子 cluster
桶内 section 不一定是同一 pattern, 子聚类:
- motivation 桶可能拆出 `funnel_macro_to_pain` / `problem_only_direct` / `background_chronology` 3 个 pattern
- method 桶可能拆出 `works_panorama_paper_pair` / `single_method_deep_dive` / `pipeline_step_by_step` 3 个 pattern

子 cluster 标准: 同样的 abstract_node_sequence ± page_transitions_pattern.

### Step 3: 对每个 cluster 写 pattern
- 给抽象 archetype 节奏 (abstract_node_sequence)
- 给上下页过渡模式 (page_transitions_pattern)
- 列 carriers (**该 cluster 的全部 section, 不限数**), 每个 carrier 填:
  - deck_id / deck_title / deck_topic_tags (从 deck 抄)
  - section_id / section_title / section_role / section_narrative (从 section.json 抄)
  - section_topic_tags (Claude 综合归纳, ≤5 tag)
  - match_evidence (Claude 写一句, 说该 section 怎么体现 pattern)
  - slides: 每张 slide 标 role_in_pattern + archetype + **从 slide.json 1:1 抄 4 字段** (slide_title / slide_claim / slide_key_text / slide_visual_skeleton)
- 写 applicable_when + applicable_summary + anti_patterns

### Step 4: 跨 batch dedup
读 `previous_batches_patterns`:
- 如果某新 pattern 跟 previous 已存在某条**applicable_when + abstract_node_sequence 高度重合** (>80%) → 视作同 pattern, **用 previous 的 id**, 但 carriers 只列本 batch 新发现的 section (driver 会合并)
- 否则 → 新 pattern, 起新 id

### Step 5: 内置 batch 内 dedup (产出前自检)
产出前扫描本 batch 抽出的所有 pattern, 找近义合并 (跟 deck_level_extract 同规则)

### Step 6: 算 coverage
- sections_assigned_to_some_pattern: 本 batch 中被某 pattern 收为 carrier 的 section 数
- sections_unassigned_in_this_batch: 没被任何 pattern 收的 section 列 ID

---

## Hard rules

- **carriers ≥1 必须**: 同 deck_level
- **carriers 不限数**: 本 batch 中所有命中此 pattern 的 section 都要列, **不要**限 top-N
- **slides 每条必须 7 字段全**: slide_index / role_in_pattern / archetype / slide_title / slide_claim / slide_key_text / slide_visual_skeleton
- **4 内容字段必须从 input slide.json 1:1 抄**: 不允许 Claude 改写 (不允许总结/翻译/重排)
- **role_in_pattern ∈ abstract_node_sequence[].archetype 集合 ∪ {"off_pattern"}**: outlier slide 必须列入 (见下条), 其他 slide 必须命中 abstract 节奏中某 archetype
- **outlier slide 必须列入 carrier.slides**: 若某 slide 不属于 abstract_node_sequence 的任何 archetype (e.g. 章中插了一张过渡图 / 章末有张未被 abstract 覆盖的总结页), **仍必须列入** carrier.slides, `role_in_pattern` 标 `"off_pattern"`, `archetype` 字段照常填该 slide 自己的版式. 这保证 carrier 数据完整, 后续 byte-clone 不漏页. driver 后处理可选过滤
- **slide_index 必须真实**: 从 input slides.页序号 抄
- **section_narrative 必须从 input 抄, 不改写**
- **section_topic_tags 是 Claude 综合, ≤5 tag, 反映该 section 实际讲什么**: 不是从 deck.主题标签 抄
- **archetype 优先用标准词汇表**: 选 `archetype` 字段时优先匹配 "## 标准 archetype 词汇表" 表内词. 新发明的 archetype 必须 snake_case 命名 + 在 `extraction_notes` 末追加 "new_archetype: <name> — <一句话定义>"
- **abstract_node_sequence.archetype 的 count 总和**应**对得上**多数 carriers 的非 off_pattern slides 数 (允许 ±1 弹性). off_pattern slides 不计入 count 校验
- **跨 batch dedup 必做**: 看 previous_batches_patterns 决定起新 id 还是用 existing id
- **batch 内 dedup 必做**: 不重复 emit 等价 pattern
- **不要**: 把同一 carrier section 列在多个 pattern 的 carriers (一个 section 只属一个 pattern. 多 pattern 共存的 section 选最贴的)
- **不要**: 自己发明 chapter_role 之外的 role (motivation / problem / framework / method / comparison / result / engineering / discussion / outlook / closing). 如果 section 角色超出, 选最接近的

---

## Output format

- **CRITICAL — DIRECT STDOUT OUTPUT ONLY**:
  - 你必须**直接输出 JSON 到 stdout**, **绝不**说"我把它写到文件"或"我先写一段说明"
  - 你的**第一个字符必须是 `{`**, 最后一个字符必须是 `}`
  - **No prose preamble.** 不要写"Looking at this batch..." / "I'll analyze..." / "Now I'll write..."
  - **No file write.** 没有文件工具, 必须直接输出
  - **No markdown code fences.** 不要 ` ```json ` 包裹
  - 输出可能很大 (50-200 KB), 没关系, **直接 stream JSON 全部内容**
- Strict JSON only
- 顶层只有 `batch_index` + `patterns` + `extraction_notes` + `coverage`
- patterns[] 按 source_count_in_this_batch desc 排序
- 单 batch 输出文件大小预期 80-200 KB (carrier 不限数后体积比之前大, 每 carrier slide 多 4 字段)
