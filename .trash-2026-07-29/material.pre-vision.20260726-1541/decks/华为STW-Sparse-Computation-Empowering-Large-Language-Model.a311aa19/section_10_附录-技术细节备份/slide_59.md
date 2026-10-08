---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_59"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 59
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Decode 阶段 Flat GEMM 瓶颈分析"
核心论断: "decode 阶段 Flat GEMM 随 N 变化呈现不同瓶颈"
本页讲什么: "分析 decode 阶段的 GEMM 特征——即 Flat GEMM,并针对不同的 N 值做瓶颈分析,指出小 N 与大 N 下瓶颈来源不同,为下一页提出对应的 tiling 与算子优化技术铺垫。"
关键文字: "[\"GEMM at decode phase: Flat GEMM\", The bottleneck analysis with different N]"
视觉骨架: "[Flat GEMM 结构示意, 不同 N 瓶颈分析图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_59.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_59.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_59.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_59.asset.04]"
适合复用场景: "[GEMM 算子瓶颈分析页, decode 阶段计算特征展开]"
不适合复用场景: "[概念性 bullet 引入页, MoE 训练加速结果页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "左侧", "内容": "Flat GEMM 结构示意"}
  - {"位置": "右侧", "内容": "不同 N 瓶颈分析图"}
alternate_claims:
  - "小 N 时瓶颈来自访存/低算力利用"
  - "大 N 时瓶颈转向算力/带宽约束"
layout_tag: "mixed"
---
# slide 59: Decode 阶段 Flat GEMM 瓶颈分析

**核心论断**: decode 阶段 Flat GEMM 随 N 变化呈现不同瓶颈

## 本页讲什么
分析 decode 阶段的 GEMM 特征——即 Flat GEMM,并针对不同的 N 值做瓶颈分析,指出小 N 与大 N 下瓶颈来源不同,为下一页提出对应的 tiling 与算子优化技术铺垫。

## 关键文字片段
- GEMM at decode phase: Flat GEMM
- The bottleneck analysis with different N

## 视觉骨架
- Flat GEMM 结构示意
- 不同 N 瓶颈分析图

## 可复用到
- GEMM 算子瓶颈分析页
- decode 阶段计算特征展开

## 不适合复用的场景
- 概念性 bullet 引入页
- MoE 训练加速结果页
