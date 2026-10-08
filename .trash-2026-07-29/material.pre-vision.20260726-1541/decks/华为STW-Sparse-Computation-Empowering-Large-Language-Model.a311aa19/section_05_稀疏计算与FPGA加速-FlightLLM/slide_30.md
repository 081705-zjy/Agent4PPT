---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_30"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.05"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 30
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Sparse DSP Chain 架构"
核心论断: "Sparse DSP Chain 统一支持稀疏注意力与线性层"
本页讲什么: "展示 Sparse DSP Chain 架构，说明其可同时支撑 LLM 中的 sparse attention 与 linear layers 两类算子，把上页的灵活 N:M 稀疏落到 FPGA 的 DSP 硬件实现。"
关键文字: "[Sparse DSP Chain supports both sparse attention and linear layers in LLMs, Sparse Attention]"
视觉骨架: "[DSP Chain 硬件架构框图, 注意力/线性层数据流]"
资源ID列表:
适合复用场景: "[FPGA 稀疏算子架构页, Sparse DSP 硬件设计页]"
不适合复用场景: "[纯概念 motivation 页, 工艺节点论证页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Sparse DSP Chain 架构"}
  - {"位置": "中间主体", "内容": "DSP Chain 硬件框图与数据流"}
  - {"位置": "下方标注", "内容": "支持 sparse attention 与 linear layers"}
alternate_claims:
  - "同一 DSP 链路可复用于 attention 与 linear 两类算子"
layout_tag: "block_diagram"
---
# slide 30: Sparse DSP Chain 架构

**核心论断**: Sparse DSP Chain 统一支持稀疏注意力与线性层

## 本页讲什么
展示 Sparse DSP Chain 架构，说明其可同时支撑 LLM 中的 sparse attention 与 linear layers 两类算子，把上页的灵活 N:M 稀疏落到 FPGA 的 DSP 硬件实现。

## 关键文字片段
- Sparse DSP Chain supports both sparse attention and linear layers in LLMs
- Sparse Attention

## 视觉骨架
- DSP Chain 硬件架构框图
- 注意力/线性层数据流

## 可复用到
- FPGA 稀疏算子架构页
- Sparse DSP 硬件设计页

## 不适合复用的场景
- 纯概念 motivation 页
- 工艺节点论证页
