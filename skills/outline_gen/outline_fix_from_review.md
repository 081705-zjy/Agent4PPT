# OUTLINE Fix-from-Review — Surgical Patcher for Codex & Human Issues (v2.0)

## Purpose

接 **统一 issues 列表** (来源可为 codex 或 human) + 当前 `outline.json` + **已选叙事模板与
节奏模板的完整 body** + hard rules summary + page-specific rules summary,
输出 **surgical 修正版** outline.json (schema 不变, 只动 flagged 字段)。

**这不是 generation, 不是 review** — 只做手术式修复, 让下一轮 codex review 能 ok, 且不违反
已选模板的骨架约束。

**双 loop 共用本 skill** (mirror IDEA):
- **小 loop (codex)**: `outline_review.md` → issues (source=codex) → 本 skill 修 → codex 再审
- **大 loop (human)**: 自然语言 → `outline_revision.md` (mode=structure_only) → issues (source=human) → 本 skill 修 → codex 兜底 → 回人类 gate

---

## 与其他 OUTLINE skill 的边界

| skill | 谁触发 | 输入 | 风格 |
|---|---|---|---|
| `outline_chapter_stub.md` | driver Stage 1a | per chapter context | 生成 stub (free) |
| `outline_slide_detail.md` | driver Stage 1c | stub + slide briefs | 生成 detail (free) |
| `outline_skeleton_review.md` | codex Stage 1b | full stubs | 只**找**骨架 issues |
| `outline_review.md` | codex Stage 2 | full outline.json | 只**找** issues |
| `outline_revision.md` (structure_only) | driver | user 自然语言 | 翻译→定位, 输出 issues, 不改 |
| **`outline_fix_from_review.md`** (本) | driver | 统一 issues (codex+human) + 模板 body | **手术式修复**, 改 flagged 字段 |

---

## Inputs

```json
{
  "prior_outline": {
    "schema_version": "1.0",
    "slides": [...],
    "chapter_to_slide_map": {...},
    "rhythm_adherence_log": [...],
    "narrative_constraints_realization": {...},
    "provenance": {...},
    "user_concern_history": [...],
    "fix_round": <int, 上一轮 fix_round, 无则 0>
  },
  "issues": [
    {
      "source": "codex" | "human",
      "category": "rule_compliance | narrative_coherence | source_matching | slide_content | structure | user_concern_regression | other",
      "severity": "critical | high | medium | low",
      "location": "slides[12].source_resource_ids[0].slide_id  /  chapter_to_slide_map.4  /  complete",
      "evidence": "<原文摘录 或 human 引用, ≤120 字>",
      "explanation": "<为什么这是问题, ≤120 字>",
      "suggested_fix": "<具体改什么, 改成什么, ≤150 字>",
      "human_note": "<仅 source=human 时有, human 原自然语言, 保留追溯>"
    }
  ],
  "idea_analysis": { /* idea-analysis.json v4.0 — 上游契约, 不可改 */ },
  "logic_story_hard_rules_summary": [...],
  "page_specific_rules_summary": [...],
  "selected_narrative_pattern_body": { /* idea 阶段选定的 primary_pattern_id 完整 JSON body */ },
  "rhythm_pattern_bodies": {
    "<rhythm_pattern_id_1>": { /* 完整 JSON body */ },
    "<rhythm_pattern_id_2>": { /* ... */ }
  }
}
```

**关键说明**:
- `prior_outline.user_concern_history` 是 user 历轮 + IDEA 留下的诉求记录, 每条
  `must_not_regress=true` 都是 **hard constraint**, surgical fix 时绝对不能违反 (见 #8)。
- `selected_narrative_pattern_body` / `rhythm_pattern_bodies` 是**必看**的骨架约束来源 —
  修 slide 结构 / 加删 slide / 改章内 slide 数时必须先对照模板 body 里的骨架序列, 否则会破坏
  已选叙事骨架 (详见 #10)。

---

## Task

按以下原则修 outline.json:

### 1. 处理优先级

**severity 优先级**:
- `critical` → 必修
- `high` → 必修
- `medium` → 可跳过 (在 `referenced_review_issues[].status` 标 "skipped (low priority)")
- `low` → 跳过

**source 优先级** (同 severity 时):
- `human` > `codex` — human issue 反映真实使用者判断, 优先响应
- 特别: **source=human 若未标 severity, 视同 high**
- 若 codex issue 和 human issue **冲突** (e.g. codex 说"合并 slide 12/13", human 说"12/13 分开更好"),
  **保留 human 意图, skip codex issue** 并在 referenced_review_issues 说明冲突

同 location 多 issues 合并处理 (一次 patch 解多 issues)。

### 2. 字段精准定位

`issue.location` 用 JSON path 风格定位:
- `slides[12]` — 第 12 张 slide (0-based per JSON path 约定)
- `slides[12].source_resource_ids[0]` — 第 12 张 slide 的第 1 个 source
- `chapter_to_slide_map.4` — chapter_index=4 的 slide 范围
- `provenance.rule_relaxed_with_reason` — 整个数组
- `rhythm_adherence_log[3]` — 第 4 章的 rhythm adherence 记录

**严禁** 修改 location 未覆盖的字段。

### 3. 加 slide / 删 slide / 改 slide_index 的连锁更新

如 issue 要求**加 1 slide** (e.g. "ch4 缺 rhythm node 'paper_1_intro' 对应 slide"):

- 在 slides 数组合适位置 insert 1 slide object
- **全部后续 slide_index 自动 +1** (绝对 slide_index)
- chapter_to_slide_map 同步更新 (该 chapter 的 slide_index range 扩展, 后续 chapter 整体后移)
- rhythm_adherence_log 同步 (该 chapter 的 page_to_rhythm_node_map 加 1 项, slide_count +1)
- narrative_constraints_realization 同步 (若该 slide 落在 thesis_callback/framework_repeat
  指定章, 相关字段更新)

如**删 slide** / **改 slide_index**: 同样连锁更新。

### 4. preserve untouched 字段必须 byte-identical

未被 issue.location 覆盖的字段必须**逐字保留**:
- 各 slide 的 `archetype` 数组 (除非 issue 直接 flag)
- 各 slide 的 `source_resource_ids` 内每条 (deck_id/slide_id/rank_score/match_reasons)
- `identity.*` (除非 codex 提示 schema_completeness)
- `provenance.referenced_rule_ids_followed`
- `user_concern_history` 全部条目 (不删/不改, 仅追加)

**anti-rule**: 不要 reformat 整 JSON, 不要 paraphrase 未 flag 的 target_claim, 不要补
provenance 没要求加的字段。

### 5. rule_compliance issue 的修复参考 hard_rules_summary

issue.evidence 引用了某 rule_id (e.g. `claim_is_judgment_sentence_with_predicate`), 在
hard_rules_summary 或 page_specific_rules_summary 里查该 rule 的 summary, 按 rule 语义修复。

常见 rule 修法对照:

| rule_id | 修法 |
|---|---|
| `claim_is_judgment_sentence_with_predicate` | 改写 target_claim 加 predicate |
| `cover_layout_centered_title_with_author_signature` | cover slide archetype 加该项 |
| `ending_signature_includes_date_email_institution_triple` | closing slide archetype 加该项 + delivery_hint 提示 |
| `framework_overview_page_repeated_as_chapter_transition` | method 章首 slide archetype 加 framework_overview |
| `chapter_role_correctness (cover at slide_1)` | slides 重新排序使 cover=slide_1 |
| `source_carrier_resource_kind_miscoded` | 调整 kind 或重选 source_resource_ids |

### 6. archetype 改动从 page_specific 枚举内选

修 archetype 时必须从 input.page_specific_rules_summary 的 id 集合内选, 不允许凭空造。

### 6.5. **no_supporting_material issue 处理 (v30 fix G — HARD, 库驱动原则)**

**触发**: `issues[].category == "no_supporting_material"` (driver 从 OUTLINE review/final gate 注入).

**核心原则**: 库驱动生成 —— outline **必须**与库对齐, **不允许**保留无材料 placeholder,
必须调整 outline 到"库能支撑的形态".

**3 选 1 决策树** (按优先级):

**(a) 删除 slide (首选)** — 若满足:
- 该 slide 的 target_role ∈ {motivation, discussion, references, transition} (非关键结构页) 且
- 章内 rhythm 骨架砍掉这页仍能对齐 (rhythm_pattern_bodies 里 abstract_node_sequence
  少 1 node 不破)
- 章总页数 ≥ IDEA expected_pages_indicative × 0.7 (砍完不至于太薄)

动作:
- 从 `slides` 数组删除该 slide
- 全部后续 slide_index 顺移 -1
- 更新 `chapter_to_slide_map` 该 chapter range
- 从 `narrative_constraints_realization` 移除对该 slide_index 的引用

**(b) 改 target_claim 到库能支撑方向 (次选)** — 若删了会破坏叙事:
- 用 input.chapter_wide_cascade_candidates 或 library evidence keywords 反查
  该 chapter 里库实际有的具体内容方向
- 改 target_title / target_claim / key_points → 挑一个库里有 slide 承载的方向
- 重新挑 source_resource_ids (从 cascade candidates 里挑 _claim_alignment 最高的)
- 若成功: kind 改回 `carrier_bound`, gap_status = `ok`, source_resource_ids 非空
- 记 action_taken: "改 claim 从 X (库无) 到 Y (库有), 挑 source Z"

**(c) 章级重拆 (兜底)** — 若整章 ≥50% slide 都 no_material:
- 触发 `outline_decomposition` 层修复: chapter_decomposition.axis 需换到库能支撑的方向
- 引用 input.chapter_wide_cascade_candidates 里该章实际能匹配的 top decks/sections
- 调整 chapter.sublines 和整章 slide 数以适配库容量
- rationale 里说明"因原 axis 库无支撑, 换到 X axis"

**禁止**:
- ❌ 保留 no_material slide 不动 (违背库驱动)
- ❌ 强塞一个 semantic 不对的 source 假装匹配 (回到用户报的 v23 fallback 问题)
- ❌ 加 gap_research_hint 让 SLIDE_REWRITE 处理 (违背 no-fabrication)

**输出**: 每个 no_material_page 必须在 `referenced_review_issues` 里标 action_taken:
- "deleted" (走 a)
- "claim_rewritten to '<新方向>' + source rebind to <resource_id>" (走 b)
- "escalated to chapter_decomposition_redo" (走 c)

### 6.6. v34 structural/source-binding issues 处理 (HARD)

以下 issue 是 outline 阶段必须解决的结构问题, 不能只写进 gapcard:

| category | 必须动作 |
|---|---|
| `weak_or_fallback_source_binding` / `matching_fallback_not_final_outline_source` | 优先从 alternates/chapter_wide_cascade_candidates 改绑强匹配 source; 若无强匹配, 把 target_title/target_claim/key_points 改到当前 source 真实承载的方向; 仍不成立则删除该 slide 或标记 chapter_decomposition_redo |
| `duplicate_source_within_chapter` / `distinct_neighbor_slides_require_distinct_sources` | 保留最贴合的一页; 其他重复页改绑不同 source. 不允许两张不同目标页继续复用同一 source, 除非补 `same_source_intent.allowed=true` 且是 agenda/framework 模板复用 |
| `structural_page_bound_to_content_source` / `structural_pages_require_structural_sources` | 改绑 agenda/framework/closing/references 类结构 source; 若找不到结构 source, 删除/合并该结构页或把 target_role 改成普通内容页, 不能用具体方法页伪装结构页 |
| `method_chapter_structural_rhythm_inconsistent` | 调整相关 chapter skeleton: 补同构 chapter_divider/framework_recap, 或统一删除/合并全组结构锚. 必须同步 slide_index/chapter_to_slide_map |
| `parallel_work_blocks_asymmetric` / `parallel_representative_work_blocks_same_template` | 统一同章代表工作 block 模板. 可以补缺页、删多余页或同步压缩, 但不能保留一个工作完整四段、另一个缺 method/result |

**优先级**:
1. 改绑真实 source, 不改叙事。
2. 若无真实 source, 改 target_claim 到 source 真实语义, 但不得偏离 IDEA 章 intent 太远。
3. 若仍不成立, 删除/合并 slide 或回滚 chapter_decomposition。

**禁止**:
- ❌ 把这些 issue 标为 "gapcard will fix" 或 "downstream rewrite".
- ❌ 保留 `matching_fallback` / `weak_*` 作为最终 outline 状态。
- ❌ 为了避免重排而让不同目标页继续复用同一 source。
- ❌ 结构页继续绑定普通 method/result/论文封面源页。

### 7. 记录修改痕迹

输出新字段 `referenced_review_issues` (同时涵盖 codex + human):

```json
{
  ...原 outline.json 字段 (修改过的)...,
  "fix_round": <current_fix_round + 1, 不存在时 = 1>,
  "referenced_review_issues": [
    {
      "source": "codex" | "human",
      "category": "rule_compliance",
      "severity": "high",
      "location": "slides[12].target_claim",
      "rule_id_or_summary": "claim_is_judgment_sentence_with_predicate",
      "human_note": "<若 source=human, 原自然语言保留>",
      "action_taken": "<≤80 字, 具体改了什么字段, 加/删/调了哪个值>",
      "status": "applied | skipped (low priority) | skipped (ambiguous fix) | skipped (would violate template skeleton) | skipped (conflicts with human intent) | skipped (would regress user concern)"
    }
  ]
}
```

### 8. **user_concern_history regression guard (HARD constraint)**

prior_outline.user_concern_history 中每条 `must_not_regress=true` 的 concern 是**绝对不可违反**:

- 在 fix 任何 issue 之前, 先扫一遍 user_concern_history, 列出所有 `must_not_regress=true` 的
  (concern, resolved_at_field, applied_action) 三元组
- 修任何 issue 时, 检查所选改法是否会触及上述 resolved_at_field
- 若某条 suggested_fix 的修改会**违反 user concern** (e.g. user 之前要求 ch7 单轴=部署延展,
  codex 现在建议把"集群调度"加回 ch7 — 这恰好回到 ch5 系统层方法重叠的状态) → **拒绝该 issue**
  (仅当 source=codex; source=human 允许覆盖旧 concern, 见下方 human append 规则):
  - 标 status="skipped (would regress user concern: <concern 引用>)"
  - 改用替代方案 (e.g. 不在 ch7 加, 改在 ch5 加)
  - 若没有替代方案, 报告 in action_taken: "无解, codex 建议与 user concern 冲突, 保留 user concern, 跳过此 codex issue"

**human issue 覆盖旧 concern 的处理**:
- source=human 的 issue 若与旧 user_concern_history 冲突, **优先响应新的 human 意图** (人有权
  更新自己的想法), 在旧对应 concern 上标 `superseded_at_fix_round: <本轮>` 且 `must_not_regress: false`
- 同时 append 一条新 user_concern_history 记录 (stage="OUTLINE") 反映本轮 human 意图

**user_concern_history 必须保留** (复制到输出, 不要删/合并); 仅在上述 supersede 场景下修改
`must_not_regress` 字段。

### 9. 跨阶段守护: IDEA 阶段 concern 也算

user_concern_history 含 stage=IDEA 的 concern (从 IDEA 阶段继承的, 例如 "ch7 必须单轴=部署延展").
OUTLINE fix 时这些也必须不 regression — 即 OUTLINE 的 ch7 对应 slides 集合应当全部围绕该单轴。

### 10. **selected_narrative_pattern_body 骨架约束 (HARD constraint)**

selected_narrative_pattern_body 是 IDEA_ANALYSIS 阶段选定的 primary_pattern_id 对应模板全文。
修 slide 结构 / 加删 slide / 改章内 slide 分配时必须:

- 对照模板 body 中的**骨架序列描述** (通常在 `abstract_node_sequence` / `carriers` 字段),
  确认改后 slides 序列仍能对齐模板骨架
- 若某个 issue 的 suggested_fix 会破坏骨架 (e.g. 模板要求 method 章按 "framework_recap →
  paper_intro → paper_unfold × N → efficiency_summary" 展开, issue 说"删掉 framework_recap",
  破坏骨架) → **skip 该 issue** 或改用不破坏骨架的替代方案
- rhythm_pattern_bodies 是每章 rhythm 骨架的完整描述, 修某章内 slides 时对照对应 rhythm body
  的 abstract_node_sequence 保证不违反该章节奏约束

**破坏骨架** 是硬红线, 优先级高于 codex issue, 次于 human 明确要求破坏 (human 意图 > 骨架 > codex).

---

## Output Schema

完整 `outline.json` v1.0 (所有原字段保留, schema_version 不变, 加 `fix_round` +
`referenced_review_issues`)

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

---

## Hard Rules

1. **Surgical**: 只动 issue.location 字段 + 因连锁更新必须改的派生字段; 其他字段 byte-identical 保留
2. **优先级**: (severity) critical > high; medium/low 可跳过; (source) human > codex 于冲突时
3. **加/删 slide** 必须重编 slide_index 全 chain, 同步 chapter_to_slide_map /
   rhythm_adherence_log / narrative_constraints_realization
4. **不重写** archetype 数组 / source_resource_ids 内每条 (除非 issue 直接 flag)
5. **不补充** provenance.referenced_rule_ids_followed 等审计字段 (除非 issue 要求)
6. **不 paraphrase** 未 flag 的 target_claim / key_points 字段值
7. **schema_version 不变** ("1.0"); generated_at / source 字段不改
8. **referenced_review_issues 必须涵盖所有 input critical/high issues** (每条标 applied/skipped 状态)
9. **user_concern_history 累加保留**: 输入原封保留 (含 IDEA stage); source=human issue 若与旧
   concern 冲突, 在旧对应记录标 superseded 而不是删; 本轮 applied 的 human issue append 新
   concern 记录 (stage="OUTLINE", must_not_regress=true)
10. **archetype 必须从 input.page_specific_rules_summary 枚举选**, 不凭空造
11. **selected_narrative_pattern_body 骨架不破坏** (除非 human 明确要求)
12. Output **strict JSON only**

---

## Anti-rules (常见错误, 不要做)

- ❌ "趁此机会优化一下 narrative_constraints_realization 文字" — 不在 issue location 里, 不要动
- ❌ "把 source_resource_ids 重新排序优化" — driver/Stage 1c 给的不动
- ❌ "target_claim 重新精炼一遍" — 未 flag 即保留原文
- ❌ "重写 chapter_to_slide_map 整段" — 只改受影响的 chapter range
- ❌ "加 fix_round 但漏掉 referenced_review_issues" — 两个必须配对
- ❌ "把 issue.suggested_fix 原文复制到字段" — suggested_fix 是建议, 你要按建议改 schema
  字段, 不要直接拷文本
- ❌ "human issue 严重程度低就跳过" — human 无 severity 视同 high, 除非 human 显式标 low
- ❌ "codex 说要删这 slide, human 说要保留 → 删了" — 冲突时保 human 意图, skip codex
- ❌ "为了满足 codex issue, 把 slide 加删改到破坏 selected_narrative_pattern_body 骨架" — 骨架优先
- ❌ "user_concern_history 中改 must_not_regress=false 让 codex 通过" — 严禁, supersede 必须由
  source=human 的 issue 触发, 不是 fix skill 自行决定
