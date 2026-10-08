---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_43"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.08"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 43
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "面向稀疏的新基础模型愿景"
核心论断: "稀疏应从算子/硬件上推到基础模型训练层"
本页讲什么: "本页作为收官 method 章的开篇,立起「带稀疏的新基础模型」这一愿景:当前 LLM 训练严重依赖 GPU(NVIDIA/AMD)上的稠密 GEMM,而稀疏计算应从算子和硬件层进一步上升到基础模型本身,为后续 N:M 稀疏训练与 TB-STC 铺垫问题背景。"
关键文字: "[New Foundation Model with Sparsity, LLMs 依赖 GPUs(NVIDIA, AMD), 以 GEMMs 为核心算子]"
视觉骨架: "[LLM-GPU-GEMM 关系框图, 新基础模型愿景标题块]"
资源ID列表:
适合复用场景: "[稀疏基础模型章节 opener, 大模型训练算力问题引入页]"
不适合复用场景: "[具体算子实现细节页, 含 benchmark 数字的结果页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "opener"
视觉文本层次:
  - {"位置": "上方标题块", "内容": "New Foundation Model with Sparsity 愿景标题"}
  - {"位置": "下方主体", "内容": "LLMs-GPUs(NVIDIA/AMD)-GEMMs 关系框图"}
alternate_claims:
  - "当前 LLM 训练严重依赖 GPU 上的稠密 GEMM 算子"
layout_tag: "block_diagram"
---
# slide 43: 面向稀疏的新基础模型愿景

**核心论断**: 稀疏应从算子/硬件上推到基础模型训练层

## 本页讲什么
本页作为收官 method 章的开篇,立起「带稀疏的新基础模型」这一愿景:当前 LLM 训练严重依赖 GPU(NVIDIA/AMD)上的稠密 GEMM,而稀疏计算应从算子和硬件层进一步上升到基础模型本身,为后续 N:M 稀疏训练与 TB-STC 铺垫问题背景。

## 关键文字片段
- New Foundation Model with Sparsity
- LLMs 依赖 GPUs(NVIDIA, AMD)
- 以 GEMMs 为核心算子

## 视觉骨架
- LLM-GPU-GEMM 关系框图
- 新基础模型愿景标题块

## 可复用到
- 稀疏基础模型章节 opener
- 大模型训练算力问题引入页

## 不适合复用的场景
- 具体算子实现细节页
- 含 benchmark 数字的结果页
