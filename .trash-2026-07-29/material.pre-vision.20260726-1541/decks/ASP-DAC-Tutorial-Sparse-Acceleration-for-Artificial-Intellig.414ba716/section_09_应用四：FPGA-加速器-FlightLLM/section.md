---
章节标识: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.09
所属deck: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716
章节序号: 9
章节角色: case_study
标题: 应用四：FPGA 加速器 FlightLLM
页码范围: [78, 88]
页数: 11
页ID列表: [slide_78, slide_79, slide_80, slide_81, slide_82, slide_83, slide_84, slide_85, slide_86, slide_87, slide_88]
章节叙事: 作为第四个代表性工作案例，用完整论文叙事弧（背景→动机→挑战→双方案→结果）展示 FPGA 上端到端稀疏 LLM 推理落地，为「稀疏提升等效算力」提供硬件加速器实证。
页间关系: ["slide 78 → slide 79: 由论文标题/署名过渡到 N:M 灵活稀疏背景", "slide 79 → slide 80: 由稀疏背景引出与 GPU 对比的 motivation", "slide 80 → slide 81: 由动机收敛到待解的三大 challenges", "slide 81 → slide 82: 由挑战切入 Solution 1 稀疏 DSP 链", "slide 82 → slide 83: 由 DSP 链原理展开其对 N:M 与块稀疏的支持", "slide 83 → slide 84: 由方案一转入 Solution 2 全芯片解码方案", "slide 84 → slide 85: 由解码带宽方案引出指令复用优化", "slide 85 → slide 86: 由方法收束到与加速器对比的结果", "slide 86 → slide 87: 由加速器对比延伸到与 LLM 方案对比结果", "slide 87 → slide 88: 由实验结果收束到本案例小结页"]
适合复用场景: [论文式硬件工作的完整案例讲解章节, 需展示 FPGA/加速器端到端映射流程的技术汇报, 论证稀疏模式与硬件利用率协同的案例, 背景→挑战→多方案→结果的标准工作汇报弧]
不适合复用场景: [无硬件/加速器内容的纯算法汇报, 只需单页结论、不展开论文细节时, "非 N:M/块稀疏相关的稀疏主题", FlightLLM 数据已被后续工作超越时]
在deck中的位置: 第 9 章，位于四个应用案例之末，紧跟大模型稀疏推理，后接 FlashDecoding++
分析状态: claude-opus-4-8
---

# section 9: 应用四：FPGA 加速器 FlightLLM

## 在 deck 中的位置
第 9 章，位于四个应用案例之末，紧跟大模型稀疏推理，后接 FlashDecoding++

## 章内 slide 间的关系
- slide 78 → slide 79: 由论文标题/署名过渡到 N:M 灵活稀疏背景
- slide 79 → slide 80: 由稀疏背景引出与 GPU 对比的 motivation
- slide 80 → slide 81: 由动机收敛到待解的三大 challenges
- slide 81 → slide 82: 由挑战切入 Solution 1 稀疏 DSP 链
- slide 82 → slide 83: 由 DSP 链原理展开其对 N:M 与块稀疏的支持
- slide 83 → slide 84: 由方案一转入 Solution 2 全芯片解码方案
- slide 84 → slide 85: 由解码带宽方案引出指令复用优化
- slide 85 → slide 86: 由方法收束到与加速器对比的结果
- slide 86 → slide 87: 由加速器对比延伸到与 LLM 方案对比结果
- slide 87 → slide 88: 由实验结果收束到本案例小结页

## 整章可复用的场景
- 论文式硬件工作的完整案例讲解章节
- 需展示 FPGA/加速器端到端映射流程的技术汇报
- 论证稀疏模式与硬件利用率协同的案例
- 背景→挑战→多方案→结果的标准工作汇报弧

## 不适合复用的场景
- 无硬件/加速器内容的纯算法汇报
- 只需单页结论、不展开论文细节时
- 非 N:M/块稀疏相关的稀疏主题
- FlightLLM 数据已被后续工作超越时
