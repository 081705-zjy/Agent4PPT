---
页标识: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16"
所属章节: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.sec.03"
所属deck: "tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274"
页序号: 16
源文件: "templates/本组论文与科研成果/SpAct-NDP Efficient LLM Inference via Sparse.pptx"
页面角色: "content_candidate"
标题: "预测掩码驱动动态 DRAM 访问"
核心论断: "预测掩码依赖关系动态触发按需 DRAM 访问"
本页讲什么: "展开第二大组件掩码预测，说明 Predicted Mask 及其依赖关系如何驱动 Dynamic DRAM Access，仅按预测的稀疏模式访问所需数据，从而削减冗余访存，承接上页映射、引向下页调度。"
关键文字: "[Predicted Mask, Dependent, Dynamic DRAM Access]"
视觉骨架: "[掩码预测流程框图, DRAM 访问路径示意, 依赖关系箭头]"
资源ID列表: "[tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.01, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.02, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.03, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.04, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.05, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.06, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.07, tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.slide_16.asset.08]"
适合复用场景: "[掩码预测机制方法页, 动态按需访存详解页]"
不适合复用场景: "[纯结果数据页, 章节导览列表页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方", "内容": "Predicted Mask 掩码预测流程框图"}
  - {"位置": "下方", "内容": "Dynamic DRAM Access 访问路径与依赖箭头"}
alternate_claims:
  - "按预测稀疏模式访存可显著削减冗余 DRAM 读取"
layout_tag: "block_diagram"
---
# slide 16: 预测掩码驱动动态 DRAM 访问

**核心论断**: 预测掩码依赖关系动态触发按需 DRAM 访问

## 本页讲什么
展开第二大组件掩码预测，说明 Predicted Mask 及其依赖关系如何驱动 Dynamic DRAM Access，仅按预测的稀疏模式访问所需数据，从而削减冗余访存，承接上页映射、引向下页调度。

## 关键文字片段
- Predicted Mask
- Dependent
- Dynamic DRAM Access

## 视觉骨架
- 掩码预测流程框图
- DRAM 访问路径示意
- 依赖关系箭头

## 可复用到
- 掩码预测机制方法页
- 动态按需访存详解页

## 不适合复用的场景
- 纯结果数据页
- 章节导览列表页
