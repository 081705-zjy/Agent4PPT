---
页标识: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_13"
所属章节: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.sec.04"
所属deck: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738"
页序号: 13
源文件: "templates/本组论文与科研成果/SpecEE Accelerating Large Language Model Inference with Speculative Early Exiting.pptx"
页面角色: "content_candidate"
标题: "每层后部署轻量预测器"
核心论断: "在每层后部署轻量预测器判定是否早退"
本页讲什么: "本页给出第二根技术支柱：在每一层之后部署一个预测器，实时判断当前 token 是否可早退退出，落地投机搜索缩减后的判定环节，衔接后续离线特征与训练闭环。"
关键文字: "[Deploy a predictor after each layer, Predictor]"
视觉骨架: "[逐层预测器部署示意, 层间判定流程图]"
资源ID列表: "[tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_13.asset.01, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_13.asset.02]"
适合复用场景: "[轻量预测器部署介绍页, 逐层早退判定机制页]"
不适合复用场景: "[宏观背景动机页, 结果 benchmark 对比页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "每层后部署轻量预测器"}
  - {"位置": "下方主体", "内容": "逐层预测器部署示意与层间判定流程图"}
alternate_claims:
  - "预测器实时判定当前 token 是否可早退"
layout_tag: "block_diagram"
---
# slide 13: 每层后部署轻量预测器

**核心论断**: 在每层后部署轻量预测器判定是否早退

## 本页讲什么
本页给出第二根技术支柱：在每一层之后部署一个预测器，实时判断当前 token 是否可早退退出，落地投机搜索缩减后的判定环节，衔接后续离线特征与训练闭环。

## 关键文字片段
- Deploy a predictor after each layer
- Predictor

## 视觉骨架
- 逐层预测器部署示意
- 层间判定流程图

## 可复用到
- 轻量预测器部署介绍页
- 逐层早退判定机制页

## 不适合复用的场景
- 宏观背景动机页
- 结果 benchmark 对比页
