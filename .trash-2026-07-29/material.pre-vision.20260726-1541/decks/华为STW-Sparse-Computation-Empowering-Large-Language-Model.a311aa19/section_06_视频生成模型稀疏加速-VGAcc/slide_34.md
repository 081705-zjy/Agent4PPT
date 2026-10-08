---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_34"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.06"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 34
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "视频生成的算力痛点:更大更冗余"
核心论断: "视频生成比文本/图像有更大且冗余的计算量"
本页讲什么: "承接上页引出的视频生成垂域,本页立起其高算力痛点:相比文本生成和图像分类,视频生成存在更大规模且高度冗余的计算。用90%+相似度点出帧间冗余的来源,为下页给出基于相似性与稀疏分布的加速思路做铺垫。"
关键文字: "[相比文本生成和图像分类,视频生成计算量更大且冗余, larger and redundant computations, \"90%+ similarity 的帧间冗余\"]"
视觉骨架: "[帧间相似度示意图, 冗余计算量对比图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_34.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_34.asset.02]"
适合复用场景: "[视频生成 motivation 痛点页, 帧间冗余引出稀疏的论证页]"
不适合复用场景: "[硬件PE微架构页, 最终实测数据收尾页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "左侧/上方", "内容": "帧间相似度示意图 (90%+ similarity)"}
  - {"位置": "右侧/下方", "内容": "视频 vs 文本/图像 冗余计算量对比图"}
alternate_claims:
  - "帧间冗余来源于 90%+ 的相邻帧相似度"
layout_tag: "mixed"
---
# slide 34: 视频生成的算力痛点:更大更冗余

**核心论断**: 视频生成比文本/图像有更大且冗余的计算量

## 本页讲什么
承接上页引出的视频生成垂域,本页立起其高算力痛点:相比文本生成和图像分类,视频生成存在更大规模且高度冗余的计算。用90%+相似度点出帧间冗余的来源,为下页给出基于相似性与稀疏分布的加速思路做铺垫。

## 关键文字片段
- 相比文本生成和图像分类,视频生成计算量更大且冗余
- larger and redundant computations
- 90%+ similarity 的帧间冗余

## 视觉骨架
- 帧间相似度示意图
- 冗余计算量对比图

## 可复用到
- 视频生成 motivation 痛点页
- 帧间冗余引出稀疏的论证页

## 不适合复用的场景
- 硬件PE微架构页
- 最终实测数据收尾页
