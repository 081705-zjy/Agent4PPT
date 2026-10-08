---
页标识: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_11"
所属章节: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.03"
所属deck: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716"
页序号: 11
源文件: "templates/本组论文与科研成果/ASP-DAC Tutorial   Sparse Acceleration for Artificial Intelligence Progress and Trends.pptx"
页面角色: "content_candidate"
标题: "稀疏计算流：内积与行式数据流"
核心论断: "内积与行式是 SpMM 稀疏计算流的两类基本数据流"
本页讲什么: "承接上页的 SpMM 算子，进一步拆解其数据流组织方式：介绍内积 (Inner product) 与行式 (Row-based) 两类数据流。讲者可对比二者在数据访问与并行方式上的差异，说明不同数据流决定了稀疏硬件的取数与计算模式。"
关键文字: "[Inner product, Row-based]"
视觉骨架: "[内积数据流示意图, 行式数据流示意图]"
资源ID列表: "[tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_11.asset.01, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_11.asset.02, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_11.asset.03]"
适合复用场景: "[稀疏数据流分类讲解页, SpMM 计算模式对比页]"
不适合复用场景: "[结果能效对比页, 模型类型罗列页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "左侧", "内容": "Inner product 数据流示意图"}
  - {"位置": "右侧", "内容": "Row-based 数据流示意图"}
alternate_claims:
  - "行式数据流按输出矩阵行组织稀疏计算"
layout_tag: "block_diagram"
---
# slide 11: 稀疏计算流：内积与行式数据流

**核心论断**: 内积与行式是 SpMM 稀疏计算流的两类基本数据流

## 本页讲什么
承接上页的 SpMM 算子，进一步拆解其数据流组织方式：介绍内积 (Inner product) 与行式 (Row-based) 两类数据流。讲者可对比二者在数据访问与并行方式上的差异，说明不同数据流决定了稀疏硬件的取数与计算模式。

## 关键文字片段
- Inner product
- Row-based

## 视觉骨架
- 内积数据流示意图
- 行式数据流示意图

## 可复用到
- 稀疏数据流分类讲解页
- SpMM 计算模式对比页

## 不适合复用的场景
- 结果能效对比页
- 模型类型罗列页
