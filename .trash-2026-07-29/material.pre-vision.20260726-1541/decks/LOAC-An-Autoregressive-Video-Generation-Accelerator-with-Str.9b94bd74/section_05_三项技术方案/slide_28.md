---
页标识: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_28"
所属章节: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.sec.05"
所属deck: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74"
页序号: 28
源文件: "templates/内部组会科研交流/LOAC An Autoregressive Video Generation Accelerator with Stripe-Informed Sparse Attention and KV Compaction.pptx"
页面角色: "content_candidate"
标题: "统一稀疏：轻量级预测施加分级 mask"
核心论断: "轻量级采样按块注意力分数分配粗细 mask"
本页讲什么: "本页展开技术方案一的方法细节：通过采样统计每帧内注意力的分数和，为不同块施加粗细不同的 mask，实现轻量级预测下的分级稀疏，配合多张图示说明预测与 mask 分配流程。"
关键文字: "[统一的注意力稀疏方式, 轻量级预测：采样统计每帧内注意力分数和, 给每个块施加不同粗细的 mask]"
视觉骨架: "[轻量级预测流程示意, 分级 mask 分配图]"
资源ID列表: "[tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_28.asset.01, tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_28.asset.02, tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_28.asset.03, tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_28.asset.04]"
适合复用场景: "[稀疏注意力算法细节页, 轻量级预测机制展开页]"
不适合复用场景: "[方案总览导航页, 硬件架构数据流页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "统一稀疏：轻量级预测施加分级 mask"}
  - {"位置": "中部主体", "内容": "轻量级预测流程示意 + 分级 mask 分配图"}
alternate_claims:
  - "按块注意力分数和实现分级粗细 mask 分配"
layout_tag: "block_diagram"
---
# slide 28: 统一稀疏：轻量级预测施加分级 mask

**核心论断**: 轻量级采样按块注意力分数分配粗细 mask

## 本页讲什么
本页展开技术方案一的方法细节：通过采样统计每帧内注意力的分数和，为不同块施加粗细不同的 mask，实现轻量级预测下的分级稀疏，配合多张图示说明预测与 mask 分配流程。

## 关键文字片段
- 统一的注意力稀疏方式
- 轻量级预测：采样统计每帧内注意力分数和
- 给每个块施加不同粗细的 mask

## 视觉骨架
- 轻量级预测流程示意
- 分级 mask 分配图

## 可复用到
- 稀疏注意力算法细节页
- 轻量级预测机制展开页

## 不适合复用的场景
- 方案总览导航页
- 硬件架构数据流页
