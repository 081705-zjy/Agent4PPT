# Draft Annotation Summary Skill

## Purpose

为 deck 中每一页生成**右上角黄底框**的两行精炼标语:
- `objective`: 一句话归纳这页要做什么 / 讲什么 (≤14 字)
- `gap_brief`: 一句话归纳这页需要补的关键 gap / 改写动作 (≤24 字)

这是给讲者快速 review 用的视觉锚点,**不是简单截断**,而是要**总结归纳**。

## Inputs

```json
{
  "slides": [
    {
      "slide_index": 1,
      "target_role": "cover",
      "target_title": "...",
      "target_claim": "...",
      "page_purpose": "...",
      "key_points": ["...", "..."],
      "gap_info": {
        "must_replace": ["..."],
        "must_add": ["..."],
        "evidence_needed": ["..."],
        "next_action": "..."
      }
    }
  ]
}
```

## Output Schema

```json
{
  "summaries": [
    {
      "slide_index": 1,
      "objective": "课题组多层次研究定位",
      "gap_brief": "替页标题+加六层标签"
    },
    {
      "slide_index": 25,
      "objective": "存储层 KV 优化效果",
      "gap_brief": "补吞吐 baseline 数据"
    }
  ]
}
```

## Hard Rules

### Objective (≤14 字)

- 一个名词性短语,描述本页的核心议题
- 不要动词开头 (不是 "讲清 X" 或 "展示 Y", 而是 "X 的 Y")
- 不要重复 target_title 整句; 是 target 的**精炼版**
- 删除虚词、连词、标点符号 (除了 "·" 和必要的 "/")

✅ 好的 objective:
- "课题组多层次研究定位"
- "推理时代系统压力来源"
- "存储层 KV 优化效果"
- "FlashOverlap 计算通信重叠"
- "工程实践无问芯穹案例"

❌ 不好的 objective:
- "让我们来看看课题组的研究" (口语化、动词开头)
- "目标: 课题组聚焦大模型推理时代的软硬件协同优化研究脉络以..." (太长 / 截断式)
- "本页" (空泛)

### Gap_brief (≤24 字)

- 一句话归纳"本页最需要补什么 / 改什么"
- 用紧凑动宾结构: "改X+Y · 加Z · 证W"
- 如果 must_replace + must_add + evidence_needed 都有, 选**最重要的 1-2 个**, 不要全列
- 没有显式 gap → "已就绪"

✅ 好的 gap_brief:
- "改标题+加六层标签"
- "补 vLLM 吞吐 baseline"
- "脱敏合作方+加性能数字"
- "已就绪"

❌ 不好的 gap_brief:
- "改:页标题（替换为课题组研究方向定位）; 原五层标签调整为算法/系统/算子/通信/硬件/芯片六层; 章节序号 0X" (列表式)
- "Gap: ..." (前缀冗余)
- "需要补充信息" (空泛)

### 输出要求

- `summaries` 数组长度 == 输入 slides 长度
- 必须按输入顺序输出 (用 slide_index 对应)
- strict JSON only

## Examples

输入 slide 10:
```json
{
  "slide_index": 10,
  "target_role": "problem",
  "target_title": "六类挑战总览",
  "target_claim": "推理系统压力可拆解为六类正交的瓶颈型挑战",
  "page_purpose": "把背景压力转化为可分析框架,为后续章节铺路",
  "key_points": ["六类挑战分类逻辑", "①~⑥编号锚点", "并列网格视觉版式"],
  "gap_info": {
    "must_replace": ["页标题改为推理压力六类挑战", "原四类受限扩展为六类"],
    "must_add": ["六类标签", "①~⑥编号"],
    "evidence_needed": []
  }
}
```

输出 objective: "六类挑战总览框架"
输出 gap_brief: "改四类为六类+加①~⑥编号"

输入 slide 28:
```json
{
  "slide_index": 28,
  "target_role": "result",
  "target_title": "semi-PD 性能对比",
  "target_claim": "semi-PD 在吞吐与延迟上同时优于现有 PD 分离方案",
  "page_purpose": "用数据收口 PD 分离 cluster 的性能优势",
  "key_points": ["semi-PD 系统设计要点", "vLLM/Mooncake 对比", "吞吐 + 延迟双指标"],
  "gap_info": {
    "must_replace": ["性能数字"],
    "must_add": ["延迟分布图"],
    "evidence_needed": ["同负载下 Mooncake/vLLM 对比数据"]
  }
}
```

输出 objective: "semi-PD 性能对比"
输出 gap_brief: "补 vLLM/Mooncake baseline 数据"
