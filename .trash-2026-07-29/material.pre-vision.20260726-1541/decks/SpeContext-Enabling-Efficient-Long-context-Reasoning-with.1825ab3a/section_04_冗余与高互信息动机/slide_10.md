---
页标识: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10"
所属章节: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.sec.04"
所属deck: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a"
页序号: 10
源文件: "templates/本组论文与科研成果/SpeContext Enabling Efficient Long-context Reasoning with.pptx"
页面角色: "content_candidate"
标题: "注意力示例揭示 KV 冗余"
核心论断: "滑动窗口注意力显示多数 token 贡献低、KV 存在冗余"
本页讲什么: "本页用一个具体 Prompt（What is the largest ocean?）加滑动窗口示意，展示注意力主要集中在少数关键 token 上，其余 token 贡献稀薄，从而直观揭示 KV cache 中广泛存在的冗余，为后续稀疏化论证铺垫。"
关键文字: "[\"Prompt: What is the largest ocean?\", Sliding window]"
视觉骨架: "[注意力热力示意, 滑动窗口标注, Prompt 文本框]"
资源ID列表: "[tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10.asset.01, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10.asset.02, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10.asset.03, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10.asset.04, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_10.asset.05]"
适合复用场景: "[KV 冗余 motivation 举例页, 注意力稀疏性直观演示页]"
不适合复用场景: "[纯理论公式推导页, benchmark 数据对比页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方", "内容": "Prompt 文本框: What is the largest ocean?"}
  - {"位置": "下方主体", "内容": "滑动窗口注意力热力示意图"}
alternate_claims:
  - "少数关键 token 承担主要注意力贡献"
layout_tag: "block_diagram"
---
# slide 10: 注意力示例揭示 KV 冗余

**核心论断**: 滑动窗口注意力显示多数 token 贡献低、KV 存在冗余

## 本页讲什么
本页用一个具体 Prompt（What is the largest ocean?）加滑动窗口示意，展示注意力主要集中在少数关键 token 上，其余 token 贡献稀薄，从而直观揭示 KV cache 中广泛存在的冗余，为后续稀疏化论证铺垫。

## 关键文字片段
- Prompt: What is the largest ocean?
- Sliding window

## 视觉骨架
- 注意力热力示意
- 滑动窗口标注
- Prompt 文本框

## 可复用到
- KV 冗余 motivation 举例页
- 注意力稀疏性直观演示页

## 不适合复用的场景
- 纯理论公式推导页
- benchmark 数据对比页
