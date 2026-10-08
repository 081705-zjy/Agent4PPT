---
章节标识: tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.sec.03
所属deck: tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274
章节序号: 3
章节角色: method
标题: 稀疏激活近数据处理流水线
页码范围: [10, 19]
页数: 10
页ID列表: [slide_10, slide_11, slide_12, slide_13, slide_14, slide_15, slide_16, slide_17, slide_18, slide_19]
章节叙事: deck 核心方法章，承接背景挑战，逐层铺开 SpAct-NDP 流水线：先给整体架构与原始 LLM 对比，再依次落地稀疏感知权重映射、掩码预测、离线在线启发式调度三大组件。
页间关系: ["slide 10 → slide 11: 由稀疏激活流水线总览过渡到与 Original LLM 的结构对比", "slide 11 → slide 12: 由结构对比引出该设计要解决的 background 与 challenge", "slide 12 → slide 13: 由挑战切入第一个组件——稀疏感知权重映射策略", "slide 13 → slide 14: 由权重映射过渡到 Step2 的稀疏激活计算", "slide 14 → slide 15: 展开稀疏激活内部 K/1 稀疏感知细节", "slide 15 → slide 16: 由稀疏计算引出其依赖的预测掩码机制", "slide 16 → slide 17: 由掩码预测过渡到离线在线启发式调度系统", "slide 17 → slide 18: 由调度目标过渡到预测稀疏模式的具体运用", "slide 18 → slide 19: 由稀疏模式落到 Pair(~50KB) 数据粒度与实现细节"]
适合复用场景: [需分层拆解「算法+硬件协同」流水线的 method 章, 含权重映射/掩码预测/调度多组件的方法章, 近数据处理或稀疏计算类系统方法论述, 需先对比 baseline 再逐组件展开的方法章]
不适合复用场景: [方法只有单一组件、无需分层展开时, 研究与稀疏激活/近数据处理无关时, 无 baseline 结构可供对比时, 方法偏纯算法、无硬件调度环节时]
在deck中的位置: 第 3 章方法主体，前接背景章，后接实验章
分析状态: claude-opus-4-8
---

# section 3: 稀疏激活近数据处理流水线

## 在 deck 中的位置
第 3 章方法主体，前接背景章，后接实验章

## 章内 slide 间的关系
- slide 10 → slide 11: 由稀疏激活流水线总览过渡到与 Original LLM 的结构对比
- slide 11 → slide 12: 由结构对比引出该设计要解决的 background 与 challenge
- slide 12 → slide 13: 由挑战切入第一个组件——稀疏感知权重映射策略
- slide 13 → slide 14: 由权重映射过渡到 Step2 的稀疏激活计算
- slide 14 → slide 15: 展开稀疏激活内部 K/1 稀疏感知细节
- slide 15 → slide 16: 由稀疏计算引出其依赖的预测掩码机制
- slide 16 → slide 17: 由掩码预测过渡到离线在线启发式调度系统
- slide 17 → slide 18: 由调度目标过渡到预测稀疏模式的具体运用
- slide 18 → slide 19: 由稀疏模式落到 Pair(~50KB) 数据粒度与实现细节

## 整章可复用的场景
- 需分层拆解「算法+硬件协同」流水线的 method 章
- 含权重映射/掩码预测/调度多组件的方法章
- 近数据处理或稀疏计算类系统方法论述
- 需先对比 baseline 再逐组件展开的方法章

## 不适合复用的场景
- 方法只有单一组件、无需分层展开时
- 研究与稀疏激活/近数据处理无关时
- 无 baseline 结构可供对比时
- 方法偏纯算法、无硬件调度环节时
