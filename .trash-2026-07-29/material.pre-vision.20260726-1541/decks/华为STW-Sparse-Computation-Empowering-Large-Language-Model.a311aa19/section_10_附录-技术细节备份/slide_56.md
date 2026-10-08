---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 56
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "LLM Dataflow: prefill 与 decode 阶段"
核心论断: "LLM 推理分 prefill 与 decode 两阶段,数据流特征迥异"
本页讲什么: "用数据流图铺开 LLM 推理的两个阶段——prefill 阶段与 decode 阶段,标出 Linear 等算子的数据流走向,为后续逐一分析 softmax、GEMM、tiling 的优化点建立整体框架。"
关键文字: "[prefill phase, decode phase, LLM Dataflow, Linear]"
视觉骨架: "[prefill/decode 两阶段数据流图, 算子模块连线示意]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.04, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.05, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.06, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.07, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_56.asset.08]"
适合复用场景: "[LLM 推理流程 dataflow 展开页, prefill/decode 两阶段对比引入]"
不适合复用场景: "[单一数值曲线结果页, 概念 bullet 论证页]"
上页角色: "content_candidate"
下页角色: "chapter_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方", "内容": "prefill phase 数据流图"}
  - {"位置": "下方", "内容": "decode phase 数据流图"}
alternate_claims:
layout_tag: "block_diagram"
---
# slide 56: LLM Dataflow: prefill 与 decode 阶段

**核心论断**: LLM 推理分 prefill 与 decode 两阶段,数据流特征迥异

## 本页讲什么
用数据流图铺开 LLM 推理的两个阶段——prefill 阶段与 decode 阶段,标出 Linear 等算子的数据流走向,为后续逐一分析 softmax、GEMM、tiling 的优化点建立整体框架。

## 关键文字片段
- prefill phase
- decode phase
- LLM Dataflow
- Linear

## 视觉骨架
- prefill/decode 两阶段数据流图
- 算子模块连线示意

## 可复用到
- LLM 推理流程 dataflow 展开页
- prefill/decode 两阶段对比引入

## 不适合复用的场景
- 单一数值曲线结果页
- 概念 bullet 论证页
