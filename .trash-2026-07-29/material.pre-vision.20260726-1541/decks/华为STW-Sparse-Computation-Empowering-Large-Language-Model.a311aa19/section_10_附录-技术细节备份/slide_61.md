---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_61"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 61
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Technique 3: Compilation Tuning 参数"
核心论断: "编译调优针对不同 M/N/K 形状选择最优实现"
本页讲什么: "展开第三项技术 Compilation Tuning:针对不同的矩阵形状(如 M=32、K=4096、N=11008 及 M=3 等)进行编译层面的调优,为不同工作负载匹配最优 kernel 实现。"
关键文字: "[\"Technique 3: Compilation Tuning\", M=32, K=4096, N=11008, M=3]"
视觉骨架: "[矩阵形状参数标注, 编译调优流程/映射示意]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_61.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_61.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_61.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_61.asset.04]"
适合复用场景: "[编译调优技术展开页, kernel 形状适配介绍]"
不适合复用场景: "[理论工作引入页, MoD 原理速查页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "顶部标题", "内容": "Technique 3: Compilation Tuning"}
  - {"位置": "主体", "内容": "矩阵形状参数(M/N/K)与编译调优映射示意"}
alternate_claims:
layout_tag: "block_diagram"
---
# slide 61: Technique 3: Compilation Tuning 参数

**核心论断**: 编译调优针对不同 M/N/K 形状选择最优实现

## 本页讲什么
展开第三项技术 Compilation Tuning:针对不同的矩阵形状(如 M=32、K=4096、N=11008 及 M=3 等)进行编译层面的调优,为不同工作负载匹配最优 kernel 实现。

## 关键文字片段
- Technique 3: Compilation Tuning
- M=32
- K=4096
- N=11008
- M=3

## 视觉骨架
- 矩阵形状参数标注
- 编译调优流程/映射示意

## 可复用到
- 编译调优技术展开页
- kernel 形状适配介绍

## 不适合复用的场景
- 理论工作引入页
- MoD 原理速查页
