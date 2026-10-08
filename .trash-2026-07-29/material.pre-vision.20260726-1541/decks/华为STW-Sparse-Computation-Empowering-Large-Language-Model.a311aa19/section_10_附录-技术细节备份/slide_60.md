---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_60"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 60
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Fine-grained Tiling 提升并行与访存"
核心论断: "细粒度 tiling 在小 N 提并行、大 N 缓解访存瓶颈"
本页讲什么: "针对上页瓶颈,提出 Fine-grained Tiling:小 N 时提升 GPU 并行度与利用率,大 N 时缓解访存瓶颈;并引出 Technique 2 的 Linear Operator 优化,构成技术组合。"
关键文字: "[Improve parallelism with small N, Fine-grained Tiling, GPU utilization, \"Technique 2: Linear Operator\", Alleviate memory bottleneck with large]"
视觉骨架: "[细粒度 tiling 划分示意, GPU 利用率对比图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_60.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_60.asset.02]"
适合复用场景: "[tiling 优化技术展开页, GEMM 并行度/访存优化]"
不适合复用场景: "[总结过渡 closer 页, 纯理论结论引入页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方", "内容": "小 N 场景: Fine-grained Tiling 提升 GPU 并行度与利用率"}
  - {"位置": "下方", "内容": "大 N 场景: 缓解访存瓶颈, 引出 Technique 2 Linear Operator"}
alternate_claims:
  - "Fine-grained Tiling 与 Linear Operator 优化构成技术组合"
layout_tag: "block_diagram"
---
# slide 60: Fine-grained Tiling 提升并行与访存

**核心论断**: 细粒度 tiling 在小 N 提并行、大 N 缓解访存瓶颈

## 本页讲什么
针对上页瓶颈,提出 Fine-grained Tiling:小 N 时提升 GPU 并行度与利用率,大 N 时缓解访存瓶颈;并引出 Technique 2 的 Linear Operator 优化,构成技术组合。

## 关键文字片段
- Improve parallelism with small N
- Fine-grained Tiling
- GPU utilization
- Technique 2: Linear Operator
- Alleviate memory bottleneck with large

## 视觉骨架
- 细粒度 tiling 划分示意
- GPU 利用率对比图

## 可复用到
- tiling 优化技术展开页
- GEMM 并行度/访存优化

## 不适合复用的场景
- 总结过渡 closer 页
- 纯理论结论引入页
