---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_57"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.10"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 57
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "chapter_candidate"
标题: "Partial Softmax 的额外更新开销问题"
核心论断: "各 block 最大值不同导致 softmax 需额外更新"
本页讲什么: "展开 partial softmax 的机制:因为不同 block 有不同的最大值,softmax 计算需要额外的更新步骤,带来开销。末尾抛出关键问题——能否对所有 block 使用统一的最大值,承接下一页的解答。"
关键文字: "[Partial softmax, Additional update is due to the different maximums in different blocks, Is it feasible to use a unified maximum for all blocks]"
视觉骨架: "[分 block softmax 计算示意, 额外更新开销标注, 问题式提问框]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_57.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_57.asset.02]"
适合复用场景: "[softmax 优化机制展开页, 抛出优化问题的过渡页]"
不适合复用场景: "[总结型 closer 页, MoE/MoD 原理速查页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "Partial Softmax 的额外更新开销问题"}
  - {"位置": "中间主体", "内容": "分 block softmax 计算示意 + 额外更新开销标注"}
  - {"位置": "底部", "内容": "问题式提问框:能否对所有 block 使用统一最大值"}
alternate_claims:
  - "不同 block 最大值差异是额外更新的根源"
  - "可探索使用统一最大值来消除更新开销"
layout_tag: "block_diagram"
---
# slide 57: Partial Softmax 的额外更新开销问题

**核心论断**: 各 block 最大值不同导致 softmax 需额外更新

## 本页讲什么
展开 partial softmax 的机制:因为不同 block 有不同的最大值,softmax 计算需要额外的更新步骤,带来开销。末尾抛出关键问题——能否对所有 block 使用统一的最大值,承接下一页的解答。

## 关键文字片段
- Partial softmax
- Additional update is due to the different maximums in different blocks
- Is it feasible to use a unified maximum for all blocks

## 视觉骨架
- 分 block softmax 计算示意
- 额外更新开销标注
- 问题式提问框

## 可复用到
- softmax 优化机制展开页
- 抛出优化问题的过渡页

## 不适合复用的场景
- 总结型 closer 页
- MoE/MoD 原理速查页
