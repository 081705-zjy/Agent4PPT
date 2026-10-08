---
页标识: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11"
所属章节: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.sec.04"
所属deck: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a"
页序号: 11
源文件: "templates/本组论文与科研成果/SpeContext Enabling Efficient Long-context Reasoning with.pptx"
页面角色: "content_candidate"
标题: "注意力最大值选择机制"
核心论断: "按注意力最大值选 token 可精准命中关键 KV"
本页讲什么: "本页以密集的矩阵/流程示意（Max、Q、Select）展开注意力打分与 token 选择机制，说明通过取 Query 与各 token 的最大注意力得分即可筛选出真正重要的 KV，为稀疏保留策略提供操作路径。"
关键文字: "[Max, Q × Select]"
视觉骨架: "[注意力打分矩阵, token 选择流程示意, Max/Select 标注]"
资源ID列表: "[tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.01, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.02, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.03, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.04, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.05, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.06, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.07, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.08, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.09, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.10, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_11.asset.11]"
适合复用场景: "[注意力 top-k 选择机制详解页, KV 稀疏保留算法示意页]"
不适合复用场景: "[章节导航开场页, 结论总结过渡页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "左侧矩阵区", "内容": "Q × Select 注意力打分矩阵"}
  - {"位置": "右侧标注", "内容": "Max 选择操作示意"}
alternate_claims:
  - "取 Query 与 token 的最大注意力得分即可筛出关键 KV"
layout_tag: "block_diagram"
---
# slide 11: 注意力最大值选择机制

**核心论断**: 按注意力最大值选 token 可精准命中关键 KV

## 本页讲什么
本页以密集的矩阵/流程示意（Max、Q、Select）展开注意力打分与 token 选择机制，说明通过取 Query 与各 token 的最大注意力得分即可筛选出真正重要的 KV，为稀疏保留策略提供操作路径。

## 关键文字片段
- Max
- Q × Select

## 视觉骨架
- 注意力打分矩阵
- token 选择流程示意
- Max/Select 标注

## 可复用到
- 注意力 top-k 选择机制详解页
- KV 稀疏保留算法示意页

## 不适合复用的场景
- 章节导航开场页
- 结论总结过渡页
