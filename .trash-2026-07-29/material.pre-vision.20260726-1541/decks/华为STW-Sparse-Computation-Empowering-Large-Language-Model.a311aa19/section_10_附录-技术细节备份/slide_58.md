---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_58"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 58
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Unified Maximum 保等价且保精度"
核心论断: "统一最大值保 softmax 数学等价,99.99% 情况保 FP32 精度"
本页讲什么: "回答上页的问题:采用统一最大值(unified maximum)既保持了 softmax 的数学等价性,又在 99.99% 的情况下保证 FP32 计算的精度。以①②两点论证统一最大值方案的可行性。"
关键文字: "[The unified maximum preserves the mathematical equivalence of softmax, \"The unified \\\"max\\\" value guarantees the accuracy of FP32 calculation in 99.99% cases\"]"
视觉骨架: "[①②双结论编号布局, 统一最大值机制示意图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_58.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_58.asset.02, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_58.asset.03, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_58.asset.04]"
适合复用场景: "[优化方案可行性论证页, softmax 精度保证结论页]"
不适合复用场景: "[提出问题的引入页, 系统整体 dataflow 图页]"
上页角色: "chapter_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Unified Maximum 保等价且保精度"}
  - {"位置": "下方主体", "内容": "①②双结论编号 + 统一最大值机制示意图"}
alternate_claims:
  - "统一最大值在 99.99% 情况下保证 FP32 计算精度"
layout_tag: "bullet_list_conceptual"
---
# slide 58: Unified Maximum 保等价且保精度

**核心论断**: 统一最大值保 softmax 数学等价,99.99% 情况保 FP32 精度

## 本页讲什么
回答上页的问题:采用统一最大值(unified maximum)既保持了 softmax 的数学等价性,又在 99.99% 的情况下保证 FP32 计算的精度。以①②两点论证统一最大值方案的可行性。

## 关键文字片段
- The unified maximum preserves the mathematical equivalence of softmax
- The unified "max" value guarantees the accuracy of FP32 calculation in 99.99% cases

## 视觉骨架
- ①②双结论编号布局
- 统一最大值机制示意图

## 可复用到
- 优化方案可行性论证页
- softmax 精度保证结论页

## 不适合复用的场景
- 提出问题的引入页
- 系统整体 dataflow 图页
