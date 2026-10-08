---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_21"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.04"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 21
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Way 2 示例:高效模型量化"
核心论断: "混合位宽量化以 1.27B 达到 7B 能力且更低成本"
本页讲什么: "本页展开 Way 2 高效模型,介绍自研 2/4/16-bit 混合量化方法:通过 Intra-weight 2/4-bit 量化与 Exclusive 2-bit Outliers,使 1.27B(2.9-bit)模型达到 7B 容量,实现更高精度与更低成本,是延迟-精度权衡下的高效模型例证。"
关键文字: "[\"Ours: 1.27B (2.9-bit) achieves 7B capacity\", Intra-weight 2/4-bit Quantization, Exclusive 2-bit Outliers, Higher Accuracy and Lower Cost (Ours)]"
视觉骨架: "[混合位宽量化示意图, 精度-成本对比图, Outlier 处理结构图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_21.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_21.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_21.asset.03]"
适合复用场景: "[模型量化压缩方法示例页, 高效模型精度-成本对比页]"
不适合复用场景: "[纯概念路径总览页, 新架构基础模型介绍页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "result"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Way 2 示例:高效模型量化"}
  - {"位置": "中间主体", "内容": "混合位宽量化示意图 + Outlier 处理结构"}
  - {"位置": "下方对比", "内容": "精度-成本对比图与结论文字"}
alternate_claims:
  - "Intra-weight 2/4-bit 量化配合 Exclusive 2-bit Outliers 提升精度"
  - "混合位宽方案在更低成本下取得更高精度"
layout_tag: "mixed"
---
# slide 21: Way 2 示例:高效模型量化

**核心论断**: 混合位宽量化以 1.27B 达到 7B 能力且更低成本

## 本页讲什么
本页展开 Way 2 高效模型,介绍自研 2/4/16-bit 混合量化方法:通过 Intra-weight 2/4-bit 量化与 Exclusive 2-bit Outliers,使 1.27B(2.9-bit)模型达到 7B 容量,实现更高精度与更低成本,是延迟-精度权衡下的高效模型例证。

## 关键文字片段
- Ours: 1.27B (2.9-bit) achieves 7B capacity
- Intra-weight 2/4-bit Quantization
- Exclusive 2-bit Outliers
- Higher Accuracy and Lower Cost (Ours)

## 视觉骨架
- 混合位宽量化示意图
- 精度-成本对比图
- Outlier 处理结构图

## 可复用到
- 模型量化压缩方法示例页
- 高效模型精度-成本对比页

## 不适合复用的场景
- 纯概念路径总览页
- 新架构基础模型介绍页
