---
页标识: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17"
所属章节: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.sec.05"
所属deck: "tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738"
页序号: 17
源文件: "templates/本组论文与科研成果/SpecEE Accelerating Large Language Model Inference with Speculative Early Exiting.pptx"
页面角色: "content_candidate"
标题: "离线数据采集：高频早退预测器筛选"
核心论断: "离线采集逐层早退信号可筛出高命中率预测器"
本页讲什么: "本页交代 SpecEE 部署前的离线数据采集环节：通过大量样本运行，统计各层早退信号的触发频率，从中挑选出高频、高命中的层作为轻量预测器的候选，为后续预测器训练提供带监督标签的数据基础。"
关键文字: "[Offline Data Collection, Select the predictor with high frequency]"
视觉骨架: "[离线采集流程示意图, 高频预测器筛选标注, 多层信号统计图]"
资源ID列表: "[tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.01, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.02, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.03, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.04, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.05, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.06, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.07, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.08, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.09, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.10, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.11, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.12, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.13, tpl.本组论文与科研成果.SpecEE-Accelerating-Large-Language-Model-Inference-with-Spec.039d5738.slide_17.asset.14]"
适合复用场景: "[早退/剪枝方法的离线数据采集页, 预测器训练数据制备说明页, 大模型推理方法章的离线制备环节]"
不适合复用场景: "[纯 benchmark 结果对比页, 在线部署推理流程页, 无数据采集的概念论证页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题区", "内容": "Offline Data Collection"}
  - {"位置": "中间主体", "内容": "多层早退信号统计流程图"}
  - {"位置": "下方标注", "内容": "Select the predictor with high frequency"}
alternate_claims:
  - "高频层的早退信号更适合作为轻量预测器的训练标签"
layout_tag: "flowchart"
---
# slide 17: 离线数据采集：高频早退预测器筛选

**核心论断**: 离线采集逐层早退信号可筛出高命中率预测器

## 本页讲什么
本页交代 SpecEE 部署前的离线数据采集环节：通过大量样本运行，统计各层早退信号的触发频率，从中挑选出高频、高命中的层作为轻量预测器的候选，为后续预测器训练提供带监督标签的数据基础。

## 关键文字片段
- Offline Data Collection
- Select the predictor with high frequency

## 视觉骨架
- 离线采集流程示意图
- 高频预测器筛选标注
- 多层信号统计图

## 可复用到
- 早退/剪枝方法的离线数据采集页
- 预测器训练数据制备说明页
- 大模型推理方法章的离线制备环节

## 不适合复用的场景
- 纯 benchmark 结果对比页
- 在线部署推理流程页
- 无数据采集的概念论证页
