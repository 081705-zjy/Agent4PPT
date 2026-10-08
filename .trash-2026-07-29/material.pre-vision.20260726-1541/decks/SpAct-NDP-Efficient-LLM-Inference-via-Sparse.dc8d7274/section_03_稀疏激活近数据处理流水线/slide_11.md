---
页标识: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11"
所属章节: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.sec.03"
所属deck: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274"
页序号: 11
源文件: "templates/本组论文与科研成果/SpAct-NDP Efficient LLM Inference via Sparse.pptx"
页面角色: "content_candidate"
标题: "原始 LLM 流水线与稀疏激活对比"
核心论断: "稀疏激活流水线相较原始 LLM 削减冗余计算与访存"
本页讲什么: "承接总览页，把 Original LLM Pipeline 与稀疏激活版本并置对比，逐阶段呈现两者在 Data 加载与计算路径上的差异，凸显稀疏激活对流水线的改造点，为下页引出背景与挑战做铺垫。"
关键文字: "[LLM Pipeline with Sparse Activation, Original LLM Pipeline, Data]"
视觉骨架: "[双流水线并置对比图, 原始 vs 稀疏分栏, 阶段对应箭头]"
资源ID列表: "[tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.01, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.02, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.03, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.04, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.05, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.06, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.07, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.08, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.09, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_11.asset.10]"
适合复用场景: "[方案与基线流水线对比页, 推理架构改造前后对照]"
不适合复用场景: "[纯文字总结页, 单一方案独立展示页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方", "内容": "Original LLM Pipeline 流水线图"}
  - {"位置": "下方", "内容": "LLM Pipeline with Sparse Activation 流水线图"}
alternate_claims:
  - "原始与稀疏版本在 Data 加载阶段路径存在差异"
layout_tag: "block_diagram"
---
# slide 11: 原始 LLM 流水线与稀疏激活对比

**核心论断**: 稀疏激活流水线相较原始 LLM 削减冗余计算与访存

## 本页讲什么
承接总览页，把 Original LLM Pipeline 与稀疏激活版本并置对比，逐阶段呈现两者在 Data 加载与计算路径上的差异，凸显稀疏激活对流水线的改造点，为下页引出背景与挑战做铺垫。

## 关键文字片段
- LLM Pipeline with Sparse Activation
- Original LLM Pipeline
- Data

## 视觉骨架
- 双流水线并置对比图
- 原始 vs 稀疏分栏
- 阶段对应箭头

## 可复用到
- 方案与基线流水线对比页
- 推理架构改造前后对照

## 不适合复用的场景
- 纯文字总结页
- 单一方案独立展示页
