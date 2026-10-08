---
章节标识: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.07
所属deck: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19
章节序号: 7
章节角色: method
标题: "稀疏驱动新范式:MoE/MoD"
页码范围: [39, 42]
页数: 4
页ID列表: [slide_39, slide_40, slide_41, slide_42]
章节叙事: 作为方法论收尾章,把前面算子/硬件层的稀疏加速上升到模型范式层。由重思Transformer切入,依次引出MoE(宽度稀疏)、MoD(深度稀疏),最终归纳稀疏驱动的新基础模型。
页间关系: ["slide 39 → slide 40: 由重思Transformer结构的总纲,切入宽度维度的MoE专家稀疏", "slide 40 → slide 41: 由专家宽度稀疏(MoE)平移到层深度稀疏(MoD)", "slide 41 → slide 42: 由MoE/MoD两个具体范式归纳出稀疏驱动新基础模型的总论"]
适合复用场景: [论证稀疏从算子/硬件上升到模型层的method收尾章, 并列介绍MoE与MoD两类稀疏范式的章节, 需从Transformer结构反思引出新范式的叙事]
不适合复用场景: [只讲单一稀疏范式无需并列对比时, 主题不涉及模型结构层稀疏(仅算子/硬件)时, 无前置算子/硬件铺垫的独立开篇章节]
在deck中的位置: 第7章(倒数),承接前面算子/硬件/领域三层加速,收束于模型层新范式。
分析状态: claude-opus-4-8
---

# section 7: 稀疏驱动新范式:MoE/MoD

## 在 deck 中的位置
第7章(倒数),承接前面算子/硬件/领域三层加速,收束于模型层新范式。

## 章内 slide 间的关系
- slide 39 → slide 40: 由重思Transformer结构的总纲,切入宽度维度的MoE专家稀疏
- slide 40 → slide 41: 由专家宽度稀疏(MoE)平移到层深度稀疏(MoD)
- slide 41 → slide 42: 由MoE/MoD两个具体范式归纳出稀疏驱动新基础模型的总论

## 整章可复用的场景
- 论证稀疏从算子/硬件上升到模型层的method收尾章
- 并列介绍MoE与MoD两类稀疏范式的章节
- 需从Transformer结构反思引出新范式的叙事

## 不适合复用的场景
- 只讲单一稀疏范式无需并列对比时
- 主题不涉及模型结构层稀疏(仅算子/硬件)时
- 无前置算子/硬件铺垫的独立开篇章节
