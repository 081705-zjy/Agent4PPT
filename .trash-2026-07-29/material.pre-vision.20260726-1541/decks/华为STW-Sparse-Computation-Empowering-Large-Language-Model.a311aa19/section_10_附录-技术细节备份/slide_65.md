---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_65"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 65
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "MoE 原理:Sparse MoE Layers"
核心论断: "MoE 以稀疏专家层扩大参数规模而不增等比算力"
本页讲什么: "速查 MoE 原理,以 Switch Transformers 为例说明稀疏 MoE 层的结构:每个 token 仅路由到部分专家,从而在扩大模型容量的同时保持稀疏计算。"
关键文字: "[MoE, Switch Transformers, Sparse MoE layers]"
视觉骨架: "[Sparse MoE 层结构图, 专家路由示意]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_65.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_65.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_65.asset.03]"
适合复用场景: "[MoE 原理速查介绍页, 稀疏专家结构展开]"
不适合复用场景: "[softmax 优化机制页, 结果加速数据页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "MoE 原理:Sparse MoE Layers"}
  - {"位置": "下方主体", "内容": "Sparse MoE 层结构图与专家路由示意"}
alternate_claims:
  - "每个 token 仅路由到少数专家实现稀疏激活"
layout_tag: "block_diagram"
---
# slide 65: MoE 原理:Sparse MoE Layers

**核心论断**: MoE 以稀疏专家层扩大参数规模而不增等比算力

## 本页讲什么
速查 MoE 原理,以 Switch Transformers 为例说明稀疏 MoE 层的结构:每个 token 仅路由到部分专家,从而在扩大模型容量的同时保持稀疏计算。

## 关键文字片段
- MoE
- Switch Transformers
- Sparse MoE layers

## 视觉骨架
- Sparse MoE 层结构图
- 专家路由示意

## 可复用到
- MoE 原理速查介绍页
- 稀疏专家结构展开

## 不适合复用的场景
- softmax 优化机制页
- 结果加速数据页
