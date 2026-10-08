# Slide Rank-1 Semantic Selection Skill

## Purpose

为每个 target page 选 **rank-1 候选** — 在 candidate pool 中找语义最对题
的 source slide。**版式相似不参与选源决策**,仅作 tie-breaker。

## Inputs (per target page)

- `target_aspects`: 上一步 aspect_extraction 产出的 1-5 个 aspect
- `candidate_pool`: trim 后的 slide candidates (含 _pool_tier / score)
- `prev_target_rank1_resource_id` (可选): 前一个 target page 已选的 rank-1 rid
  (用于 ADJACENCY tie-breaker)

## Selection Logic

### Step 1 — 语义对齐评估

对每个 candidate 计算它**覆盖** target_aspects 的程度:

```
candidate.title / claim / what_this_slide_explains / transferable_to / text_samples
中明确提到了该 aspect 的内容,且该 aspect 不在 candidate.do_not_reuse_when 里。
```

**禁止** 把 `salient_visuals / template_svg / slide_role` 等版式信号
当作语义对齐证据。

### Step 2 — 排序

按"覆盖 aspect 数量"降序:
- 覆盖 4-5 个 aspect: 强对题 (score >= 0.85)
- 覆盖 2-3 个 aspect: 部分对题 (0.70-0.84)
- 覆盖 1 个 aspect: 弱对题 (0.50-0.69)
- 覆盖 0 个 aspect: 不对题, 不选 (即使版式很像)

### Step 3 — Tie-breaker (同语义对齐度时)

按以下顺序:

1. **Tier priority**: `_pool_tier=strong` > `same_deck` > `default`
   (`structural_*` tier 只在 target_role 是结构页时启用)
2. **ADJACENCY ACROSS TARGETS**: 若 `prev_target_rank1_resource_id` 是
   `deckA.slide_5`,而本候选是 `deckA.slide_6/7/8`,**rank-1 选这个**(视觉
   叙事连贯)
3. **Reusability strength**: `soft_pattern` > `hard_topic`

### Step 4 — 输出

```json
{
  "rank": 1,
  "resource_id": "tpl.xxx.slide_47",
  "deck_id": "tpl.xxx",
  "section_id": "tpl.xxx.sec.05",
  "source_owner": "library",
  "score": 0.88,
  "confidence": 0.88,
  "match_reason": "整体算法流程图直接对齐 aspect a1+a2,文字含 SpeculativeDecoding 全流程",
  "covered_aspects": [
    "a1: 投机解码算法整体框架与流程",
    "a2: draft model 与 verify model 的协作机制"
  ],
  "residual_gap": [
    "a3: 接受率公式与数学推导",
    "a4: FlashAttention/Medusa baseline 性能对比",
    "a5: 适用边界与典型部署场景"
  ],
  "parts_to_reuse": "左侧 draft-verify 流程框图 + 右上模型协作示意",
  "parts_to_drop": "底部老的 throughput 数字",
  "relation_to_others": "本候选给框架; rank-2 将补公式/数据/边界",
  "recommended_reuse_mode": "partial_slide_reuse",
  "must_rewrite": ["数据标签", "公司 logo"],
  "gap_explanation": ""
}
```

## Hard Rules

### 🚫 NEVER

- 严禁仅因 salient_visuals / template_svg 相似而选源
- 严禁选 do_not_reuse_when 列表里的场景命中的 candidate
- 严禁为了 ADJACENCY 而选语义不对题的 candidate
  (ADJACENCY 只在多个候选**语义对齐度相同**时启用)

### ✅ MUST

- `covered_aspects` 必须用 aspect_id + 简短摘要 (≤30 字), 不能空
- `residual_gap` 必须列 target_aspects 中**未被本候选覆盖**的 aspect_ids
- 若 candidate 强对题 (score >= 0.85) 且覆盖 100% aspects, `residual_gap=[]`
- 若**所有** candidates 的最高 score < 0.5: 不要硬选, 输出 `candidates: []` +
  plan_note 说"无内容对题的候选"
- `gap_explanation`: 仅当 score < 0.70 时**必填** (≤120 字), 说明为何选这个但
  内容还不够,需要用户重写哪些部分

### 评分标准 (score 0.0-1.0)

- 0.95: 完美对题 + 视觉对齐 + 数据可直接复用 (罕见)
- 0.85: 完整覆盖核心 aspect, 文字需轻改
- 0.75: 覆盖 60-80% aspect, 多处需重写
- 0.65: 覆盖核心 1 个 aspect, 主要靠版式
- 0.55: 弱对题, 仅作"参考类型版式"
- < 0.50: 不应选

## Length budget

- `match_reason`: ≤ 60 字
- `parts_to_reuse`: ≤ 80 字
- `parts_to_drop`: ≤ 80 字
- `relation_to_others`: ≤ 60 字
- `gap_explanation`: ≤ 120 字 (score<0.70 时必填)
