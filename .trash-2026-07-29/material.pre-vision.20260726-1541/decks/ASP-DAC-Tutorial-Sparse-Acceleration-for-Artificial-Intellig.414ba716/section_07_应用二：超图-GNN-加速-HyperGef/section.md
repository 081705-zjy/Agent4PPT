---
章节标识: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.07
所属deck: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716
章节序号: 7
章节角色: case_study
标题: 应用二：超图 GNN 加速 HyperGef
页码范围: [49, 57]
页数: 9
页ID列表: [slide_49, slide_50, slide_51, slide_52, slide_53, slide_54, slide_55, slide_56, slide_57]
章节叙事: 作为第二个应用案例，承接稀疏算子/点云范式，把稀疏加速落到超图 GNN 场景；内部由 HyperGef 论文引入，展开问题、融合框架、GPU 优化，收束到加速效果。
页间关系: ["slide 49 → slide 50: 由 HyperGef 论文封面页切入具体 HyperGNN 应用问题", "slide 50 → slide 51: 由 HyperGNN 场景引入其计算特征与稀疏瓶颈", "slide 51 → slide 52: 由问题瓶颈过渡到 HyperGef 融合加速思路", "slide 52 → slide 53: 由整体框架深入到具体 GPU 融合/调度设计", "slide 53 → slide 54: 由方法细节收束到该应用的阶段性小节页", "slide 54 → slide 55: 由小节页展开加速实验与对比", "slide 55 → slide 56: 由实验结果延伸到进一步分析或消融", "slide 56 → slide 57: 由分析收尾过渡到本案例结束/页码衔接下一章"]
适合复用场景: [介绍图/超图 GNN 的 GPU 融合加速案例, 需要「算子融合减少访存」类优化的 case_study, 稀疏加速在图学习场景的落地示例, 论文级单点工作深度展开的案例章]
不适合复用场景: [研究主题与图/超图神经网络无关时, 无 GPU/算子级优化的高层综述, 缺少 HyperGef 实验数据支撑时, 受众不熟悉 GNN 基础概念时]
在deck中的位置: 第 7 章 case_study，紧跟应用一，为后续大模型稀疏推理案例铺垫
分析状态: claude-opus-4-8
---

# section 7: 应用二：超图 GNN 加速 HyperGef

## 在 deck 中的位置
第 7 章 case_study，紧跟应用一，为后续大模型稀疏推理案例铺垫

## 章内 slide 间的关系
- slide 49 → slide 50: 由 HyperGef 论文封面页切入具体 HyperGNN 应用问题
- slide 50 → slide 51: 由 HyperGNN 场景引入其计算特征与稀疏瓶颈
- slide 51 → slide 52: 由问题瓶颈过渡到 HyperGef 融合加速思路
- slide 52 → slide 53: 由整体框架深入到具体 GPU 融合/调度设计
- slide 53 → slide 54: 由方法细节收束到该应用的阶段性小节页
- slide 54 → slide 55: 由小节页展开加速实验与对比
- slide 55 → slide 56: 由实验结果延伸到进一步分析或消融
- slide 56 → slide 57: 由分析收尾过渡到本案例结束/页码衔接下一章

## 整章可复用的场景
- 介绍图/超图 GNN 的 GPU 融合加速案例
- 需要「算子融合减少访存」类优化的 case_study
- 稀疏加速在图学习场景的落地示例
- 论文级单点工作深度展开的案例章

## 不适合复用的场景
- 研究主题与图/超图神经网络无关时
- 无 GPU/算子级优化的高层综述
- 缺少 HyperGef 实验数据支撑时
- 受众不熟悉 GNN 基础概念时
