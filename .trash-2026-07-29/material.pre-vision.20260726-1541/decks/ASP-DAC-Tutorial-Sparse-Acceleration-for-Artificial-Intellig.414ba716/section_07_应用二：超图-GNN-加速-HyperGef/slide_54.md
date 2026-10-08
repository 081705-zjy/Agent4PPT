---
页标识: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_54"
所属章节: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.07"
所属deck: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716"
页序号: 54
源文件: "templates/本组论文与科研成果/ASP-DAC Tutorial   Sparse Acceleration for Artificial Intelligence Progress and Trends.pptx"
页面角色: "chapter_candidate"
标题: "源-目的分区重叠优化"
核心论断: "源与目的分区重叠减少跨分区冗余访存"
本页讲什么: "展开另一项 GPU 优化：对源分区（Source partitions）与目的分区（Destination partitions）做重叠（Overlapping）划分，让相邻分区共享数据以减少跨分区的重复访存，提升缓存局部性，是融合框架的关键调度策略。"
关键文字: "[\"Application: HyperGNN\", Overlapping, Source partitions, Destination partitions]"
视觉骨架: "[源/目的分区网格图, 重叠区域高亮标注]"
资源ID列表: "[tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_54.asset.01, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_54.asset.02, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_54.asset.03]"
适合复用场景: "[图计算分区调度优化页, 分区重叠减冗余方案页]"
不适合复用场景: "[能效结果数字页, 整体框架总览页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Application: HyperGNN — Overlapping"}
  - {"位置": "下方主体", "内容": "源分区与目的分区重叠划分示意图"}
alternate_claims:
  - "重叠划分提升缓存局部性"
layout_tag: "block_diagram"
---
# slide 54: 源-目的分区重叠优化

**核心论断**: 源与目的分区重叠减少跨分区冗余访存

## 本页讲什么
展开另一项 GPU 优化：对源分区（Source partitions）与目的分区（Destination partitions）做重叠（Overlapping）划分，让相邻分区共享数据以减少跨分区的重复访存，提升缓存局部性，是融合框架的关键调度策略。

## 关键文字片段
- Application: HyperGNN
- Overlapping
- Source partitions
- Destination partitions

## 视觉骨架
- 源/目的分区网格图
- 重叠区域高亮标注

## 可复用到
- 图计算分区调度优化页
- 分区重叠减冗余方案页

## 不适合复用的场景
- 能效结果数字页
- 整体框架总览页
