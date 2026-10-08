# Logic Meta-Synthesizer (A)

你正在读**已抽出的 186 条 deck_level + section_level pattern**, 抽取**跨场景通用的叙事元骨架**
(meta-pattern)。每条 meta-pattern 描述"一类**通用说服/汇报意图**该用什么核心任务序列展开",
不绑定具体 report_type。现有 186 条 concrete pattern 会作为它的 **instantiations** 列出来。

**为什么需要 meta**: 现有 deck_level 6 条 + section_level 180 条都停在"表层场景 → 结构"的
lookup, 只能覆盖训练语料里出现过的场景。当用户主题不属于任何已见 report_type (e.g. 内部
techtalk / 售前 pitch / 项目复盘), 需要 meta-pattern 提供的推理骨架来动态组装 deck。

## 后续用途 (IMPORTANT — 你写 meta 时脑子里要有下游)

```
IDEA_ANALYSIS 阶段:
  用户主题 + 目标听众 + 汇报诉求
    → 匹一条 meta-pattern (定核心任务序列 + 不变约束)
    → 用 meta 里的 instantiations 找最近的 concrete deck_level pattern
    → 每章从 section_level pattern 里挑 (受 meta 的 task_decomposition 约束)
```

**下游要 meta 帮它做的事**:
1. 给出一条 **抽象的核心任务序列** (e.g. context → claim → evidence → takeaway),
   下游从中生成章节骨架, 而不是照抄某个 report_type 的固定 5 段
2. 给出 **不变约束** (什么必须有, 什么可省), 让下游知道剪裁的自由度
3. 给出 **决策信号**, 让 IDEA_ANALYSIS 知道用户什么信号该选此 meta

---

## Input

```json
{
  "concrete_patterns": [
    {
      "id": "paper_share_bg_challenge_solution_eval_summary_canonical",
      "layer": "deck_level",
      "title": "顶会论文分享·五段式",
      "applicable_when": {"report_type": ["paper_share"], "deck_size_range": [15, 40], ...},
      "abstract_node_sequence": [{"role": "cover", ...}, ...],
      "applicable_summary": "...",
      "source_count": 10,
      "confidence": "high"
    },
    ... 186 patterns total (6 deck_level + 180 section_level)
  ]
}
```

Slim 版本 — 不含 carriers (省 tokens)。

---

## Output: `logic_meta_patterns.json`

```json
{
  "meta_patterns": [
    {
      "id": "convince_of_novelty_via_gap_then_evidence",
      "title": "以创新说服·揭 gap → 抛方案 → 证效",
      "narrative_purpose": "让专业听众接受本工作的创新性与可信度",
      "target_audience_types": ["学术同行", "评审"],
      "trigger_signals": [
        "用户主题含'论文分享/学术汇报/开题/评审'",
        "听众为专家/评审, 需被说服接受创新点",
        "存在明确的 gap 陈述空间 (已有工作不够 X)"
      ],
      "core_task_sequence": [
        {"task": "context_establishment",
         "purpose": "建立共享 vocabulary + landscape, 给听众上下文",
         "typical_chapter_roles": ["background", "motivation"],
         "swappable": false},
        {"task": "gap_or_pain_reveal",
         "purpose": "揭示已有工作的空白/矛盾, 立靶",
         "typical_chapter_roles": ["motivation", "problem"],
         "swappable": false},
        {"task": "claim_and_solution",
         "purpose": "抛主张 + 方法概述",
         "typical_chapter_roles": ["method", "framework"],
         "swappable": false},
        {"task": "evidence_deployment",
         "purpose": "用数据/案例支撑主张",
         "typical_chapter_roles": ["result", "evaluation"],
         "swappable": false},
        {"task": "takeaway",
         "purpose": "凝练贡献 + 未来方向",
         "typical_chapter_roles": ["summary", "conclusion"],
         "swappable": true}
      ],
      "invariant_principles": [
        "gap 必须在 solution 之前 — 否则听众不知道方案要解决什么",
        "evidence 必须与 claim 匹配 — 每个 claim 至少一条对应 evidence",
        "context 深度取决于听众专业度 — 专家听众可压缩, 跨领域听众必须展开"
      ],
      "swappable_dimensions": [
        "context_establishment 页数 (专家 1-2 页 vs 跨领域 3-6 页)",
        "evidence_deployment 中 ablation 是否单开一章",
        "takeaway 是否包含 future work"
      ],
      "info_density_arc": "稀疏 (context) → 密集 (gap + solution) → 密集 (evidence) → 稀疏 (takeaway)",
      "instantiations": [
        "paper_share_bg_challenge_solution_eval_summary_canonical",
        "qualifying_exam_defense_with_study_progress_and_appendix"
      ],
      "anti_patterns": [
        "solution-first (未立 gap 先讲方法) — 听众不接受动机",
        "evidence-only (只有实验没有故事) — 听众记不住 takeaway"
      ]
    },
    ... (5-10 条 meta-pattern)
  ],
  "coverage": {
    "instantiated_deck_level_ids": [...],       // 现有 6 条 deck_level 全被覆盖的 id 列
    "instantiated_section_level_ids": [...],    // 现有 180 条中被至少一 meta 引用的 id 列
    "unmapped_pattern_ids": []                  // 没被任何 meta 覆盖的 pattern id (应尽量为空)
  },
  "extraction_notes": "本次抽出 N 条 meta-pattern, 覆盖 X/186 条 concrete pattern"
}
```

---

## 抽 meta-pattern 的核心动作

### Step 1 — 按叙事意图聚类
把 186 条 concrete pattern 按**说服/汇报意图**分组, 不看 report_type。可能的意图桶:
- **说服接受创新性** (说服评审/同行接受本工作的新贡献) → paper_share, 部分 research_report method 章
- **对齐立项计划** (说服资助方/导师批准方向) → research_proposal, 开题
- **同步项目进展** (让共同工作者跟上当前状态) → qualifying_exam, 组会
- **传授方法论** (系统性介绍某技术路线, 让听众能自己复现思路) → tutorial, invited talk
- **展示能力/成果** (说服听众相信团队/机构值得合作) → 团队介绍, self_intro
- **收束致谢** (段落收尾) → closing, appendix

每桶 15-40 条 pattern 归为一个 meta 的 instantiations。

### Step 2 — 提取通用任务序列
从每桶 pattern 的 `abstract_node_sequence` 里, 抽**跨具体章节/archetype 的抽象任务**。
不用具体 `chapter_role`, 用**说服学 taxonomy** (Toulmin argument, narrative arc)。

例:
- 桶「说服接受创新性」共通任务序列 = context → gap → claim → evidence → takeaway
- 桶「同步项目进展」共通任务序列 = current_state → what_changed → next_steps
- 桶「对齐立项计划」共通任务序列 = motivation → plan_overview → feasibility_and_risk → resource_ask

### Step 3 — 找不变约束
在同一桶内比对多条 concrete pattern, 找**所有 pattern 都共有的约束**:
- 顺序约束 (e.g. "gap 必须在 solution 之前")
- 结构约束 (e.g. "任何说服型 deck 都需 cover")
- 内容约束 (e.g. "evidence 必须与 claim 一对一")

### Step 4 — 标记 swappable 维度
在同一桶内比对差异, 找**同 meta 下可变的维度**:
- 章数量 (paper_share 5章 vs 变体 6章 vs 4章)
- 某任务是否单独成章 (ablation 单章 vs 合并入 evaluation)
- 某任务的详略 (context 1 页 vs 6 页)

### Step 5 — 写 trigger_signals + audience_goal_matrix
从 concrete pattern 的 `scenario_keywords` / `audience_levels` 里归纳:
- 什么用户输入信号该匹此 meta
- 听众类型 × 汇报诉求 什么组合适用

### Step 6 — 覆盖度检查
每条 concrete pattern 至少应该被 1 条 meta 覆盖 (`instantiations` 里出现)。若有 concrete
pattern 不属于任何 meta, 或说明它是 outlier (`unmapped_pattern_ids` 列出并说明原因),
或再加一条 meta 覆盖之。

---

## Field semantics

- **`id`**: snake_case, 描述意图 + 手段. e.g. `convince_of_novelty_via_gap_then_evidence` /
  `align_on_plan_via_motivation_then_feasibility` / `sync_progress_via_current_state_then_next_steps`
- **`narrative_purpose`**: ≤30 字, 一句话描述这类 deck 的说服/汇报意图
- **`target_audience_types`**: 面向什么听众 (可多个)
- **`trigger_signals`**: 用户输入里出现哪些线索时该选此 meta. 具体, 可机器判断
- **`core_task_sequence`**: 3-7 个抽象任务的**顺序序列**. 每个 task 必须有:
  - `task` (snake_case 任务名)
  - `purpose` (该任务为整 deck 说服目标的贡献)
  - `typical_chapter_roles` (concrete pattern 里对应的 chapter_role 列表)
  - `swappable` (布尔: 此任务是否可省)
- **`invariant_principles`**: 3-6 条本 meta 下**永远为真**的原则. 顺序/结构/内容约束都可以
- **`swappable_dimensions`**: 3-6 条本 meta 下**可以变**的维度. 每条描述"什么可以怎么变"
- **`info_density_arc`**: 一句话描述信息密度模式 (稀疏/密集变化)
- **`instantiations`**: 本 meta 覆盖的 concrete pattern id 列 (deck_level 优先, 也可含 section_level).
  数量 ≥3 (少于 3 条 concrete pattern 就不足以支撑 meta)
- **`anti_patterns`**: 违反本 meta 会怎样, 与 concrete pattern 的 anti_patterns 区分 —
  这里是**跨具体 pattern 的**通用反模式

---

## Hard rules

- **meta_patterns 数量**: 5-10 条 (太少覆盖不全, 太多重复 concrete 层)
- **instantiations 每条 ≥3**: 少于 3 说明不是 meta 而是变体 concrete pattern
- **每条 concrete pattern 应被 ≥1 meta 覆盖**: 用 `coverage.instantiated_*_ids` 汇总, `unmapped_pattern_ids` 应尽量空 (>10 条 unmapped 时应再加 meta)
- **core_task_sequence 必须抽象**: 不直接抄 concrete pattern 的 chapter_role 序列, 用**说服学任务**级别的抽象 (context/gap/claim/evidence/takeaway / current_state/change/next / motivation/plan/feasibility/ask ...)
- **不要重复 concrete 层的内容**: meta 不列具体 archetype (那是 section_level 的事), 不列具体页数 (那是 deck_level 的事)
- **invariant_principles 必须可 falsifiable**: "listen 时能被检验的" 约束, 不写主观美感
- **id 唯一**

## Output format

- Strict JSON only, first char `{`, last char `}`
- 顶层只有 `meta_patterns / coverage / extraction_notes`
- meta_patterns[] 按 `instantiations` 数量 desc 排序
- No prose preamble, no code fences, direct stdout
- 输出预期 20-50 KB
