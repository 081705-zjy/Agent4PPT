---
章节标识: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.05
所属deck: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19
章节序号: 5
章节角色: method
标题: "稀疏计算与FPGA加速:FlightLLM"
页码范围: [24, 32]
页数: 9
页ID列表: [slide_24, slide_25, slide_26, slide_27, slide_28, slide_29, slide_30, slide_31, slide_32]
章节叙事: "承接算子加速后，本章下沉到硬件层：从摩尔定律放缓的算力困境切入，论证稀疏计算的必要性，再落到灵活N:M稀疏+Sparse DSP的FPGA方案，用FlightLLM实测超越GPU收束。"
页间关系: ["slide 24 → slide 25: 由背景总述过渡到乘法器利用率上限这一硬件度量", "slide 25 → slide 26: 由利用率指标引出摩尔定律放缓的算力瓶颈", "slide 26 → slide 27: 由算力放缓的困境转向稀疏计算这一破局思路", "slide 27 → slide 28: 由稀疏概念展开到Dense转Sparse的具体路径", "slide 28 → slide 29: 由通用稀疏路径收窄到灵活N:M稀疏方案", "slide 29 → slide 30: 由N:M稀疏的key idea落到Sparse DSP Chain硬件实现", "slide 30 → slide 31: 由DSP架构支撑转入FlightLLM实测性能对比", "slide 31 → slide 32: 由超越GPU的量化结果收束到U280实机Demo"]
适合复用场景: [论证摩尔定律放缓需转向稀疏计算的硬件章节, FPGA/专用芯片加速大模型的method章节, 需从「问题动机→稀疏思路→硬件方案→实测」完整闭环的章节, "N:M稀疏或稀疏attention/linear层加速的技术介绍", 以「超越GPU」实测结论收尾的硬件工作展示]
不适合复用场景: [仅讲算子/软件层加速、不涉及硬件的章节, 无FPGA/专用硬件对比数据支撑时, 受众对稀疏与量化基础概念完全陌生时, 研究主题与大模型推理加速无关时, 无法提供实机Demo或实测对比的场合]
在deck中的位置: 第5章method，紧接FlashDecoding++算子章，代表稀疏加速的硬件层
分析状态: claude-opus-4-8
---

# section 5: 稀疏计算与FPGA加速:FlightLLM

## 在 deck 中的位置
第5章method，紧接FlashDecoding++算子章，代表稀疏加速的硬件层

## 章内 slide 间的关系
- slide 24 → slide 25: 由背景总述过渡到乘法器利用率上限这一硬件度量
- slide 25 → slide 26: 由利用率指标引出摩尔定律放缓的算力瓶颈
- slide 26 → slide 27: 由算力放缓的困境转向稀疏计算这一破局思路
- slide 27 → slide 28: 由稀疏概念展开到Dense转Sparse的具体路径
- slide 28 → slide 29: 由通用稀疏路径收窄到灵活N:M稀疏方案
- slide 29 → slide 30: 由N:M稀疏的key idea落到Sparse DSP Chain硬件实现
- slide 30 → slide 31: 由DSP架构支撑转入FlightLLM实测性能对比
- slide 31 → slide 32: 由超越GPU的量化结果收束到U280实机Demo

## 整章可复用的场景
- 论证摩尔定律放缓需转向稀疏计算的硬件章节
- FPGA/专用芯片加速大模型的method章节
- 需从「问题动机→稀疏思路→硬件方案→实测」完整闭环的章节
- N:M稀疏或稀疏attention/linear层加速的技术介绍
- 以「超越GPU」实测结论收尾的硬件工作展示

## 不适合复用的场景
- 仅讲算子/软件层加速、不涉及硬件的章节
- 无FPGA/专用硬件对比数据支撑时
- 受众对稀疏与量化基础概念完全陌生时
- 研究主题与大模型推理加速无关时
- 无法提供实机Demo或实测对比的场合
