---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_44"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.08"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 44
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "新基础模型愿景延展"
核心论断: "稠密 GEMM 主导的训练范式需引入稀疏化"
本页讲什么: "延续上页愿景,进一步铺陈「带稀疏的新基础模型」的动机:LLM 在 GPU 上以稠密 GEMM 为主要计算负载,本页把这一现状展开成问题陈述,引出后续用 N:M 稀疏改造训练流程的必要性,是 opener 的第二幕。"
关键文字: "[New Foundation Model with Sparsity, LLMs 运行于 GPUs(NVIDIA, AMD), 以 GEMMs 为主要计算]"
视觉骨架: "[LLM-GPU-GEMM 关系框图, 问题陈述文字块]"
资源ID列表:
适合复用场景: "[稀疏基础模型动机延展页, 训练范式问题铺陈页]"
不适合复用场景: "[单一数据结果页, 方法架构细节页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "opener"
视觉文本层次:
  - {"位置": "上方标题", "内容": "New Foundation Model with Sparsity"}
  - {"位置": "下方主体", "内容": "LLM-GPU-GEMM 关系框图与问题陈述"}
alternate_claims:
  - "LLM 训练主要跑在 NVIDIA/AMD GPU 上"
  - "GEMM 是当前 LLM 计算负载的核心"
layout_tag: "block_diagram"
---
# slide 44: 新基础模型愿景延展

**核心论断**: 稠密 GEMM 主导的训练范式需引入稀疏化

## 本页讲什么
延续上页愿景,进一步铺陈「带稀疏的新基础模型」的动机:LLM 在 GPU 上以稠密 GEMM 为主要计算负载,本页把这一现状展开成问题陈述,引出后续用 N:M 稀疏改造训练流程的必要性,是 opener 的第二幕。

## 关键文字片段
- New Foundation Model with Sparsity
- LLMs 运行于 GPUs(NVIDIA, AMD)
- 以 GEMMs 为主要计算

## 视觉骨架
- LLM-GPU-GEMM 关系框图
- 问题陈述文字块

## 可复用到
- 稀疏基础模型动机延展页
- 训练范式问题铺陈页

## 不适合复用的场景
- 单一数据结果页
- 方法架构细节页
