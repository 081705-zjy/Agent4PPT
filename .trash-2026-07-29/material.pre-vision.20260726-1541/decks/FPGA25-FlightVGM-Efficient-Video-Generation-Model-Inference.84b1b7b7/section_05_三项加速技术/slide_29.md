---
页标识: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_29"
所属章节: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.sec.05"
所属deck: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7"
页序号: 29
源文件: "templates/本组论文与科研成果/FPGA25  FlightVGM Efficient Video Generation Model Inference with.pptx"
页面角色: "content_candidate"
标题: "FP16 乘积的位段提取"
核心论断: "从乘积高位段提取正确 FP16 结果"
本页讲什么: "以 FP16 乘积的位段划分（P[31:16]、P[36:22]）说明如何从拆分后的乘加结果中提取正确的浮点乘积位段，落实 DSP58 混合精度浮点运算的取位逻辑。"
关键文字: "[FP16, \"P[31:16]\", \"P[36:22]\"]"
视觉骨架: "[乘积位段划分图, FP16 取位示意, 比特区间标注]"
资源ID列表: "[tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_29.asset.01, tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_29.asset.02]"
适合复用场景: "[浮点乘积位段提取页, FP16 取位逻辑展开页]"
不适合复用场景: "[技术引入标题页, 帧相似性洞察页, 调度编译流程页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
alternate_claims:
layout_tag: "block_diagram"
---
# slide 29: FP16 乘积的位段提取

**核心论断**: 从乘积高位段提取正确 FP16 结果

## 本页讲什么
以 FP16 乘积的位段划分（P[31:16]、P[36:22]）说明如何从拆分后的乘加结果中提取正确的浮点乘积位段，落实 DSP58 混合精度浮点运算的取位逻辑。

## 关键文字片段
- FP16
- P[31:16]
- P[36:22]

## 视觉骨架
- 乘积位段划分图
- FP16 取位示意
- 比特区间标注

## 可复用到
- 浮点乘积位段提取页
- FP16 取位逻辑展开页

## 不适合复用的场景
- 技术引入标题页
- 帧相似性洞察页
- 调度编译流程页
