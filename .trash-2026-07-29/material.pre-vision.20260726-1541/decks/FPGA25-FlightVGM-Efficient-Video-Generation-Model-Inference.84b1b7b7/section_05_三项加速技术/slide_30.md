---
页标识: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30"
所属章节: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.sec.05"
所属deck: "tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7"
页序号: 30
源文件: "templates/本组论文与科研成果/FPGA25  FlightVGM Efficient Video Generation Model Inference with.pptx"
页面角色: "content_candidate"
标题: "浮点尾数与指数的拼接"
核心论断: "分离处理尾数与指数完成 DSP58 浮点重构"
本页讲什么: "展开浮点数尾数（frac）与指数（exp）的分离处理与拼接逻辑，说明如何在可配置 DSP58 上分别计算并重组浮点分量，形成完整的混合精度浮点乘加路径。"
关键文字: "[frac, exp]"
视觉骨架: "[尾数指数分离示意, 浮点拼接框图, 分量处理箭头]"
资源ID列表: "[tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30.asset.01, tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30.asset.02, tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30.asset.03, tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30.asset.04, tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.slide_30.asset.05]"
适合复用场景: "[浮点尾数指数处理页, DSP 浮点重构方法页]"
不适合复用场景: "[技术引入标题页, 帧相似性数据页, 本章目录页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "左侧", "内容": "尾数(frac)分离处理示意"}
  - {"位置": "右侧", "内容": "指数(exp)分离处理与拼接框图"}
alternate_claims:
  - "可配置 DSP58 支持尾数与指数的独立计算路径"
layout_tag: "block_diagram"
---
# slide 30: 浮点尾数与指数的拼接

**核心论断**: 分离处理尾数与指数完成 DSP58 浮点重构

## 本页讲什么
展开浮点数尾数（frac）与指数（exp）的分离处理与拼接逻辑，说明如何在可配置 DSP58 上分别计算并重组浮点分量，形成完整的混合精度浮点乘加路径。

## 关键文字片段
- frac
- exp

## 视觉骨架
- 尾数指数分离示意
- 浮点拼接框图
- 分量处理箭头

## 可复用到
- 浮点尾数指数处理页
- DSP 浮点重构方法页

## 不适合复用的场景
- 技术引入标题页
- 帧相似性数据页
- 本章目录页
