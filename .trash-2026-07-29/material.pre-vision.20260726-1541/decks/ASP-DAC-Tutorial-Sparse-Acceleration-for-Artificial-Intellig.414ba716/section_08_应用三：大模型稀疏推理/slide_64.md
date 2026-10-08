---
页标识: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64"
所属章节: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.08"
所属deck: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716"
页序号: 64
源文件: "templates/本组论文与科研成果/ASP-DAC Tutorial   Sparse Acceleration for Artificial Intelligence Progress and Trends.pptx"
页面角色: "content_candidate"
标题: "稀疏方法：统计注意力分布自动生成掩码"
核心论断: "按注意力统计分布可自动生成稀疏 attention mask"
本页讲什么: "展开团队的 LLM 稀疏方法：观察模型不同位置的注意力矩阵，发现其分布规律，进而基于统计注意力分布自动生成稀疏 attention mask，把原始稠密注意力转为稀疏计算。"
关键文字: "[\"LLM: Sparse Method\", Attention matrix at different positions of a model, automatically generate a sparse attention mask based on the statistical attention distribution]"
视觉骨架: "[多位置注意力矩阵热力图, 稀疏掩码生成示意]"
资源ID列表: "[tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.01, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.02, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.03, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.04, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.05, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.06, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.07, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.08, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.09, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.10, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_64.asset.11]"
适合复用场景: "[稀疏注意力掩码方法展示页, 注意力分布统计观察页]"
不适合复用场景: "[训练成本论证页, 实验结果汇总页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "LLM: Sparse Method"}
  - {"位置": "中部主体", "内容": "多位置注意力矩阵热力图 + 稀疏掩码生成示意"}
alternate_claims:
  - "模型不同位置的注意力矩阵呈现可识别的分布规律"
layout_tag: "block_diagram"
---
# slide 64: 稀疏方法：统计注意力分布自动生成掩码

**核心论断**: 按注意力统计分布可自动生成稀疏 attention mask

## 本页讲什么
展开团队的 LLM 稀疏方法：观察模型不同位置的注意力矩阵，发现其分布规律，进而基于统计注意力分布自动生成稀疏 attention mask，把原始稠密注意力转为稀疏计算。

## 关键文字片段
- LLM: Sparse Method
- Attention matrix at different positions of a model
- automatically generate a sparse attention mask based on the statistical attention distribution

## 视觉骨架
- 多位置注意力矩阵热力图
- 稀疏掩码生成示意

## 可复用到
- 稀疏注意力掩码方法展示页
- 注意力分布统计观察页

## 不适合复用的场景
- 训练成本论证页
- 实验结果汇总页
