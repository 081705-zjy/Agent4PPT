---
页标识: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_03"
所属章节: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.sec.02"
所属deck: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738"
页序号: 3
源文件: "templates/本组论文与科研成果/SpecEE Accelerating Large Language Model Inference with Speculative Early Exiting.pptx"
页面角色: "content_candidate"
标题: "Agent 场景推动请求 token 量级激增"
核心论断: "Agent 应用把单请求 token 从 0.1k 推高到 10k 量级"
本页讲什么: "本页用 token 量级数据立起「推理成本」这一压力。以 Agent 等新型应用为例，说明单次请求的 token 数正从 0.1k~1k 跃升到 1k~10k 甚至更高量级，请求越长、逐层计算越重，直接推高推理开销。这是本章第一条压力线，为下一页的边缘部署难题和最终「如何减少逐层计算」做铺垫。"
关键文字: "[Agent, \"0.1k~1k tokens/request\", \"1k~10k\"]"
视觉骨架: "[token 量级对比柱图, 请求场景标注, 量级增长箭头]"
资源ID列表: "[tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_03.asset.01, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_03.asset.02]"
适合复用场景: "[大模型推理成本 motivation 页, 长上下文/Agent 场景论证页]"
不适合复用场景: "[方法架构展开页, 边缘硬件部署页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Agent 场景推动请求 token 量级激增"}
  - {"位置": "下方主体", "内容": "token 量级对比柱图与场景标注"}
alternate_claims:
  - "请求越长，逐层计算负担越重，直接推高推理开销"
layout_tag: "dense_data_chart"
---
# slide 3: Agent 场景推动请求 token 量级激增

**核心论断**: Agent 应用把单请求 token 从 0.1k 推高到 10k 量级

## 本页讲什么
本页用 token 量级数据立起「推理成本」这一压力。以 Agent 等新型应用为例，说明单次请求的 token 数正从 0.1k~1k 跃升到 1k~10k 甚至更高量级，请求越长、逐层计算越重，直接推高推理开销。这是本章第一条压力线，为下一页的边缘部署难题和最终「如何减少逐层计算」做铺垫。

## 关键文字片段
- Agent
- 0.1k~1k tokens/request
- 1k~10k

## 视觉骨架
- token 量级对比柱图
- 请求场景标注
- 量级增长箭头

## 可复用到
- 大模型推理成本 motivation 页
- 长上下文/Agent 场景论证页

## 不适合复用的场景
- 方法架构展开页
- 边缘硬件部署页
