---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_40"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.07"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 40
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "新范式之一：混合专家 MoE"
核心论断: "MoE 以宽度稀疏——按需激活部分专家——扩容而不增推理算力"
本页讲什么: "承接上页对 Transformer 的重思，引出第一条稀疏化路线：Mixture of Experts。用多专家 + 路由的结构图说明 MoE 在宽度维度上稀疏——每个 token 只激活少数专家，从而在扩大参数规模的同时不成比例增加计算量。"
关键文字: "[New Model Paradigm — Mixture of Experts]"
视觉骨架: "[多专家 + 路由结构图, 宽度稀疏激活示意]"
资源ID列表:
适合复用场景: "[MoE 模型范式介绍页, 宽度稀疏专家路由讲解页]"
不适合复用场景: "[MoD 深度稀疏主题页, 硬件层能效对比页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方标题", "内容": "新范式之一：混合专家 MoE"}
  - {"位置": "下方主体", "内容": "多专家 + 路由结构图, 宽度稀疏激活示意"}
alternate_claims:
  - "每个 token 仅激活少数专家实现宽度稀疏"
layout_tag: "block_diagram"
---
# slide 40: 新范式之一：混合专家 MoE

**核心论断**: MoE 以宽度稀疏——按需激活部分专家——扩容而不增推理算力

## 本页讲什么
承接上页对 Transformer 的重思，引出第一条稀疏化路线：Mixture of Experts。用多专家 + 路由的结构图说明 MoE 在宽度维度上稀疏——每个 token 只激活少数专家，从而在扩大参数规模的同时不成比例增加计算量。

## 关键文字片段
- New Model Paradigm — Mixture of Experts

## 视觉骨架
- 多专家 + 路由结构图
- 宽度稀疏激活示意

## 可复用到
- MoE 模型范式介绍页
- 宽度稀疏专家路由讲解页

## 不适合复用的场景
- MoD 深度稀疏主题页
- 硬件层能效对比页
