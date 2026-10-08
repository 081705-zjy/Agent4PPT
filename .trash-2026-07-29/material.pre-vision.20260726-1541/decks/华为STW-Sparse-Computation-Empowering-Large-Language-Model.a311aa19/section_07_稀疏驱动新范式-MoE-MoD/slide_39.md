---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_39"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.07"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 39
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "重思 Transformer：迈向稀疏范式"
核心论断: "标准 Transformer 存在稠密冗余，需从范式层重构以引入稀疏"
本页讲什么: "作为本章开篇，从重新审视 Transformer 结构切入：前面已在算子与硬件层做稀疏加速，本页把视角上升到模型范式层，指出稠密 Transformer 的计算冗余，为后续 MoE（宽度稀疏）与 MoD（深度稀疏）两条稀疏化路线做铺垫。"
关键文字: "[Rethink Transformer]"
视觉骨架: "[Transformer 结构块图, 稀疏化切入点标注]"
资源ID列表:
适合复用场景: "[模型范式重构章节开篇页, Transformer 稀疏化引入页]"
不适合复用场景: "[具体算子层实现页, 含 benchmark 数字的结果页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "opener"
视觉文本层次:
alternate_claims:
layout_tag: "block_diagram"
---
# slide 39: 重思 Transformer：迈向稀疏范式

**核心论断**: 标准 Transformer 存在稠密冗余，需从范式层重构以引入稀疏

## 本页讲什么
作为本章开篇，从重新审视 Transformer 结构切入：前面已在算子与硬件层做稀疏加速，本页把视角上升到模型范式层，指出稠密 Transformer 的计算冗余，为后续 MoE（宽度稀疏）与 MoD（深度稀疏）两条稀疏化路线做铺垫。

## 关键文字片段
- Rethink Transformer

## 视觉骨架
- Transformer 结构块图
- 稀疏化切入点标注

## 可复用到
- 模型范式重构章节开篇页
- Transformer 稀疏化引入页

## 不适合复用的场景
- 具体算子层实现页
- 含 benchmark 数字的结果页
