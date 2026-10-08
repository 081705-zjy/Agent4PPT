# Draft Quality Score Skill — Codex Final Reviewer

端到端管线完成后,你（codex）作为独立终审员对最终产出 (draft-deck.pptx 的
逻辑表示 + 备注内容) 进行**多维评分**。你不重写任何内容,只给分数 + 问题
+ 改进建议。

## Inputs

```json
{
  "idea_analysis": {... brief 草稿,代表用户意图 ...},
  "outline": {... 50 页骨架,每页 role/claim/key_points ...},
  "slide_matches": {... 每页 0-3 候选 ...},
  "slide_plan": {... slide_plan + reuse_bindings ...},
  "draft_assembly_plan": {... 物理装配计划 ...},
  "draft_deck_summary": {
    "total_pages": 50,
    "direct_slide_reuse_count": 45,
    "placeholder_count": 5,
    "notes_with_alternates_count": 39,
    "average_notes_length": 1280
  },
  "speaker_notes_samples": [
    {"slide_index": 1, "notes_text": "【源页来源】... 【备选候选】..."},
    {"slide_index": 5, "notes_text": "..."},
    {"slide_index": 12, "notes_text": "..."},
    ...
  ]
}
```

## 评分维度 (5 个,每个 0-100)

### Dim 1: brief_alignment (与用户意图对齐度)
- outline 章节切分是否符合 `brief.expected_sections`
- 章节页数比例是否合理
- 关键术语 (brief.anchor_terms / brief.topic_tags) 是否在 outline / slide_matches
  中都有对应页
- 用户在 brief 中指明的 must_have_pages 是否都覆盖
- 是否遵守 brief 的章间硬约束 (如挑战编号 ① ~ ⑥ 一致性)

扣分点:章节缺失、关键术语漏掉、用户强调的内容没出现。

### Dim 2: structural_quality (结构质量)
- 章节是否嵌套或重叠
- 相邻页 claim 是否高度相似 (重复)
- role 多样性 (是否一连串相同 role,如 5 页连续 method 无过渡)
- target_role / target_claim / key_points 是否完整填写
- section_index 是否对齐 section_breakdown

扣分点:章节内容重复、role 单一、claim 重复、字段缺失。

### Dim 3: reuse_quality (复用质量)
- target_coverage (有候选页比例)
- 候选页是否真的语义匹配 (从 slide_matches 的 score / match_reason 判断)
- 复用来源是否过度集中在单一 deck (单一 deck 占比 > 60% 是问题)
- placeholder 是否合理 (内容页大量 placeholder 是问题; 结构页 placeholder OK)
- 候选页之间是否互补 (rank-1 / rank-2 / rank-3 内容是否同质)

扣分点:覆盖率低、来源过度集中、候选不互补、placeholder 多于合理量。

### Dim 4: notes_quality (备注质量 - 这次评测的重点)
重点评估每页 PowerPoint 备注内容,因为这是用户审阅时实际看的:
- 备注是否包含完整源页来源 (路径 + slide_index)
- 备注是否包含可执行的演讲建议 (本页讲什么 / 怎么讲解 / 与前后衔接)
- 备注的 Gap 任务 (must_replace / must_remove / must_add) 是否具体
- 【备选候选】段是否完整 (rank-2/3 信息含 来源/可用部分/与 rank-1 关系)
- 备注总长度是否合理 (太短不够用、太长读不完, 800-1500 字合适)
- 是否有低质量段 (如全靠模板套话、claim 跟标题重复)

**这一维度对 v4-rerun 测试最关键**——用户想看的就是备注内容能不能直接用。

扣分点:备注空泛、备选段缺失、Gap 任务不具体、长度极端、模板套话。

### Dim 5: usability (整体可用度)
- 用户拿到 draft-deck.pptx 后,有多少页可以**直接用**(不需要重大修改)
- 有多少页需要**轻微调整**(改改标题/数字)
- 有多少页需要**重新做**(候选不对题、placeholder 没东西)
- 用户大约需要多少小时把这份 draft 修成最终 deck

扣分点:大量页需要重做、需要的总工时高。

## Output schema

```json
{
  "schema_version": "1.0",
  "scores": {
    "brief_alignment": 85,
    "structural_quality": 78,
    "reuse_quality": 90,
    "notes_quality": 82,
    "usability": 80,
    "overall": 83
  },
  "score_explanations": {
    "brief_alignment": "...具体扣分原因,引用具体字段或页号...",
    "structural_quality": "...",
    "reuse_quality": "...",
    "notes_quality": "...",
    "usability": "..."
  },
  "critical_issues": [
    {
      "dim": "structural_quality | reuse_quality | ...",
      "severity": "critical | high | medium",
      "location": "slide_index=27 | section_index=4 | ...",
      "evidence": "具体引用 (≤120 chars)",
      "impact": "对最终 deck 的影响 (≤80 chars)",
      "suggested_fix": "改进建议 (≤120 chars)"
    }
  ],
  "strengths": [
    "本 deck 表现良好的方面 (≤4 条,每条 ≤60 chars)"
  ],
  "improvement_priorities": [
    "下一版应该优先改进的 3 件事 (按优先级排序,每条 ≤80 chars)"
  ],
  "estimated_user_effort_hours": 2.5,
  "summary": "本 deck 整体评价一句话 (≤100 chars)"
}
```

## Hard rules

- 输出 strict JSON only.
- 分数标准:
  - **90-100**: 直接可用,极少改动
  - **75-89**: 主体可用,需要轻度调整
  - **60-74**: 框架对但需要明显改进
  - **40-59**: 部分可用,需要大量改动
  - **<40**: 不可用,需要重做
- overall 是 5 个维度的**加权平均**: brief_alignment×0.20 + structural_quality×0.20 +
  reuse_quality×0.15 + notes_quality×0.30 + usability×0.15
  (notes_quality 权重最高因为是本次评测重点)
- `score_explanations` 必须有具体引用 (slide_index / section_index / 字段路径),
  不能写"整体不错"这种笼统话
- `critical_issues` 上限 10 条,只列真正影响产出可用度的问题
- `strengths` 上限 4 条,挑做得最好的部分
- `improvement_priorities` 上限 3 条,按优先级排
- `estimated_user_effort_hours`: 用户把这份 draft 修成最终 deck 大约需要的小时数
- 不要给"完美 100 分"或"全 0 分"的极端分,真实评分应该在 50-95 区间
- 不重写 deck, 不返回修正后的内容
