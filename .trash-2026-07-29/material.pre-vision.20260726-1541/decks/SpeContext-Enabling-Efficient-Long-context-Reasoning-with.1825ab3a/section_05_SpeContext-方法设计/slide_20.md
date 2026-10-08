---
页标识: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_20"
所属章节: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.sec.05"
所属deck: "tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a"
页序号: 20
源文件: "templates/本组论文与科研成果/SpeContext Enabling Efficient Long-context Reasoning with.pptx"
页面角色: "content_candidate"
标题: "预取稀疏 KV 缓存（组件三）"
核心论断: "预取稀疏 KV 缓存按需加载 Re/Attn/FFN 计算"
本页讲什么: "本页开启 SpeContext 第三组件 Prefetch Sparse KV Cache（预取稀疏 KV 缓存）的介绍，用 Re./Attn/FFN 计算流框图展示预取机制如何在稀疏缓存下提前调度所需 KV，降低长上下文解码时的访存瓶颈。"
关键文字: "[(b) Prefetch Sparse KV Cache, Re. / Attn / FFN 计算流]"
视觉骨架: "[预取稀疏 KV 缓存流程框图, Re/Attn/FFN 计算流示意]"
资源ID列表: "[tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_20.asset.01, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_20.asset.02, tpl.本组论文与科研成果.SpeContext-Enabling-Efficient-Long-context-Reasoning-with.1825ab3a.slide_20.asset.03]"
适合复用场景: "[KV 缓存预取机制 method 页, 稀疏缓存访存优化介绍页]"
不适合复用场景: "[benchmark 数字对比页, 宏观动机页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标签", "内容": "(b) Prefetch Sparse KV Cache 组件标题"}
  - {"位置": "下方主体", "内容": "Re./Attn/FFN 计算流与预取调度框图"}
alternate_claims:
layout_tag: "flowchart"
---
# slide 20: 预取稀疏 KV 缓存（组件三）

**核心论断**: 预取稀疏 KV 缓存按需加载 Re/Attn/FFN 计算

## 本页讲什么
本页开启 SpeContext 第三组件 Prefetch Sparse KV Cache（预取稀疏 KV 缓存）的介绍，用 Re./Attn/FFN 计算流框图展示预取机制如何在稀疏缓存下提前调度所需 KV，降低长上下文解码时的访存瓶颈。

## 关键文字片段
- (b) Prefetch Sparse KV Cache
- Re. / Attn / FFN 计算流

## 视觉骨架
- 预取稀疏 KV 缓存流程框图
- Re/Attn/FFN 计算流示意

## 可复用到
- KV 缓存预取机制 method 页
- 稀疏缓存访存优化介绍页

## 不适合复用的场景
- benchmark 数字对比页
- 宏观动机页
