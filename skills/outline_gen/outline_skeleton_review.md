# OUTLINE Skeleton Review (v17 C.1b, Codex 骨架审)

## Purpose

在 Stage 1a (chapter_stub) 生成完 8 章 stub 后, 由 codex **一次性审查全 deck 骨架**, 检查:
- 章序合理性
- 章内 stub 序列 (role/archetype/placement/rhythm 对齐)
- chapter_decomposition 分解合理性
- 章间叙事流 (thesis / framework_anchor / cross_section_hooks 落实)
- 41 logic_story rule 抽样 (cover_to_agenda_distance / method 章平衡 / closing_future_vision)

**任务边界**:
- ✅ 只审骨架 (stubs 数组), 不看 slide detail
- ✅ 出 issue 时按 `fix_target_layer` 分类:
  - `chapter_decomposition` — 某章 subline 分解错 → driver 重跑该章 Stage 1a
  - `deck_skeleton` — 全 deck 章序问题 → driver escalate (罕见, 通常 IDEA 已保证)
  - `chapter_rhythm` — 章内 archetype 序列跟 rhythm_pattern 不对齐 → 重跑 Stage 1a
  - `stub_polish` — 小问题 (page_purpose_hint 文字调整) → 直接改 stub 字段
- ❌ 不选具体技术名 (那是 Stage 1b 的事)
- ❌ 不看 slide.target_claim / source (还没生成)

---

## Inputs

```json
{
  "idea_analysis": { /* 抽象 narrative, 用作对照 */ },
  "chapter_stubs": [
    {
      "chapter_index": 3,
      "chapter_title": "软硬件协同总体框架",
      "section_role": "framework",
      "rhythm_pattern_id": "...",
      "chapter_decomposition": {
        "axis": "...",
        "sublines": [{"index": 1, "name": "...", "abstract_topics": [...]}, ...],
        "rationale": "..."
      },
      "stubs": [{"slide_index_in_chapter":1, "target_role":"framework", "archetype":[...], "archetype_placement":"...", "page_purpose_hint":"..."}, ...],
      "page_count": 5,
      "page_to_rhythm_node_map": [0, 0, 1, 1, 2],
      "rhythm_adherence": {"rhythm_node_count": 3, "expansion_ratio": 1.67, "skipped_rhythm_nodes": []},
      "claim_to_stub_map": [{"claim_index":0, "stub_indices":[0,4]}, ...]
    },
    ...
  ],
  "rhythm_patterns": {
    "<rhythm_id>": {
      "abstract_node_sequence": [...],
      "carriers": [...]  // 参考, 不强 enforce
    },
    ...
  },
  "logic_story_rules_summary": [...],   /* 41 hard rules 摘要 */
  "page_specific_archetypes_summary": [...],  /* 54 archetype 摘要 */
  "round": <int>,
  "prior_issues": [ ... ]  /* 上一轮 (round=1 为空) */
}
```

---

## 检查层次 (自底向上)

### L0 SKELETON_INTEGRITY — **CRITICAL**

- 每章 chapter_index 唯一且 1..N 连续
- stubs 内 slide_index_in_chapter 1..M 连续
- archetype 必须从 page_specific_archetypes 枚举选
- role 必须合法枚举值 (cover/agenda/motivation/framework/method/discussion/closing/...)

### L1 CHAPTER_ROLE_CORRECTNESS — **HIGH**

- 第 1 章必须 role=cover
- 若有 agenda 章必须紧跟 cover (第 2 章)
- 最后一章必须 role=closing
- method/discussion 章 stubs 数 ≥ 3

### L2 CHAPTER_DECOMPOSITION (核心) — **HIGH** ⭐

- **fix_target_layer = chapter_decomposition**
- method/discussion 章必须有 2-4 条 subline, cover/closing/framework 章 sublines=[]
- **subline 不允许重叠** — 每条 subline 主题应互斥
- **subline 覆盖章 axis** — sublines 加起来应能撑起 chapter.axis 描述
- **abstract_topics 必须**是**抽象主题词** (调度 / 通信 / 稀疏 / FPGA 加速方向), **不允许**具体工作名 (vLLM / FlightLLM)
- 每条 subline stubs ≥ 2 (至少 opener + method 1 张)

### L3 RHYTHM_ADHERENCE — **MEDIUM/HIGH**

- **fix_target_layer = chapter_rhythm**
- 每章 stubs 数量 ≥ rhythm_pattern.abstract_node_sequence 长度 (rhythm 装得下)
- page_to_rhythm_node_map 长度 = page_count
- 每章 skipped_rhythm_nodes 不超过 rhythm_node_count 的 30%
- expansion_ratio 在 [0.7, 2.5] 区间

### L3b METHOD_CHAPTER_CANONICAL_RHYTHM — **HIGH**

- **fix_target_layer = chapter_rhythm**
- 对所有主体 method/result/engineering/comparison 章, 先识别 canonical 章首结构:
  - 若任一主体章有 `chapter_divider` / `section_divider` / `agenda` /
    `framework_recap` stub, sibling 主体章也必须有同类结构 stub。
  - 若任一主体章采用 `chapter_divider → framework_recap → content`, 其他主体章不得直接进入
    `method` 内容页。
  - 结构 stub 的 `page_purpose_hint` 应体现"当前章/当前层高亮", 而不是具体方法内容。
- 违反时输出 HIGH issue, category=`method_chapter_structural_rhythm_inconsistent`,
  suggested_fix 指向缺失结构页的 chapter。

### L4 CROSS_CHAPTER_COHERENCE — **HIGH**

- **fix_target_layer = deck_skeleton** (若章序错) 或 **chapter_decomposition** (若某章缺 hook 位)
- IDEA narrative_constraints.thesis_callback.callback_at_chapters 里每个 chapter 必须有 ≥1 stub 的 page_purpose_hint 含"回扣" / "thesis" 类字样
- IDEA narrative_constraints.framework_anchor_repeat.repeat_at_chapters 每个 chapter 必须**首页** stub 是 framework recap 类 archetype
- IDEA narrative_constraints.cross_section_hooks 每对相邻 chapter 应能对齐 (前章末 stub hint 跟后章首 stub hint 呼应)

### L4b PARALLEL_WORK_BLOCK_TEMPLATE — **HIGH**

- **fix_target_layer = chapter_rhythm**
- 同一章内若有 ≥2 个代表工作 opener stub (archetype/page_purpose_hint 含 paper_intro /
  work_intro / case_study_opener / 代表工作), 必须采用同一 work-block template:
  - `opener → challenge → method → result`
  - 或同步压缩版 `opener → challenge → result`
- 不允许一个 work block 有 4 页、另一个只有 opener 或缺 result。
- 若资源库候选不足以支撑完整四段, skeleton 应同步压缩全部 work block, 不把不对称留到
  gapcard 阶段。

### L5 RULE_COMPLIANCE (抽样) — **MEDIUM**

- **fix_target_layer = stub_polish**
- `cover_to_first_content_distance_bounded` (cover 到第 1 张 content ≤ 3 张)
- `closing_chapter_includes_future_vision_slide` (closing 章末含 outlook 类 stub)
- `method_chapter_uses_numbered_tech_or_challenge_prefix` (method 章多 stub 应用编号 prefix)
- 抽样其余 41 rules

---

## Output (strict JSON only)

```json
{
  "ok": <bool>,
  "round": <int>,
  "issues_by_layer": {
    "L0": [...], "L1": [...], "L2": [...], "L3": [...], "L4": [...], "L5": [...]
  },
  "issues": [
    {
      "layer": "L0|L1|L2|L3|L4|L5",
      "category": "...",
      "severity": "critical|high|medium|low",
      "location": "chapter_stubs[3].stubs[2]  /  chapter_stubs[5].chapter_decomposition",
      "target_chapter_index": <int>,
      "fix_target_layer": "chapter_decomposition|deck_skeleton|chapter_rhythm|stub_polish",
      "evidence": "<≤120 字, 摘录原文>",
      "explanation": "<≤120 字>",
      "suggested_fix": "<≤180 字, 具体改什么>"
    }
  ],
  "layer_summary": [
    {"layer": "L0", "checked": true, "critical": 0, "high": 0, "medium": 0, "low": 0, "verdict": "pass"},
    ...
  ],
  "summary": "<≤100 字>"
}
```

---

## Hard rules

- **Output strict JSON only**
- L0 含 critical → 立即跳 L1/L2/L3/L4/L5, verdict="skipped"
- L1 含 critical/high → 跳 L2+
- L2 含 critical → 跳 L3+ (L2 是分解层, 错则后续 rhythm 无意义)
- `ok=true` 当且仅当所有 checked layer 无 critical/high
- issue 必须 精确到 location + target_chapter_index (driver dispatch 用)
- 不修 chapter_stubs 自己, 只报告 issue

## Anti-rules

- ❌ 不看 slide 详情 (还没生成)
- ❌ 不查具体技术名 (Stage 1b 阶段的事)
- ❌ 不报 style_unification_hint / claim_alignment (那是 Stage 1b + review 的事)
- ❌ 不做 chapter_decomposition 自己的判定 (审查, 不重写)
