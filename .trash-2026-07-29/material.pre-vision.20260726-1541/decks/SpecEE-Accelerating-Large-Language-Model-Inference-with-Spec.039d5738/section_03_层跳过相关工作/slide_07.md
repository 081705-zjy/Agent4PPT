---
页标识: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_07"
所属章节: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.sec.03"
所属deck: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738"
页序号: 7
源文件: "templates/本组论文与科研成果/SpecEE Accelerating Large Language Model Inference with Speculative Early Exiting.pptx"
页面角色: "content_candidate"
标题: "方法一：每层后部署预测器"
核心论断: "逐层部署预测器判断早退会引入显著额外开销"
本页讲什么: "承接总览，本页展开第一类方法：在每一层 Transformer 之后各部署一个预测器，用于判断是否可以提前退出。图示逐层的预测器结构，指出该方案需要为每层单独训练/部署预测器，带来不小的参数与推理开销。"
关键文字: "[Deploy a predictor after each layer, Predictor]"
视觉骨架: "[逐层预测器堆叠示意图, 层-预测器对应结构图]"
资源ID列表: "[tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_07.asset.01, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_07.asset.02]"
适合复用场景: "[早退预测器部署方案介绍页, 层跳过方法的算法层展开页]"
不适合复用场景: "[方法效果的数据对比页, 章节总结过渡页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
alternate_claims:
layout_tag: "layer_hierarchy_diagram"
---
# slide 7: 方法一：每层后部署预测器

**核心论断**: 逐层部署预测器判断早退会引入显著额外开销

## 本页讲什么
承接总览，本页展开第一类方法：在每一层 Transformer 之后各部署一个预测器，用于判断是否可以提前退出。图示逐层的预测器结构，指出该方案需要为每层单独训练/部署预测器，带来不小的参数与推理开销。

## 关键文字片段
- Deploy a predictor after each layer
- Predictor

## 视觉骨架
- 逐层预测器堆叠示意图
- 层-预测器对应结构图

## 可复用到
- 早退预测器部署方案介绍页
- 层跳过方法的算法层展开页

## 不适合复用的场景
- 方法效果的数据对比页
- 章节总结过渡页
