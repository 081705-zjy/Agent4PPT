---
页标识: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_67"
所属章节: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.08"
所属deck: "tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716"
页序号: 67
源文件: "templates/本组论文与科研成果/ASP-DAC Tutorial   Sparse Acceleration for Artificial Intelligence Progress and Trends.pptx"
页面角色: "content_candidate"
标题: "Attention 算子访存受限，单一映射非最优"
核心论断: "Attention 算子访存受限，单一编译映射得不到最优数据流"
本页讲什么: "转入编译映射环节，指出与传统 AI 模型相比，attention 算子具有访存受限（limited memory access）特性，单一的编译映射无法获得最优数据流，引出需要自适应的编译映射策略。"
关键文字: "[The attention operator has the characteristic of limited memory access, a single compilation mapping cannot obtain the optimal data flow]"
视觉骨架: "[访存受限特性示意, 编译映射数据流对比]"
资源ID列表: "[tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_67.asset.01, tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.slide_67.asset.02]"
适合复用场景: "[Attention 访存痛点论证页, 编译映射立题引入页]"
不适合复用场景: "[实验结果汇总页, 稀疏掩码方法页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Attention 算子访存受限，单一映射非最优"}
  - {"位置": "下方主体", "内容": "访存受限特性示意与编译映射数据流对比"}
alternate_claims:
  - "单一编译映射无法为 attention 生成最优数据流"
layout_tag: "block_diagram"
---
# slide 67: Attention 算子访存受限，单一映射非最优

**核心论断**: Attention 算子访存受限，单一编译映射得不到最优数据流

## 本页讲什么
转入编译映射环节，指出与传统 AI 模型相比，attention 算子具有访存受限（limited memory access）特性，单一的编译映射无法获得最优数据流，引出需要自适应的编译映射策略。

## 关键文字片段
- The attention operator has the characteristic of limited memory access
- a single compilation mapping cannot obtain the optimal data flow

## 视觉骨架
- 访存受限特性示意
- 编译映射数据流对比

## 可复用到
- Attention 访存痛点论证页
- 编译映射立题引入页

## 不适合复用的场景
- 实验结果汇总页
- 稀疏掩码方法页
