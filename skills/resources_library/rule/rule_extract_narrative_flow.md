# Rule Extract — Narrative Flow (跨页连贯性 universal rules)

你正在从**整个 PPT 语料库**里**抽取 universal 故事逻辑 rules**。这些规则**不依赖具体主题**, 描述
"任何 ppt 都应该 hold 的跨页连贯性 / 叙事承接 / 重复强调模式"。

跟其他层的区别:
- **logic 库** 的 cross_section_hooks: conditional on chapter_role (e.g. method→result 章间)
- **rule_extract_visual_authoring**: per-slide 层 (布局/写作风格)
- **本 skill**: per-deck 序列层 (跨多张 slide 的语义连贯性)

跟 Python rule_stats.py 的分工:
- Python 算: anchor_first_appearance_page (位置统计), agenda_chapter_match_rate (字符串匹配),
  motivation_before_method (sequence 频率), per_chapter_avg_pages (页数分布)
- **本 skill 做**: 需要语义判断的部分 — 例如"前面提的挑战在后面是否回扣" (verbatim/paraphrased
  匹配), "什么算 quantitative claim", "章末是否埋 hook"

---

## Inputs (per batch, 看 deck 完整 sequence)

```json
{
  "batch_index": 0,
  "decks_in_this_batch": [
    {
      "deck标识": "tpl.topic.论文分享.6b133f9d6028",
      "标题": "...",
      "报告类型": "paper_share",
      "适用场景": "...",
      "论述弧线": [...],
      "章节列表": [...],
      // === 整 deck 全部 slides, 保持顺序 ===
      "slides_in_order": [
        {"slide_index": 1, "页面角色": "cover_candidate", "section_id": "...sec.01",
         "section_role": "cover",
         "标题": "...", "核心论断": "...", "本页讲什么": "...",
         "关键文字": [...], "视觉骨架": [...], "上页角色": null, "下页角色": "..."},
        ... (deck 顺序)
      ],
      "sections_outline": [
        {"section_index": 1, "section_role": "cover", "标题": "封面", "页码范围": [1,1]},
        {"section_index": 2, "section_role": "motivation", "标题": "...", "页码范围": [2,4]},
        ...
      ]
    },
    ... × N (本 batch 的所有 deck, N = decks_in_this_batch 长度)
  ],
  "previous_batches_rules": [                          // ← 跨 batch dedup
    {"id": "motivation_to_method_callback_required",
     "category": "callback",
     "description": "...",
     "applicable_when": "any deck with motivation + method sections"},
    ...
  ]
}
```

---

## 8 大类 narrative_flow rules

每类预期出 1-3 条 rule, 单 batch 总共 ~10-20 条 rule。

### 类 1: 回扣与呼应 (callback)

**抽什么**: 前面 chapter 提出的元素 (挑战 / 主题 / 框架图) 后面 chapter 是否回扣。

典型 rule 范例:
- `motivation_challenges_callback_in_method`: motivation 章列出的 N 个挑战, method 章逐一回应 ≥80% (优秀 deck >95%)
- `cover_title_callback_in_closing`: cover 主标题 / 主 anchor 在 closing 中被 verbatim 或 paraphrased 引用
- `framework_diagram_reuse_in_method`: framework 图 / 6 层划分 在 method 章被引用 ≥1 次
- `agenda_promise_fulfillment`: agenda 中承诺的每章主题在该章首页确实展开

**Claude 判断**:
- "challenge 在 motivation 章被列出" → "method 章里是否提到回应它?" (语义匹配, paraphrase OK)
- "cover 标题 keyword" → 是否在 closing 中重复出现
- 用 hit_carriers 给出具体证据 (e.g. "motivation slide 5 列出 4 个 challenge: A/B/C/D; method slide 12,18,23 回应 A,B,C — 命中 3/4")

### 类 2: 悬念与揭示 (suspense & reveal)

**抽什么**: motivation 提出问题 → method 揭示方案的 setup 模式。

典型 rule 范例:
- `teaser_at_motivation_end`: motivation 章末是否埋 "我们方法 X 解决了这" 钩子 (但不细讲) (~52%, 优秀 deck >85%)
- `problem_solution_distance`: 问题首次提出 → 方案首次揭示之间的页数 (avg 2-4 页. 太远→ deck 散; 太近→ 缺乏 build-up)
- `result_holdback_at_chapter_end`: result 章最炸的数字放在章末 vs 章首 (avg 76% 放末)
- `anti_pattern_show_solution_too_early`: 反模式 — 在 motivation 中就给具体方案数字 (这破坏 build-up)

**Claude 判断**:
- 看 motivation 章末页 是否含"将我们的方法 X 即将展开" 类语义
- 看 result 章首页 vs 末页, 哪页含最大 speedup 数字

### 类 3: 承上启下 (chapter transitions)

**抽什么**: 章间过渡的硬切 vs 衔接。

典型 rule 范例:
- `chapter_outro_hook_required`: 每章末页是否含下章 preview (avg 64%, 优秀 deck >85%)
- `chapter_intro_recap`: 每章首页是否回顾上章 + 引出本章 (avg 48%)
- `naked_pivot_max_rate`: "上下页之间无 hook 硬切" 的比例应 <10% (优秀 deck <3%)
- `mini_agenda_at_chapter_start`: 长 deck (>40 张) 每章首页显示导航 ("你在第 N 章") 的命中率

**Claude 判断**:
- 看章末页 (section_index N 的 last slide) → 是否含下章 preview
- 看章首页 (section_index N+1 的 first slide) → 是否含上章 recap

### 类 4: 重复与强调 (repetition emphasis)

**抽什么**: 关键术语/数字在 deck 中的重复频率。

典型 rule 范例:
- `main_thesis_repeat_count`: 主 thesis (e.g. "软硬件协同") 在 deck 中出现 8-15 次为佳, <5=主题不清, >20=啰嗦
- `main_anchor_chapter_span`: 主 anchor 跨章节比例 (avg 60-80% 章节都提到)
- `key_number_repeat_count`: 关键数字 (e.g. 24×加速) 在 deck 中重复出现 3-5 次为佳
- `framework_diagram_reuse_count`: 框架图在不同章节复现 (motivation 1 次 + method 1-3 次 + closing 1 次)

**Claude 判断**:
- 识别 deck 的"主 thesis" (从 deck.标题 / 论述总结 抽取)
- 看主 thesis / 主 anchor 在哪些 slide 出现 (verbatim 或 paraphrased)

### 类 5: 比较与证据 (comparison & evidence chain)

**抽什么**: result 章用什么证据支撑 claim。

典型 rule 范例:
- `before_after_pair_in_result`: result 章中含 before/after 对比页 (avg 1-2 张 per method)
- `baseline_comparison_density`: result 章中跟 baseline 对比页数 (each method ≥1 张)
- `our_vs_theirs_mention_ratio`: 自己工作 vs baseline 提及比 (优秀 deck 1.5-3:1)
- `claim_evidence_pairing`: 每条 quantitative claim 平均跟 N 张 evidence slide (avg 1.5-2.5)
- `evidence_type_diversity`: result 章用几种 evidence type (charts/tables/case studies/ablations, 优秀 deck 3+ 类)

**Claude 判断**:
- 识别 "quantitative claim" (含 % / × / 具体数字)
- 识别 "evidence slide" (含 chart/table/ablation visual)
- 算 ratio

### 类 6: 关键术语轨迹 (anchor term trajectory)

**抽什么**: 关键术语首次出现位置 + 定义时机。

典型 rule 范例:
- `main_anchor_first_appearance_at_cover`: 主 anchor 首次出现页通常 slide_1 (cover 标题), ~91%
- `jargon_first_definition_distance`: 专业术语首次使用 → 首次定义之间 ≤2 页 (91%)
- `abbreviation_define_at_first_use`: 缩写首次使用时定义 (e.g. "LLM (Large Language Model)") (~82%)
- `secondary_anchor_occurrence`: 次要 anchor 出现 2-3 次为佳

**Claude 判断**:
- 识别"专业术语" / "缩写" (单/双字母组合或专业名词)
- 找首次使用 + 首次定义页, 算距离

### 类 7: 结构性承诺 (structural promise)

**抽什么**: agenda 跟实际 deck 是否对得上。

典型 rule 范例:
- `agenda_chapter_match`: agenda 列出的章节 = 实际 deck.章节列表 (~96%)
- `agenda_chapter_order`: agenda 顺序 = 实际章节顺序 (~98%)
- `chapter_first_page_intro_topic`: 每章首页确实引入该章主题 (~89%)
- `chapter_promise_keeping`: 每章 deliver 该章在 agenda 里承诺的内容 (test plan check off)

**Claude 判断**: 主要 Python 算 (字符串匹配), 但 Claude 可以总结"什么算 deliver" 的语义判断。

### 类 8: 节奏控制 (pacing)

**抽什么**: 不同 chapter_role 的页数分布 + 内容/结构页比例。

典型 rule 范例:
- `per_chapter_avg_pages_by_role`: motivation 4-6 / framework 2-4 / method 8-14 per work / result 3-5 / closing 1-2
- `structural_to_content_ratio`: 结构页 (cover/agenda/divider/closing) 比例 15-25%
- `cover_to_first_content_distance`: cover→agenda→motivation 距离 ≤3 页
- `chapter_role_sequence_invariant`: motivation→framework→method→result→closing 顺序命中率 ~97%

**Claude 判断**: 大部分 Python 算 (统计), 但 Claude 总结"什么算 anomaly" (e.g. method 章只 2 页就异常少)。

---

## Output: `narrative_flow_rules_batch_<N>.json`

```json
{
  "batch_index": 0,
  "rules": [
    {
      "id": "motivation_challenges_callback_in_method",
      "category": "callback",                            // 1..8 类之一
      "applicable_when": "deck has both motivation and method sections",
      "title": "动机挑战需在方法章回扣",
      "description": "motivation 章列出的 N 个 challenge, method 章必须逐一回应 (verbatim 或 paraphrased), 命中率应 ≥80%.",
      "what_to_check": [                                 // 给 codex review 用的具体检查项
        "找 motivation 章 slide.关键文字 / 核心论断 中的 challenge 列表 (通常含 '挑战' '问题' '难点' 关键词)",
        "对每条 challenge, 在 method 章所有 slide 中找语义匹配 (verbatim 或 paraphrased)",
        "算命中率 = 命中数 / 总 challenge 数"
      ],
      "hit_carriers": [                                  // 本 batch 中命中的 deck
        {"deck_id": "...", "evidence": "motivation slide 5 列出 4 个 challenge (内存/算力/带宽/能效); method slide 12-23 回应 4/4"},
        ...
      ],
      "miss_carriers": [                                 // 本 batch 中违反的 deck
        {"deck_id": "...", "reason": "motivation 列了 3 challenge, method 只回应 1, 命中率 33%"}
      ],
      "estimated_hit_rate_in_batch": 0.71,
      "enforcement_level": "soft",                       // hard / soft / discard
      "rationale": "听众记不住 motivation 章的所有 challenge — method 章逐一回扣是本工作'兑现承诺'的核心机制, 缺失就让 motivation 沦为空谈",  // ← 为什么此规则存在
      "fix_hint": "遍历 motivation 章 challenge 列表, 对每条在 method 章追加一张 slide 或段落明确说'X 挑战由 Y 方法解决'",  // ← 违反时怎么改, 一句可执行
      "exceptions": [                                    // ← 什么情况不 enforce, 0-3 条
        "综述型 deck (motivation 列的是领域整体挑战, 本工作只覆盖一部分是正常的)",
        "多工作并列 deck (每个工作各回应一部分, 整章合计需覆盖 80%+)"
      ]
    },
    ... (本 batch 10-20 条 rule, 覆盖 8 大类)
  ],
  "extraction_notes": "本 batch N decks, rules by category: callback=3, suspense=2, ...",
  "coverage": {
    "rules_count": 14,
    "by_category": {
      "callback": 3, "suspense_reveal": 2, "chapter_transitions": 3,
      "repetition_emphasis": 2, "comparison_evidence": 2,
      "anchor_trajectory": 1, "structural_promise": 1, "pacing": 0
    }
  }
}
```

---

## Field semantics

- **`id`**: snake_case, 描述性. 命名:
  - `<feature>_<expected_behavior>` (e.g. `motivation_challenges_callback_in_method`, `chapter_outro_hook_required`, `main_thesis_repeat_count`)
- **`category`**: 严格 8 类:
  - `callback` (回扣呼应)
  - `suspense_reveal` (悬念揭示)
  - `chapter_transitions` (承上启下)
  - `repetition_emphasis` (重复强调)
  - `comparison_evidence` (比较证据)
  - `anchor_trajectory` (anchor 轨迹)
  - `structural_promise` (结构承诺)
  - `pacing` (节奏控制)
- **`applicable_when`**: 该 rule 何时适用 (e.g. "any deck with motivation+method sections", "decks ≥40 pages")
- **`what_to_check`**: ≥1 条具体检查项, **必须可被 codex review 程序化执行**. 每条描述"看哪个字段 + 找什么"
- **`hit_carriers`**: 本 batch 中命中此 rule 的 ≤5 个 deck. 每个含 deck_id + ≤100 字 evidence
- **`miss_carriers`**: 本 batch 中违反此 rule 的 ≤2 个 deck (反例). 没有反例时空数组
- **`estimated_hit_rate_in_batch`**: 0.0-1.0
- **`enforcement_level`**: hard / soft / discard
- **`rationale`**: ≤60 字, 该 rule **为什么存在** (说服学/认知/信息传递等 first principles). 下游遇到边界场景需据此判豁免. 不写"因为大家都这样"
- **`fix_hint`**: ≤40 字, 违反时**该怎么改**, 一句可执行动作, 具体到 slide/字段/章节. 不写"改进叙事" 空话
- **`exceptions`**: 0-3 条**明确豁免条件**, 每条 ≤30 字 what-not-when. 没有例外时空数组

---

## Process

### Step 1: per-deck 通读
对本 batch 每 deck 通读 slides_in_order, 识别:
- 主 anchor / 主 thesis
- motivation 章列的 challenges (如果有)
- framework 图 (如果有)
- claim / quantitative number 在 deck 中的分布

### Step 2: 类别遍历
对 8 大类, 每类问"本 batch 哪些 deck 命中此类的典型 rule, 哪些违反"。预期每类出 1-3 条 rule.

### Step 3: 跨 batch dedup
读 `previous_batches_rules`:
- 80%+ 重合 → 用 previous id
- 否则 → 新 id

### Step 4: 算 hit_carriers / miss_carriers / estimated_hit_rate
对每 rule 列出本 batch 命中/违反 deck 的具体证据.

---

## Hard rules

- **rules ≥5 必须**: 任何 batch 至少抽出 5 条 rule, 覆盖至少 4 个 category
- **id 唯一**: 同 batch 内不重复
- **category 严格 8 值之一**: 不创新 category
- **what_to_check 必须可机器执行**: 描述具体字段 (slide.核心论断 / slide.关键文字 等) + 关键词. 不写主观评价
- **hit_carriers + miss_carriers 必须真实 deck_id 引用**: 从 input 抄, 不虚构
- **estimated_hit_rate_in_batch 必填**: 0.0-1.0
- **enforcement_level 跟 hit_rate 一致**: ≥0.95 → hard, 0.7-0.95 → soft, <0.7 → discard (不该 emit)
- **rationale 必填**: ≤60 字, 说明**为什么** — 用说服学 / 认知 / 信息传递 first principles, 不写"大家都这样"
- **fix_hint 必填**: ≤40 字, 一句**可执行动作**, 具体到 slide/字段/章节. 不写"改进"这种空话
- **exceptions 可空 (给 `[]`)**: 只写**真实存在**的豁免条件, 不硬编虚构例外
- **跨 batch dedup 必做**
- **不要**: 把统计型 rule 当 narrative_flow (e.g. "title 字数 ≤14 字" 不该出现 — 是 Python 的事)
- **不要**: 重复 visual_authoring skill 的内容 (e.g. "title 用名词短句" 不该在这)
- **不要**: 列 conditional-on-pattern rule (那是 logic 库的)

---

## 经典误报警告

- 不要为单个 deck 的特殊性硬造 rule (e.g. "deck X 在 slide 5 用了 framework 图 → 所有 deck 都该这样")
- 不要把 chapter 顺序当 narrative_flow rule (chapter sequence invariant 是 Python rule_stats 的事)
- 不要凭"我觉得 ppt 应该这样写"出 rule, 必须有 hit_carriers 实证
- estimated_hit_rate_in_batch <0.5 的 rule 不要 emit (太弱不该 universal)

---

## Output format

- Strict JSON only, no markdown fences
- 顶层 `batch_index / rules / extraction_notes / coverage`
- rules[] 按 category 排序 (callback 先, pacing 后), 同 category 内按 enforcement_level 排序
- 单 batch 输出预期 40-80 KB
