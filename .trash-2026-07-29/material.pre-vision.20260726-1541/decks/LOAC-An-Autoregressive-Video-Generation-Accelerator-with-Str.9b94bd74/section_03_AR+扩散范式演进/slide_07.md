---
页标识: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_07"
所属章节: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.sec.03"
所属deck: "tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74"
页序号: 7
源文件: "templates/内部组会科研交流/LOAC An Autoregressive Video Generation Accelerator with Stripe-Informed Sparse Attention and KV Compaction.pptx"
页面角色: "content_candidate"
标题: "双向注意力视频模型的两大局限"
核心论断: "双向注意力训推计算量爆炸且无法真正实时生成"
本页讲什么: "本页开启范式演进讨论，指出以往视频生成模型依赖双向注意力（bidirectional attention）做时空建模，带来训练与推理计算量爆炸，且天然无法实时逐帧生成，为后文转向自回归范式建立动机。"
关键文字: "[之前的视频模型通过双向注意力（bidirectional attention）进行时空建模, 训推计算量爆炸，且无法真正实时生成]"
视觉骨架: "[双向注意力时空建模示意图, 视频帧序列配图]"
资源ID列表: "[tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_07.asset.01, tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.slide_07.asset.02]"
适合复用场景: "[视频生成范式演进章节 opener, 双向注意力局限论证页]"
不适合复用场景: "[具体加速方法细节页, 含benchmark数字的结果页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "opener"
视觉文本层次:
  - {"位置": "上方标题", "内容": "双向注意力视频模型的两大局限"}
  - {"位置": "中部主体", "内容": "双向注意力时空建模示意图与视频帧序列"}
  - {"位置": "下方结论", "内容": "训推计算量爆炸且无法实时生成"}
alternate_claims:
  - "双向注意力天然无法逐帧实时生成"
layout_tag: "block_diagram"
---
# slide 7: 双向注意力视频模型的两大局限

**核心论断**: 双向注意力训推计算量爆炸且无法真正实时生成

## 本页讲什么
本页开启范式演进讨论，指出以往视频生成模型依赖双向注意力（bidirectional attention）做时空建模，带来训练与推理计算量爆炸，且天然无法实时逐帧生成，为后文转向自回归范式建立动机。

## 关键文字片段
- 之前的视频模型通过双向注意力（bidirectional attention）进行时空建模
- 训推计算量爆炸，且无法真正实时生成

## 视觉骨架
- 双向注意力时空建模示意图
- 视频帧序列配图

## 可复用到
- 视频生成范式演进章节 opener
- 双向注意力局限论证页

## 不适合复用的场景
- 具体加速方法细节页
- 含benchmark数字的结果页
