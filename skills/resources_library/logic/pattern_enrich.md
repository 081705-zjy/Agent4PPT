# Logic Pattern Enricher (C)

你正在读**一条已有的 concrete pattern** (deck_level 或 section_level), 给它补上一组
**推理层抽象字段**, 让下游 IDEA_ANALYSIS / OUTLINE 阶段能基于 reasoning 而不是 lookup 使用它。

**任务**: 输入一条 pattern JSON, 输出该 pattern 的**补丁字段** (JSON dict), driver 会
把补丁 merge 回 pattern 文件。**不要**改写现有字段, 只**添加**新字段。

**注意**: pattern 可能是 deck_level (章节序列级) 或 section_level (章内页序列级), 补丁字段
不同。你会在 input 里看到 `layer` 字段区分。

---

## Input

```json
{
  "pattern": {
    "id": "paper_share_bg_challenge_solution_eval_summary_canonical",
    "layer": "deck_level",                                   // ← "deck_level" or "section_level"
    "title": "...",
    "applicable_when": {...},
    "abstract_node_sequence": [...],
    "narrative_arc": "...",                                  // deck_level 有
    "page_transitions_pattern": [...],                       // section_level 有
    "applicable_summary": "...",
    "anti_patterns": [...],
    "carriers": [
      {..., "chapter_outline": [...] or "slides": [...]},    // deck_level 或 section_level 各自
      ...
    ],
    "source_count": 10,
    "confidence": "high"
  }
}
```

**IMPORTANT**: 你能看到该 pattern 的 **carriers** (真实源 deck/section 的引用 + 章节大纲
或每张 slide 的详细字段)。用 carriers 归纳出该 pattern 的**真实执行细节**, 而不是凭空想象。

---

## Output (deck_level 的补丁)

若 `pattern.layer == "deck_level"`, 输出:

```json
{
  "pattern_id": "paper_share_bg_challenge_solution_eval_summary_canonical",
  "layer": "deck_level",
  "enrichment": {
    "narrative_goal": "让学术同行接受本论文的创新性与技术可靠性",
    "audience_goal_matrix": [
      {"audience": "顶会评审", "primary_goal": "评审接受",
       "which_chapters_expand": ["motivation", "challenge", "evaluation"],
       "which_chapters_compress": ["background"]},
      {"audience": "同组同行", "primary_goal": "理解与讨论",
       "which_chapters_expand": ["method", "ablation"],
       "which_chapters_compress": ["motivation"]}
    ],
    "chapter_dependency_graph": [
      {"from": "background", "to": "challenge",
       "dependency_type": "sets_up", "dependency_reason": "背景章为挑战陈述建立 landscape"},
      {"from": "challenge", "to": "solution",
       "dependency_type": "aim", "dependency_reason": "挑战定义了 solution 必须打的靶"},
      {"from": "solution", "to": "evaluation",
       "dependency_type": "must_verify", "dependency_reason": "方案的每个 claim 必须被 evaluation 验证"},
      {"from": "evaluation", "to": "summary",
       "dependency_type": "distill", "dependency_reason": "总结把验证过的 claim 凝练成 takeaway"}
    ],
    "info_density_arc": [
      {"chapter": "background", "density": "sparse", "reason": "铺 context 不宜信息过载"},
      {"chapter": "challenge", "density": "dense", "reason": "多点痛点陈述, 需累积压力"},
      {"chapter": "solution", "density": "dense", "reason": "方法细节密集, 抗信息稀释"},
      {"chapter": "evaluation", "density": "dense", "reason": "多图表多数字支撑 claim"},
      {"chapter": "summary", "density": "sparse", "reason": "凝练 takeaway 需空间"}
    ],
    "invariant_constraints": [
      "cover 必须首页",
      "challenge 必须在 solution 之前 (否则 solution 无对标)",
      "evaluation 必须覆盖至少 solution 抛出的每个 claim",
      "summary 必须回扣 motivation (对读者形成回环)"
    ],
    "swappable_dimensions": [
      {"dimension": "ablation 章位置",
       "options": ["单独章 (evaluation 之后)", "并入 evaluation 章末尾"],
       "decision_criterion": "论文 ablation 结果数 > 3 组时单独章"},
      {"dimension": "related work 位置",
       "options": ["background 章内一节", "challenge 章末对比表"],
       "decision_criterion": "已有工作 ≤ 3 项时并入 challenge; 更多则 background 单节"},
      {"dimension": "future work 是否含在 summary",
       "options": ["含 (研究导向听众)", "不含 (工业导向听众)"],
       "decision_criterion": "看听众"}
    ],
    "reasoning_level_summary": "本 pattern 服务'让学术同行接受创新性'的说服意图, 用 gap-then-solution 结构立靶, 用 evaluation 兑现每个 claim, 用 summary 完成回扣。深度可根据听众专业度和 ablation 复杂度调整。"
  }
}
```

## Output (section_level 的补丁)

若 `pattern.layer == "section_level"`, 输出:

```json
{
  "pattern_id": "method_technique_route_full_arc_prior_challenge_paper_method_result",
  "layer": "section_level",
  "enrichment": {
    "chapter_task_decomposition": [
      {"task_id": "situate_within_landscape",
       "purpose": "定位本方法在已有工作图谱里的位置",
       "typical_pages_count": "1-2",
       "must_have": true},
      {"task_id": "isolate_key_contradiction",
       "purpose": "从已有工作中抽出一个未解矛盾, 立本方法的靶",
       "typical_pages_count": "1",
       "must_have": true},
      {"task_id": "introduce_paper_and_method_kernel",
       "purpose": "抛论文封面 + 方法核心思想 (一页级)",
       "typical_pages_count": "1-2",
       "must_have": true},
      {"task_id": "unfold_method_implementation",
       "purpose": "分层展开方法实现细节 (Pattern → 硬件 → 动画帧 递进)",
       "typical_pages_count": "2-5",
       "must_have": true},
      {"task_id": "deliver_result_headline",
       "purpose": "用一页收在核心结果数字上",
       "typical_pages_count": "1-2",
       "must_have": true}
    ],
    "task_to_slide_binding": [
      {"task_id": "situate_within_landscape",
       "binds_to_role_in_pattern": ["toc_progress_highlight", "prior_works_taxonomy_table"],
       "why_this_binding": "章首 agenda 定位 + 表格 landscape 双页承担建 landscape"},
      {"task_id": "isolate_key_contradiction",
       "binds_to_role_in_pattern": ["challenge_key_contradiction_statement"],
       "why_this_binding": "大字文本页承担立靶"},
      ...
    ],
    "persuasion_path": [
      {"page_position": "start",
       "contributes_to_conviction": "读者对 landscape 有共识, 承认已有工作局限"},
      {"page_position": "middle",
       "contributes_to_conviction": "读者接受方法针对的矛盾是真的, 且方法是合理的应对"},
      {"page_position": "end",
       "contributes_to_conviction": "读者看到结果数字被本方法解释, 承认方法有效"}
    ],
    "archetype_alternatives": [
      {"task_id": "isolate_key_contradiction",
       "primary_archetype": "challenge_key_contradiction_statement",
       "alternatives": [
         {"archetype": "quantitative_gap_chart",
          "when_to_use": "痛点可量化, 且数据说明力强于文字"},
         {"archetype": "domain_pain_point_callout",
          "when_to_use": "痛点是共识, 文字大字比数字更冲击"}
       ]},
      {"task_id": "deliver_result_headline",
       "primary_archetype": "result_efficiency_or_deployment_headline",
       "alternatives": [
         {"archetype": "single_experiment_result_speedup_callout",
          "when_to_use": "结果核心是单个数字 (加速比等)"},
         {"archetype": "result_table_systematic",
          "when_to_use": "结果覆盖多任务/多基线"}
       ]}
    ],
    "page_dependency": [
      {"page_role_from": "prior_works_taxonomy_table",
       "page_role_to": "challenge_key_contradiction_statement",
       "what_prev_must_establish": "已有工作 landscape 被列全",
       "why_dependency": "抽矛盾时听众得知道 baseline"},
      {"page_role_from": "paper_title_authors_only",
       "page_role_to": "method_formula_overview_with_positioning",
       "what_prev_must_establish": "论文身份被建立, 听众进入方法接收态",
       "why_dependency": "方法总览页假设听众已知'是这篇论文的方法'"}
    ],
    "reasoning_level_summary": "本 section pattern 承担 method 章的说服任务 = 让听众相信矛盾真实 + 方法合理 + 效果可信。5 个子任务串成完整弧线, 每个任务对应 1-2 张 slide, 主要 archetype 可替换但任务序列不能变。"
  }
}
```

---

## Field semantics (deck_level enrichment)

- **`narrative_goal`**: ≤30 字, 本 deck 的说服/汇报意图
- **`audience_goal_matrix`**: 3-5 个 audience × goal 组合, 每组给"该展开哪几章, 该压缩哪几章"
- **`chapter_dependency_graph`**: 章间依赖. 每条边:
  - `from` / `to` (章节 role, 从 `abstract_node_sequence` 抄)
  - `dependency_type` ∈ {`sets_up`, `aim`, `must_verify`, `distill`, `parallel_continuation`, `enable_bridge`}
  - `dependency_reason` (为什么 to 需要 from)
- **`info_density_arc`**: 每章的信息密度 (`sparse` / `medium` / `dense`) + 一句 reason
- **`invariant_constraints`**: 3-6 条**本 pattern 下永远为真的**约束. 具体可检验, 不写主观美感
- **`swappable_dimensions`**: 3-6 个可变维度. 每条含 `dimension` + `options` + `decision_criterion`
- **`reasoning_level_summary`**: ≤120 字, 一段抽象总结, 让下游读它就能判断是否适配

## Field semantics (section_level enrichment)

- **`chapter_task_decomposition`**: 3-6 个子任务. 每条:
  - `task_id` (snake_case)
  - `purpose` (该任务对章节说服目标的贡献)
  - `typical_pages_count` (数字或 "1-2")
  - `must_have` (布尔: 是否必须)
- **`task_to_slide_binding`**: 每个 task 绑定的 `role_in_pattern` (从 `abstract_node_sequence[].archetype` 抄) + 为什么绑定
- **`persuasion_path`**: 章内 start / middle / end 各自对说服的贡献
- **`archetype_alternatives`**: 对可替换的 task, 列 primary_archetype + alternatives (每个含
  `archetype` + `when_to_use`)
- **`page_dependency`**: 章内页与页的依赖. 每条含 `from` / `to` (用 role_in_pattern) + `what_prev_must_establish` + `why_dependency`
- **`reasoning_level_summary`**: ≤120 字

---

## Process

### Step 1 — 读 pattern
读 input.pattern, 分辨 layer (deck_level or section_level)。

### Step 2 — 读 carriers
从 carriers 里看**具体 chapter_outline (deck_level) 或每 slide 的 role_in_pattern + slide_title / slide_claim (section_level)**, 归纳出真实执行细节。

### Step 3 — 抽 reasoning 字段
根据 carriers 里的真实例子, 抽:
- **narrative_goal / chapter_task_decomposition** (说服意图)
- **audience_goal_matrix / persuasion_path** (听众-目标匹配)
- **chapter_dependency_graph / page_dependency** (要素间依赖)
- **info_density_arc** (信息密度)
- **invariant_constraints** (不变约束)
- **swappable_dimensions / archetype_alternatives** (可变维度)

### Step 4 — 写 reasoning_level_summary
用 ≤120 字总结上面所有字段, 让下游读一句就能判断本 pattern 适不适用。

---

## Hard rules

- **必须输出所有必填字段**: deck_level 补丁 7 大项 (narrative_goal / audience_goal_matrix /
  chapter_dependency_graph / info_density_arc / invariant_constraints / swappable_dimensions /
  reasoning_level_summary), section_level 补丁 6 大项 (chapter_task_decomposition /
  task_to_slide_binding / persuasion_path / archetype_alternatives / page_dependency /
  reasoning_level_summary)
- **不修改**现有 pattern 字段, 只输出补丁 (`enrichment` 对象)
- **必须基于 carriers 真实内容**, 不能凭空想象
- **swappable_dimensions ≥3 条**: 至少给下游 3 个可以剪裁的维度
- **invariant_constraints ≥3 条**: 至少给下游 3 条约束
- **role_in_pattern / chapter_role 必须来自 input pattern**: 引用 `abstract_node_sequence` 里出现过的 role, 不发明新 role
- **`pattern_id` + `layer` 必须与 input 一致**

## Output format

- Strict JSON only, first char `{`, last char `}`
- 顶层三个 key: `pattern_id` / `layer` / `enrichment`
- No prose preamble, no code fences, direct stdout
- 输出预期 5-15 KB
