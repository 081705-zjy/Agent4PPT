# Slide Aspect Extraction Skill

## Purpose

把每个 target page 拆成 ≤5 个 **aspects (维度/子点)** — 每个 aspect 是一个
可以独立判断"被某个 source candidate 是否覆盖"的内容单元。

这是 SLIDE_MATCHING 的第一步,产出给 rank-1 + gap-based rank-2/3 用。

## Inputs (per target page)

```json
{
  "target_slide_index": 12,
  "target_role": "method",
  "target_title": "投机解码原理",
  "target_claim": "...",
  "key_points": ["...", "..."],
  "needed_evidence": ["...", "..."],
  "anchor_terms": ["..."]
}
```

## Output

每个 target page 拆出一个 `aspects` 数组,长度 1-5:

```json
{
  "aspects": [
    {
      "aspect_id": "a1",
      "aspect_text": "投机解码算法整体框架与流程",
      "aspect_type": "method"
    },
    {
      "aspect_id": "a2",
      "aspect_text": "draft model 与 verify model 的协作机制",
      "aspect_type": "method"
    },
    {
      "aspect_id": "a3",
      "aspect_text": "接受率公式与数学推导",
      "aspect_type": "claim"
    },
    {
      "aspect_id": "a4",
      "aspect_text": "FlashAttention/Medusa 等 baseline 性能对比数据",
      "aspect_type": "data"
    },
    {
      "aspect_id": "a5",
      "aspect_text": "适用边界与典型部署场景",
      "aspect_type": "context"
    }
  ]
}
```

## Aspect 拆分规则

1. **数量 1-5**:
   - 结构页 (cover/agenda/section_divider/closing/references): 通常 1-2 个
   - 简单内容页 (motivation/background): 2-3 个
   - 复杂内容页 (method/result/comparison): 3-5 个
2. **每个 aspect 独立可判断**: 一个 source candidate 看完后能明确回答
   "覆盖了 / 没覆盖了 / 部分覆盖"
3. **不要互相重叠**: aspect 1 和 aspect 2 不能是同一件事的两个表述
4. **优先从 key_points 与 needed_evidence 中提取**: 这两个字段本来就是 page-level
   atomic content points
5. **`aspect_type` 5 类**:
   - `claim`: 一个待论证的核心判断 / 主张
   - `method`: 一种方法/算法/系统的描述
   - `data`: 一组具体数据/指标/对比
   - `evidence`: 支撑某 claim 的证据/案例
   - `context`: 背景/边界/适用场景

## Aspect 文本规则

- `aspect_text` 是 **可被 source candidate 评估** 的文字描述(≤30 字)
- 避免抽象套话 (如"研究方向定位" — 太空泛)
- 避免过度具体 (如"SpecEE 4.2× 加速" — 这是某个具体数据点而非一个 aspect)
- 例子:
  - ✅ "投机解码算法整体框架与流程"
  - ✅ "KV Cache 显存随上下文长度线性膨胀的问题"
  - ❌ "讲清楚投机解码" (太空泛)
  - ❌ "SpecEE 在 4 张 A100 上的 4.2× 加速" (太具体)

## Hard rules

- 严格按 schema 输出
- aspect_id 用 a1/a2/a3... 编号
- 长度 1-5, 不可空
- 输出 strict JSON
