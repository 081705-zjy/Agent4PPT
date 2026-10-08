---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.03"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 14
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "FlashDecoding++ 的两项 GPU 算子优化"
核心论断: "统一最大值消除同步，加速注意力与线性算子"
本页讲什么: "本页展开 FlashDecoding++ 的技术方案，分两条技术线:Tech.1 注意力算子(Attention Operator)通过 unified maximum 消除 softmax 的同步开销;Tech.2 线性算子(Linear Operator)优化。承接 slide 13 提出的成本延迟问题，给出 GPU 上的算子级解法，为后续实验数据做方法铺垫。"
关键文字: "[\"LLM Acceleration on GPUs: FlashDecoding++\", \"Tech. 1: Attention Operator\", \"Tech. 2: Linear Operator\", Eliminate synchronization with unified maximum]"
视觉骨架: "[注意力算子结构示意图, 线性算子优化示意图, 双技术并列框图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14.asset.04, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_14.asset.05]"
适合复用场景: "[注意力算子优化方法介绍页, GPU 算子加速技术方案页]"
不适合复用场景: "[纯背景 motivation 页, benchmark 数据对比页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "LLM Acceleration on GPUs: FlashDecoding++"}
  - {"位置": "左侧板块", "内容": "Tech.1 Attention Operator: 统一最大值消除同步"}
  - {"位置": "右侧板块", "内容": "Tech.2 Linear Operator 优化"}
alternate_claims:
  - "线性算子优化与注意力优化并行构成 FlashDecoding++ 双技术线"
layout_tag: "block_diagram"
---
# slide 14: FlashDecoding++ 的两项 GPU 算子优化

**核心论断**: 统一最大值消除同步，加速注意力与线性算子

## 本页讲什么
本页展开 FlashDecoding++ 的技术方案，分两条技术线:Tech.1 注意力算子(Attention Operator)通过 unified maximum 消除 softmax 的同步开销;Tech.2 线性算子(Linear Operator)优化。承接 slide 13 提出的成本延迟问题，给出 GPU 上的算子级解法，为后续实验数据做方法铺垫。

## 关键文字片段
- LLM Acceleration on GPUs: FlashDecoding++
- Tech. 1: Attention Operator
- Tech. 2: Linear Operator
- Eliminate synchronization with unified maximum

## 视觉骨架
- 注意力算子结构示意图
- 线性算子优化示意图
- 双技术并列框图

## 可复用到
- 注意力算子优化方法介绍页
- GPU 算子加速技术方案页

## 不适合复用的场景
- 纯背景 motivation 页
- benchmark 数据对比页
