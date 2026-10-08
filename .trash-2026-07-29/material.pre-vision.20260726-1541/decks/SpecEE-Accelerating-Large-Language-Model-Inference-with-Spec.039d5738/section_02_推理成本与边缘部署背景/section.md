---
章节标识: tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.sec.02
所属deck: tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738
章节序号: 2
章节角色: motivation
标题: 推理成本与边缘部署背景
页码范围: [2, 5]
页数: 4
页ID列表: [slide_02, slide_03, slide_04, slide_05]
章节叙事: 为 SpecEE 方法做铺垫：先立推理成本与边缘部署两大压力，再收敛到「如何减少逐层计算」这一核心问题，引出后续投机早退方案。
页间关系: ["slide 2 → slide 3: 由 background/related work 总起过渡到 Agent 场景下 token 量级激增的成本压力", "slide 3 → slide 4: 由推理成本压力过渡到边缘推理引擎的部署约束", "slide 4 → slide 5: 由边缘算力受限收敛到「如何减少逐层计算」的核心问题"]
适合复用场景: [需论证「推理成本 + 边缘算力受限」双重压力的 motivation 章, 由通用背景收敛到单一技术问题的漏斗式铺垫, 面向 LLM 推理加速/层裁剪类工作的背景章]
不适合复用场景: [研究主题与 LLM 推理无关时, 无边缘/端侧部署约束的场景, 背景需展开多分支而非漏斗收敛时, Agent token 量级数据已过时]
在deck中的位置: 第 2 章 background，紧跟 cover，为方法章节铺垫。
分析状态: claude-opus-4-8
---

# section 2: 推理成本与边缘部署背景

## 在 deck 中的位置
第 2 章 background，紧跟 cover，为方法章节铺垫。

## 章内 slide 间的关系
- slide 2 → slide 3: 由 background/related work 总起过渡到 Agent 场景下 token 量级激增的成本压力
- slide 3 → slide 4: 由推理成本压力过渡到边缘推理引擎的部署约束
- slide 4 → slide 5: 由边缘算力受限收敛到「如何减少逐层计算」的核心问题

## 整章可复用的场景
- 需论证「推理成本 + 边缘算力受限」双重压力的 motivation 章
- 由通用背景收敛到单一技术问题的漏斗式铺垫
- 面向 LLM 推理加速/层裁剪类工作的背景章

## 不适合复用的场景
- 研究主题与 LLM 推理无关时
- 无边缘/端侧部署约束的场景
- 背景需展开多分支而非漏斗收敛时
- Agent token 量级数据已过时
