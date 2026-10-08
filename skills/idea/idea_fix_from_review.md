# IDEA Fix-from-Review — Surgical Patcher for Codex & Human Issues

## Purpose

接 **统一 issues 列表** (来源可为 codex 或 human) + 当前 `idea-analysis.json` + **已选叙事模板与
节奏模板的完整 body** + hard rules summary, 输出 **surgical 修正版** idea-analysis.json
(schema 不变, 只动 flagged 字段)。

**这不是 generation, 不是 review** — 只做手术式修复, 让下一轮 codex review 能 ok, 且不违反
已选模板的骨架约束。

**双 loop 共用本 skill**:
- **小 loop (codex)**: `idea_review.md` → issues (source=codex) → 本 skill 修 → codex 再审
- **大 loop (human)**: 自然语言 → `idea_revision.md` (mode=structure_only) → issues (source=human) → 本 skill 修 → codex 兜底 → 回人类 gate

---

## 与其他 skill 的边界

| skill | 谁触发 | 输入 | 风格 |
|---|---|---|---|
| `idea_analysis.md` | driver init | intake + patterns | **生成** (free, design narrative) |
| `idea_review.md` | codex (审查) | full idea-analysis.json | 只**找** issues, 不改 |
| `idea_revision.md` (structure_only) | driver | user 自然语言 | 翻译→定位, 输出 issues, 不改 |
| **`idea_fix_from_review.md`** (本) | driver | 统一 issues (codex+human) + 模板 body | **手术式修复**, 改 flagged 字段 |

---

## Inputs

```json
{
  "prior_idea_analysis": {
    "schema_version": "6.1",
    "identity": {...},
    "selected_narrative_arc": {...},
    "chapter_plan": [...],
    "narrative_constraints": {...},
    "reuse_strategy": {...},
    "provenance": {...},
    "user_concern_history": [...],
    "fix_round": <int, 上一轮 fix_round, 无则 0>,
    ...
  },
  "issues": [
    {
      "source": "codex" | "human",
      "category": "rule_compliance | narrative_coherence | user_concern_regression | structure | content | other",
      "severity": "critical | high | medium | low",
      "location": "chapter_plan[7].section_role  /  narrative_constraints.framework_anchor_repeat  /  complete",
      "evidence": "<原文摘录 或 human 引用, ≤120 字>",
      "explanation": "<为什么这是问题, ≤120 字>",
      "suggested_fix": "<具体改什么, 改成什么, ≤150 字>",
      "human_note": "<仅 source=human 时有, human 原自然语言, 保留追溯>"
    }
  ],
  "logic_story_hard_rules_summary": [
    {"id": "...", "category": "...", "hit_rate": 1.0, "summary": "..."}
  ],
  "selected_narrative_pattern_body": { /* primary_pattern_id 对应模板的完整 JSON body,
    含 abstract_node_sequence / applicable_summary / carriers / page_transitions_pattern
    / anti_patterns 等 — 这是骨架约束的权威来源 */ },
  "rhythm_pattern_bodies": {
    "<rhythm_pattern_id_1>": { /* 完整 JSON body, 同上结构 */ },
    "<rhythm_pattern_id_2>": { /* ... */ }
  }
}
```

**关键说明**:
- `prior_idea_analysis.user_concern_history` 是 user 历轮留下的诉求记录, 每条 `must_not_regress=true`
  的 concern 都是 **hard constraint**, surgical fix 时绝对不能违反 (详见 #7)。
- `selected_narrative_pattern_body` / `rhythm_pattern_bodies` 是**必看**的骨架约束来源 —
  修 `chapter_plan` 结构 / 章节名 / 章节 role 时必须先对照模板 body 里的"骨架序列"和"节奏约束",
  否则会破坏已选模板的骨架 (详见 #8)。

---

## Task

按以下原则修 idea-analysis.json:

### 0. ⚠️ 首要规则 — suggested_fix 是"给你的方向指令", 不是"要写进 field 的内容" (v29)

codex 给的 `suggested_fix` 常长这样:
> "改为『系统层跨算法-硬件联合设计方向』; 具体倍数由 OUTLINE 反查 source 后填入 slide.target_claim"

**这里只有『系统层跨算法-硬件联合设计方向』是新的字段值**。分号后半段 (`由 OUTLINE 反查...`)
是 codex 对你的说明, **绝对不能**当成 field 内容抄进去。

严禁在 `claims_to_make` / `purpose` / `chapter` / `core_message` 任何内容字段出现:
- `由\s*OUTLINE.*(填入|反查|决定)`
- `留给\s*OUTLINE / 下游`
- `slide\.target_claim`
- `具体.*(留给|由).*(OUTLINE|下游)`
- `参考 codex 建议`
- 任何形如"改为 X"的 meta 短语

**正确做法**: 从 suggested_fix 里**抠出新字段值本身** (通常在引号 / 冒号 / "改为" 之后),
只把这一部分写入 field; 舍弃 codex 的元指令说明。

**如果 suggested_fix 只有元指令(没给出具体新值)** → 你需要**自己按 hard rules 反推一个合适的
抽象值**, 而不是抄元指令。

### 1. 处理优先级

**severity 优先级**:
- `critical` → 必修
- `high` → 必修
- `medium` → 可跳过 (标 `status: "skipped (low priority)"`)
- `low` → 跳过

**source 优先级** (同 severity 时):
- `human` > `codex` — human issue 反映真实使用者判断, 优先响应
- 特别: **source=human 若未标 severity, 视同 high**
- 若 codex issue 和 human issue **冲突** (e.g. codex 说"合并 ch5/ch6", human 说"ch5/ch6 分开更好"),
  **保留 human 意图, skip codex issue** 并在 referenced_review_issues 说明冲突

同 location 多 issues 合并处理 (一次 patch 解多 issues)。

### 2. 字段精准定位

`issue.location` 用 JSON path 风格定位:
- `chapter_plan[7].section_role` — 第 7 章 (0-based) section_role
- `chapter_plan[3].claims_to_make[2]` — 第 3 章第 2 条 claim
- `narrative_constraints.framework_anchor_repeat` — 整个对象
- `selected_narrative_arc.primary_pattern_id` — 单字符串字段
- `chapter_plan[i].section_rhythm_pattern_id` — v4.0 单字符串 rhythm 选择
- `chapter_plan[i].material_section_hints` — v6.1 section-level material handoff
- `reuse_strategy.target_reuse_rate` — float 字段
- `complete` — 全局意见, 需自己判断落到具体字段 (常见于 human 提"整体太学术"等模糊反馈)

**严禁** 修改 location 未覆盖的字段。

### 3. 加章 / 删章 / 改章序的连锁更新

如 issue 要求**加 1 章** (e.g. "trend_chapter_follows_method_chapters 违反, 缺 discussion/outlook 章"):

- 在 chapter_plan 合适位置 insert 1 个 chapter object
- **全部后续 chapter section_index 自动 +1**
- 同步更新:
  - `narrative_constraints.thesis_callback.raise_at_chapter / callback_at_chapters` 若引用变化的 index
  - `narrative_constraints.framework_anchor_repeat.repeat_at_chapters`
  - `narrative_constraints.anchor_term_trajectory[].must_appear_in_chapters`
  - `narrative_constraints.cross_section_hooks[].from / .to`
- 新章必须含 v6.1 必填字段:
  - `section_rhythm_pattern_id` (从对应 role 的 rhythm_patterns_per_role top-3 中选 1;
    若 rhythm_pattern_bodies 里已有该 role 的可选模板, 优先复用其中之一)
  - `section_rhythm_summary` (≤80 字)
  - `section_rhythm_source_count`
  - `material_section_hints` (只填 deck/section 级字段, 不得填 slide_id 或 source_resource_ids)
- 新章 `claims_to_make` 要承接前章 claims_to_setup_for_later, 写后续 cross_section_hooks
- **加/删章后必须重新对照 selected_narrative_pattern_body 骨架序列检验**: 章序仍能对齐模板
  骨架的 abstract_node_sequence 吗? 若破坏骨架, 改用替代加章位置

如要求**删章** / **改章序**: 同样连锁更新。

### 3.5. 改章内容时的引用同步 (v30 lesson)

即使**章数不变、章序不变**, 只要 issue 修改了 `chapter_plan[i]` 的 `purpose` /
`claims_to_make` / role 语义, **也必须扫描下列位置的语义引用并同步改写**, 否则会出现
"章内容改了但 hook/bridge 仍说旧内容"的断链:

- `narrative_constraints.cross_section_hooks[]` 中 `from` / `to` = i 的条目:
  - 若 `hook_content` 提到 ch[i] 的旧内容 (e.g. "ch7末做愿景收束", "ch6 埋 tokens/J 证据"),
    改成新内容的表述
- `chapter_plan[i-1].chapter_bridge_hint.out_to_next_chapter` (前一章 → i 的桥接):
  - 若引用了 ch[i] 的旧 purpose/claims, 同步改
- `chapter_plan[i].chapter_bridge_hint.in_from_prev_chapter` (前章 → i 的接口):
  - 若引用了 ch[i-1] 的旧 setup, 同步改
- `chapter_plan[i].chapter_bridge_hint.out_to_next_chapter` (i → 下一章):
  - 若 ch[i] 内容变了, 该桥接文本可能过时, 检查
- `narrative_constraints.thesis_callback.callback_at_chapters` 若含 i 但 ch[i] 内容改后
  不再承接 thesis, 从数组中移除 i (或改 thesis 表述)
- `narrative_constraints.anchor_term_trajectory[].must_appear_in_chapters` 若含 i 但
  ch[i] 新 claims 已不含该 anchor term, 移除

**判定规则**: 对每个被改的 chapter[i], 逐条扫描上述位置, 对比"旧引用文本 vs 新 claims/purpose",
若明显不一致就同步。同步动作也计入 `referenced_review_issues[]`, `action_taken` 里写
"因 chi purpose/claims 改动, 连锁同步 XXX".

**anti-pattern** (v30 观察到的实际 bug):
- ch7 purpose 改为 "愿景留给 ch8", 但 `cross_section_hooks[5].hook_content` 仍写 "ch7 末做愿景收束"
- ch6 claims 加了 "tokens/J 收敛证据", 但 ch8 claims 未承接, 导致 thesis_callback 断链

### 3.6. 修复后的全局回归自检 (v31)

即使 issue 只改一处，也要在输出前做一次最小全局自检，避免“修完局部又留下新的叙事断链”:

- 检查 `selected_narrative_arc.borrowed_patterns[]` 是否混入 `deck_task` ID；若是，移除该条并改记到兼容字段 `selected_meta_pattern` / `provenance.referenced_meta_pattern_ids`
- 检查 `chapter_plan[role=outlook/discussion/background]` 是否单轴；若一章同时覆盖 3 个以上独立轴，优先收敛到一个主轴，而不是把问题留给 Codex
- 检查 `narrative_constraints.cross_section_hooks` 是否至少覆盖大多数章间过渡；若少于 `chapter_plan.length - 2`，补齐最关键的相邻章 handoff
- 检查最后一章 `closing` 是否回扣 cover title / core thesis；若没有，补一句回扣，不引入新论据
- 检查同一 `parallel_group_id` 的章是否仍用同一主框架词汇；若改坏了，统一术语而不是拆掉并行结构

**原则**: 这不是重新设计整份 idea，而是把因本轮修复暴露出的结构性断链一起补上，避免下一轮 review 继续报新 issue。

### 4. preserve untouched 字段必须 byte-identical

未被 issue.location 覆盖的字段必须**逐字保留**:
- `selected_narrative_arc.primary_pattern_id` (除非 issue 直接 flag)
- 各章 `section_rhythm_pattern_id` / `section_rhythm_summary` / `section_rhythm_source_count`
  (v4.0 rhythm 选择, 不重选除非 issue flag)
- `identity.*` (除非 codex 提示 schema_completeness)
- `provenance.referenced_pattern_ids` / `referenced_rhythm_pattern_ids`

**anti-rule**: 不要 reformat 整 JSON, 不要 paraphrase 未 flag 的 claims, 不要补 provenance 没要求加的字段。

### 5. rule_compliance issue 的修复参考 hard_rules_summary

issue.evidence 引用了某 rule_id (如 `trend_chapter_follows_method_chapters`), 在 hard_rules_summary 里查该 rule 的 summary, 按 rule 语义修复。

常见 rule 修法对照 (示例, 非穷举):

| rule_id | 修法 |
|---|---|
| `closing_required_and_at_last_2_slides` | 加 closing 章, 放最后 |
| `motivation_before_method_invariant` | 调 motivation 章 section_index < method 章最小 index |
| `trend_chapter_follows_method_chapters` | 在 method 末和 closing 之间 insert outlook/discussion 章 |
| `framework_overview_redisplay_at_each_layer_chapter_open` | 更新 narrative_constraints.framework_anchor_repeat.repeat_at_chapters 加入所有 method 章 index |
| `solution_chapter_closes_with_overall_framework_diagram` | method 章末页 claims_to_setup_for_later 加 "回扣 framework" |
| `main_thesis_repeated_across_majority_chapters` | narrative_constraints.thesis_callback.callback_at_chapters 加章 |
| `experiment_chapter_page_count_5_to_15` | 调 expected_pages_indicative ∈ [5,15] |

### 5.5. v6.1 阶段边界保护

修复任何 issue 时都不得引入 IDEA 阶段越界字段:

- `slide_stubs`
- `chapter_page_count`
- `page_to_rhythm_node_map`
- `page_specific_archetypes`
- `referenced_archetype_ids`
- `target_title`
- `target_claim`
- `key_points`
- `source_resource_ids`
- `source_slide_id`
- `slides_by_section`
- `library_pool_slide_ids`

如果 issue 要求修页级骨架或 source binding, 只在 `referenced_review_issues[].action_taken`
记录 `"escalated_to_outline"`; 不要在 IDEA 阶段修这些字段。

### 6. 记录修改痕迹

输出新字段 `referenced_review_issues` (同时涵盖 codex + human):

```json
{
  ...原 idea-analysis.json 字段 (修改过的)...,
  "fix_round": <current_fix_round + 1, 不存在时 = 1>,
  "referenced_review_issues": [
    {
      "source": "codex" | "human",
      "category": "rule_compliance",
      "severity": "high",
      "location": "narrative_constraints.framework_anchor_repeat",
      "rule_id_or_summary": "framework_overview_redisplay_at_each_layer_chapter_open",
      "human_note": "<若 source=human, 原自然语言保留>",
      "action_taken": "<≤80 字, 具体改了什么字段, 加/删/调了哪个值>",
      "status": "applied | skipped (low priority) | skipped (ambiguous fix) | skipped (would violate template skeleton) | skipped (conflicts with human intent) | skipped (would regress user concern)"
    }
  ]
}
```

### 7. **user_concern_history regression guard (HARD constraint)**

prior_idea_analysis.user_concern_history 中每条 `must_not_regress=true` 的 concern 是
**绝对不可违反的硬约束**:

- 在 fix 任何 issue 之前, 先扫一遍 user_concern_history, 列出所有 `must_not_regress=true`
  的 (concern, resolved_at_field, applied_action) 三元组
- 修任何 issue 时, 检查所选改法是否会触及上述 resolved_at_field
- 若某条 suggested_fix 的修改会**违反 user concern** (e.g. user 之前要求 ch5/6 用不同 deck,
  codex 现在建议把 ch5 改回跟 ch6 同 deck) → **拒绝该 issue** (仅当 source=codex; source=human
  的新意图允许覆盖旧 concern, 见下方 human append 规则):
  - 在 referenced_review_issues 标 status="skipped (would regress user concern: <concern 引用>)"
  - 改用替代方案 (e.g. 不动 ch5, 改 ch6 carrier 满足 codex 同时不违反 user)
  - 若没有替代方案, 报告 in `referenced_review_issues[].action_taken` 写
    "无解, codex 建议与 user concern 冲突, 保留 user concern, 跳过此 codex issue"

**human issue 覆盖旧 concern 的处理**:
- source=human 的 issue 若与旧 user_concern_history 冲突, **优先响应新的 human 意图** (人有权
  更新自己的想法), 在旧对应 concern 上标 `superseded_at_fix_round: <本轮>` 且 `must_not_regress: false`
- 同时 append 一条新 user_concern_history 记录反映本轮 human 意图 (append 规则见 #9)

**user_concern_history 必须保留** (复制到输出, 不要删/合并); 仅在上述 supersede 场景下修改
`must_not_regress` 字段。

### 8. **selected_narrative_pattern_body 骨架约束 (HARD constraint)**

selected_narrative_pattern_body 是 IDEA_ANALYSIS 阶段 Claude 已选定的 primary_pattern_id
对应模板全文。修 chapter_plan / section_role / 章节数 时必须:

- 对照模板 body 中的**骨架序列描述** (通常在 `## 骨架 / 节奏 / abstract_node_sequence` 类章节),
  确认改后 chapter_plan[].section_role 序列仍能对齐模板骨架
- 若某个 issue 的 suggested_fix 会破坏骨架 (e.g. 模板要求 "background→motivation→method→experiment→discussion"
  五段, issue 说"删掉 discussion", 破坏骨架) → **skip 该 issue** 或改用不破坏骨架的替代方案
- 同理 rhythm_pattern_bodies 是每章 rhythm 骨架的完整描述, 修某章 claims_to_make / expected_pages
  时对照对应 rhythm body 保证不违反该章节奏约束 (e.g. rhythm 要求"3-4 slides", 别改到 8)

**破坏骨架** 是硬红线, 优先级高于 codex issue, 次于 human 明确要求破坏 (human 意图 > 骨架 > codex).

---

## Output Schema

完整 `idea-analysis.json` v6.1 (所有原字段保留, schema_version 不变 "6.1", 加/更新
`fix_round` + `referenced_review_issues` + 视情况更新 `user_concern_history`)

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

---

## Hard Rules

1. **Surgical**: 只动 issue.location 字段 + 因连锁更新必须改的派生字段; 其他字段 byte-identical 保留
2. **优先级**: (severity) critical > high; medium/low 可跳过; (source) human > codex 于冲突时
3. **加/删章** 必须重编 section_index 全 chain, 同步 narrative_constraints / reuse_strategy 引用
4. **不重写** selected_narrative_arc / section_rhythm_pattern_id 字段 (除非 issue 直接 flag)
5. **不补充** provenance.referenced_rule_ids_followed 等审计字段 (除非 issue 要求)
6. **不 paraphrase** 未 flag 的 chapter.purpose / claims_to_make 字段值
7. **schema_version 不变** ("6.1"); generated_at / source 字段不改
8. **referenced_review_issues 必须涵盖所有 input critical/high issues** (每条标 applied/skipped 状态)
9. **user_concern_history 累加保留**: 输入原封保留; source=human issue 若与旧 concern 冲突,
   在旧对应记录标 superseded 而不是删; 本轮 applied 的 human issue append 新 concern 记录
   (`must_not_regress: true`)
10. **selected_narrative_pattern_body 骨架不破坏** (除非 human 明确要求)
11. Output **strict JSON only**

---

## Anti-rules (常见错误, 不要做)

- ❌ "趁此机会优化一下 selected_narrative_arc.why_chosen 文字" — 不在 issue location 里, 不要动
- ❌ "把 section_rhythm_pattern_id 按新章序重选" — 未 flag 即保留原 rhythm 选择
- ❌ "claims_to_make 重新精炼一遍" — 未 flag 即保留原文
- ❌ "把 narrative_constraints 整段重写让它更通顺" — 只改引用变化的 index 字段
- ❌ "加 fix_round 但漏掉 referenced_review_issues" — 两个必须配对
- ❌ "把 issue.suggested_fix 原文复制到 chapter.purpose" — suggested_fix 是建议, 你要按建议改 schema 字段, 不要直接拷文本
- ❌ "human issue 严重程度低就跳过" — human 无 severity 视同 high, 除非 human 显式标 low
- ❌ "codex 说要删这章, human 说要保留 → 删了" — 冲突时保 human 意图, skip codex
- ❌ "为了满足 codex issue, 把章序改到破坏 selected_narrative_pattern_body 骨架" — 骨架优先
