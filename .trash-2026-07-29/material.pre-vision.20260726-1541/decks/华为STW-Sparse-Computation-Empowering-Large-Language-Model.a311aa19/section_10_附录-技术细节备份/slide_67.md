---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 67
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "MoD 原理:Early Exit 跳层"
核心论断: "MoD 通过 early exit 跳过后续层实现深度稀疏"
本页讲什么: "速查 MoD(Mixture of Depths)原理:通过 Early Exit 机制让部分 token 跳过后续层的计算,在深度维度上实现动态稀疏,降低推理开销。"
关键文字: "[MoD, Early Exit, (Skip the following layers)]"
视觉骨架: "[MoD 跳层机制示意, early exit 路由图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.04, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.05, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_67.asset.06]"
适合复用场景: "[MoD 原理速查介绍页, 深度维度稀疏机制展开]"
不适合复用场景: "[GEMM 瓶颈分析页, 结果加速数据页]"
上页角色: "content_candidate"
下页角色: "ending_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
alternate_claims:
layout_tag: "block_diagram"
---
# slide 67: MoD 原理:Early Exit 跳层

**核心论断**: MoD 通过 early exit 跳过后续层实现深度稀疏

## 本页讲什么
速查 MoD(Mixture of Depths)原理:通过 Early Exit 机制让部分 token 跳过后续层的计算,在深度维度上实现动态稀疏,降低推理开销。

## 关键文字片段
- MoD
- Early Exit
- (Skip the following layers)

## 视觉骨架
- MoD 跳层机制示意
- early exit 路由图

## 可复用到
- MoD 原理速查介绍页
- 深度维度稀疏机制展开

## 不适合复用的场景
- GEMM 瓶颈分析页
- 结果加速数据页
