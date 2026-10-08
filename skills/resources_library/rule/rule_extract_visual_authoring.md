# Rule Extract — Visual & Authoring

你正在从**整个 PPT 语料库**里**抽取 universal 视觉与写作规则**。这些规则**不依赖具体主题**, 描述
"任何 ppt 这种 role 的 slide 通常长什么样" + "title/claim 的写作风格"。

跟 logic 库的区别:
- logic 库的 pattern 是 conditional on chapter_role / deck_type (e.g. method 章节奏)
- 本 skill 出的 rules 是 universal — 任何 ppt 都该 follow

跟 rule 库的统计部分区别:
- 统计型 rule (title 字数 p95 / role 位置一致性) 由 Python rule_stats.py 直接算
- 本 skill 出的是**语义型**: 视觉模板的构图、关键文字的写作风格 — Python 算不出来

---

## Inputs (per batch)

```json
{
  "batch_index": 0,                                    // 0..N-1 (总 deck 分成 N batch)
  "decks_in_this_batch": [
    {
      "deck标识": "tpl.topic.论文分享.6b133f9d6028",
      "标题": "...",
      "报告类型": "paper_share",
      "适用场景": "...",
      // 该 deck 全部 slides — 按 role 分桶供 Claude 看, 不保 deck 顺序
      "slides_by_role": {
        "cover_candidate": [
          {"slide_index": 1, "deck_id": "...", "标题": "...", "核心论断": "",
           "关键文字": [...], "视觉骨架": [...], "section_role": "cover"},
          ...
        ],
        "toc_candidate": [...],
        "chapter_candidate": [...],
        "ending_candidate": [...],
        "content_candidate": [...]
      }
    },
    ... × N (本 batch 的所有 deck, N = decks_in_this_batch 长度)
  ],
  "previous_batches_rules": [                          // ← 跨 batch dedup
    {"id": "cover_layout_centered_title_with_signature",
     "category": "visual",
     "description": "...",
     "applicable_role": ["cover"]},
    ...
  ]
}
```

**Driver per-batch 调度**:
- 整个语料库分 N batch, 每 batch batch_size 个 deck (driver 决定, 典型 4)
- 单次输入 ~120-180 KB (只含 slide 字段精选, 不含 section.json 不含视觉骨架 raw)
- batch 0: previous_batches_rules = []
- batch 1+: 前面 batch 已输出 rules 元数据

---

## Output: `visual_authoring_rules_batch_<N>.json`

```json
{
  "batch_index": 0,
  "rules": [
    {
      "id": "cover_layout_centered_title_with_signature",  // ← snake_case 唯一 id
      "category": "visual",                                // "visual" | "authoring"
      "applicable_role": ["cover_candidate"],              // 适用哪些 slide_role
      "title": "封面布局·居中主标题+作者署名",                  // 短中文标题
      "description": "封面页布局: 大字主标题居中, 副标题或方法名次行, 作者署名+单位 居底/居右, 可含 logo. 不含 body 文字.",
      "evidence_signals": [                                // ← 在 slide.视觉骨架/关键文字 中能识别的信号
        "视觉骨架 含 '主标题' / '居中' / '大字标题'",
        "关键文字 含 作者名 + 单位 + 日期",
        "无 '正文段落' / 'bullet 列表' 元素"
      ],
      "hit_carriers": [                                    // ≤ 5 命中的 slide 样本
        {"deck_id": "tpl.topic.论文分享.6b133f9d6028", "slide_index": 1,
         "评价": "标准 cover 布局: 'SpAct-NDP：稀疏激活近数据计算' + 作者 + 单位"},
        {"deck_id": "tpl.topic.对外汇报展示.戴国浩-高效大模型推理", "slide_index": 1,
         "评价": "同样布局"},
        ...
      ],
      "miss_carriers": [                                   // ≤ 2 不命中样本 (反例)
        {"deck_id": "tpl.basic.basic.dai-template", "slide_index": 1,
         "原因": "空白模板, 仅含'封面占位'文字, 无作者无主题"}
      ],
      "estimated_hit_rate_in_batch": 0.85,                 // 本 batch 7 deck 该 role 命中率
      "enforcement_level": "soft",                          // hard (>0.95) | soft (0.7-0.95) | discard (<0.7)
      "rationale": "居中大字标题+作者署名是通用的身份识别版式,让听众在开场瞬间锁定 deck 主题与讲者身份, 避免其他内容元素抢焦点",  // ← 为什么此规则存在, 下游据此判断边界豁免
      "fix_hint": "把 cover slide 的主标题居中放大, 作者/机构信息放置于底部或右下, 移除或压缩其他非身份识别元素",  // ← 违反时怎么改, 一句可执行
      "exceptions": [                                        // ← 什么情况下不 enforce, 0-3 条
        "空白模板 / 占位版式 (无实际身份可展示)",
        "品牌宣传型 deck (讲者身份让位于品牌 logo/slogan)"
      ]
    },
    {
      "id": "title_uses_noun_phrase_not_full_sentence",
      "category": "authoring",
      "applicable_role": ["all"],                          // 所有 slide
      "title": "标题用名词短句, 不用完整动宾句",
      "description": "slide.标题 倾向于名词短句 (≤14字) 或主题词, 不用 '介绍 XX' / '本节讲 XX' 这类动宾句, 也不把 claim 当 title.",
      "evidence_signals": [
        "title 不以 '介绍' '本节' '我们将' 等开头",
        "title 不含完整谓语动词 + 宾语结构",
        "title 多为 'X·Y' 或 'X 与 Y' 类名词短句"
      ],
      "hit_carriers": [...],
      "miss_carriers": [...],
      "estimated_hit_rate_in_batch": 0.92,
      "enforcement_level": "soft",
      "rationale": "名词短句 title 让听众一眼抓到本页主题, 完整动宾句 title 会让 title 与 claim 语义重叠 / title 变成'讲什么'描述而非'定位'",
      "fix_hint": "把 title 里的动词 + 介词短语去掉, 改为 '<X> · <Y>' 或 '<X> 与 <Y>' 名词短句, claim 归到本页正文",
      "exceptions": [
        "章节封面页 / 议程页 (title 承担'即将展开' 提示时可用 '介绍 X' 类)"
      ]
    },
    ... (本 batch 8-15 条 rule)
  ],
  "extraction_notes": "本 batch N decks, visual: M rules, authoring: K rules",
  "coverage": {
    "rules_count": 12,
    "by_category": {"visual": 7, "authoring": 5}
  }
}
```

---

## Field semantics

- **`id`**: snake_case, 描述性. 命名:
  - visual: `<role>_layout_<distinguishing_feature>` (e.g. `cover_layout_centered_title_with_signature`, `section_divider_layout_big_chapter_number`)
  - authoring: `<field>_<rule>` (e.g. `title_uses_noun_phrase_not_full_sentence`, `claim_must_be_judgment_sentence`)
- **`category`**: 严格 2 值 — `visual` | `authoring`. 视觉 = 布局/构图; 写作 = 文字风格
- **`applicable_role`**: 适用 slide_role 集合. 可用 `["all"]` 表示所有 slide
- **`description`**: ≤120 字, 描述 rule 的内容
- **`evidence_signals`**: 在 slide.json 中能识别此 rule 是否命中的具体信号 (字段名 + 关键词). **必须可机器判断**, 不要写 "大家都这样写" 这种主观话
- **`hit_carriers`**: 本 batch 中命中此 rule 的 ≤5 个 slide 引用. 每个含 deck_id + slide_index + ≤80 字评价
- **`miss_carriers`**: 本 batch 中违反此 rule 的 ≤2 个 slide 引用 (反例) — **没有反例时给空数组**, 不要硬编反例
- **`estimated_hit_rate_in_batch`**: 0.0-1.0, 估算本 batch 命中率. driver 跨 batch 重算最终 hit_rate
- **`enforcement_level`**: `hard` (≥0.95 命中) | `soft` (0.7-0.95) | `discard` (<0.7, 不该当 rule)
- **`rationale`**: ≤60 字, 该 rule **为什么存在** (说服/认知/视觉焦点等原理). 下游遇到边界场景 (双栏封面 / 品牌型 deck) 需据此判断是否豁免. 不写"因为大家都这样" — 要写 first principles
- **`fix_hint`**: ≤40 字, 违反时**该怎么改**, 一句可执行动作. 具体到"改 X 字段 / 移到 X 位置 / 加 X 元素". 不写"改进版式"这种空话
- **`exceptions`**: 0-3 条**明确豁免条件**. 每条 ≤30 字, 描述 what-not-when. 没有例外时给空数组, 不硬编例外

---

## Process

### Step 1: 按 slide_role 索引输入
本 batch 7 deck 共 ~200 slides, 按 `页面角色` (slide_role) 分桶:
- cover_candidate 桶
- toc_candidate 桶
- chapter_candidate 桶
- ending_candidate 桶
- content_candidate 桶 (最大)

### Step 2: 对每桶找 visual common patterns
看 slide.视觉骨架 / 关键文字 字段, 找该桶 slide 的**共同视觉特征**:
- 大字标题位置 (居中/居左/居右)
- 是否含作者署名
- 是否含 logo
- 是否含 bullet 列表
- 图文比

每桶出 0-3 条 visual rule (描述该 role 的标准布局).

### Step 3: 跨桶找 authoring rules
看所有 slide.标题 + 核心论断 + 关键文字, 找**全局写作风格规律**:
- title 名词短句 vs 完整动宾句
- claim 判断句 vs 描述句
- 数字/百分比在 claim 中的频率
- 缩写首次使用是否带定义
- bullet 用动词起句 vs 名词起句

预期 4-8 条 authoring rule.

### Step 4: 跨 batch dedup
读 `previous_batches_rules`:
- 80%+ 重合 → 用 previous id (carriers 累加由 driver)
- 否则 → 新 id

### Step 5: batch 内 dedup
产出前自检, 不同 rule 描述近义合并.

---

## Hard rules

- **rules ≥1 必须**: 任何 batch 至少抽出 5 条 rule
- **id 唯一**: 同 batch 内不能重复
- **category 严格 2 值**: visual / authoring
- **evidence_signals 必须可机器判断**: 描述具体字段 + 关键词, 不写主观评价
- **hit_carriers + miss_carriers 必须从 input 抄**: deck_id / slide_index 真实, 评价 ≤80 字
- **estimated_hit_rate_in_batch 必填**: 0.0-1.0 估值
- **rationale 必填**: ≤60 字, 说明**为什么** — 不写"大家都这样"; 写视觉/认知/说服学 first principles
- **fix_hint 必填**: ≤40 字, 一句**可执行动作**, 具体到字段/位置/元素. 不写"改进"这种空话
- **exceptions 可空 (给 `[]`)**: 只写**真实存在**的豁免条件, 别硬编虚构例外
- **跨 batch dedup 必做**
- **不要**: 列 statistical rule (那是 Python rule_stats.py 的工作). e.g. "title 平均 8.2 字" 不该出现 — 但 "title 用名词短句不用动宾句" 可以

---

## 经典误报警告 (不要做)

- 不要写"主观评价" rule (e.g. "封面应该美观") — 评价不可机器判断
- 不要把统计数据当 rule (e.g. "title 平均 8.2 字") — 那是 Python 的事
- 不要把 chapter_role 顺序当 rule (e.g. "motivation 在 method 前") — 那也是 rule_stats.py 的统计
- 不要重复 logic 库的内容 (e.g. "method 章用 4 paper 平行") — logic 库覆盖 conditional 规则

---

## Output format

- Strict JSON only, no markdown fences, no prose preamble
- 顶层 `batch_index / rules / extraction_notes / coverage`
- rules[] 按 enforcement_level desc (hard 先 / soft 后) + estimated_hit_rate_in_batch desc 排序
- 单 batch 输出预期 30-60 KB
