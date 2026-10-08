---
页标识: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_62"
所属章节: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.08"
所属deck: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716"
页序号: 62
源文件: "templates/本组论文与科研成果/ASP-DAC Tutorial   Sparse Acceleration for Artificial Intelligence Progress and Trends.pptx"
页面角色: "content_candidate"
标题: "大模型基础：Attention 计算流"
核心论断: "LLM 核心是 Attention 层的矩阵乘与掩码计算流"
本页讲什么: "介绍 LLM 的基础结构，重点讲 Attention 层的计算流：Linear 投影、Attention-mask、矩阵乘等步骤，为后续说明「注意力矩阵可稀疏化」以及访存痛点打下概念基础。"
关键文字: "[Introduction to LLM, Attention layer Computational flow, Attention-mask, Liner]"
视觉骨架: "[Attention 计算流框图, 矩阵乘数据流示意]"
资源ID列表: "[tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_62.asset.01, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_62.asset.02, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_62.asset.03]"
适合复用场景: "[LLM Attention 结构基础介绍页, 稀疏方法前置的原理铺垫页]"
不适合复用场景: "[硬件能效对比页, 研究路线总览页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Introduction to LLM - Attention layer"}
  - {"位置": "下方主体", "内容": "Attention 计算流框图 (Linear 投影 + Attention-mask + 矩阵乘)"}
alternate_claims:
  - "Attention 计算由 Linear 投影与矩阵乘串联组成"
  - "Attention-mask 是控制注意力范围的关键步骤"
layout_tag: "block_diagram"
---
# slide 62: 大模型基础：Attention 计算流

**核心论断**: LLM 核心是 Attention 层的矩阵乘与掩码计算流

## 本页讲什么
介绍 LLM 的基础结构，重点讲 Attention 层的计算流：Linear 投影、Attention-mask、矩阵乘等步骤，为后续说明「注意力矩阵可稀疏化」以及访存痛点打下概念基础。

## 关键文字片段
- Introduction to LLM
- Attention layer Computational flow
- Attention-mask
- Liner

## 视觉骨架
- Attention 计算流框图
- 矩阵乘数据流示意

## 可复用到
- LLM Attention 结构基础介绍页
- 稀疏方法前置的原理铺垫页

## 不适合复用的场景
- 硬件能效对比页
- 研究路线总览页
