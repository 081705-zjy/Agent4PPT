---
章节标识: tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274.sec.02
所属deck: tpl.本组论文与科研成果.SpAct-NDP-Efficient-LLM-Inference-via-Sparse.dc8d7274
章节序号: 2
章节角色: motivation
标题: 研究背景与挑战
页码范围: [2, 9]
页数: 8
页ID列表: [slide_02, slide_03, slide_04, slide_05, slide_06, slide_07, slide_08, slide_09]
章节叙事: 为 SpAct-NDP 方法铺垫：先立 LLM 推理重要性，再拆解 attention/softmax 计算负担，逐一评述量化、动态剪枝等现有压缩路线的局限，导出稀疏激活的必要性。
页间关系: ["slide 2 → slide 3: 由章节分隔封面进入正文，抛出 LLM 受关注的大背景", "slide 3 → slide 4: 由 LLM 崛起收窄到 attention/softmax 的计算瓶颈", "slide 4 → slide 5: 由瓶颈问题转入第一条解法——量化", "slide 5 → slide 6: 由量化过渡到第二条解法——动态剪枝", "slide 6 → slide 7: 从动态剪枝回到静态量化，横向对比压缩策略", "slide 7 → slide 8: 由静态量化并列到剪枝，补全现有方法版图", "slide 8 → slide 9: 由方法评述收束到参考文献，为动机部分作结"]
适合复用场景: [任何需铺陈 LLM 推理压缩背景的 motivation 章节, 需并列评述量化 vs 剪枝等现有方案的综述段, 从计算瓶颈导出新方法必要性的论证结构]
不适合复用场景: [研究主题与 LLM 推理加速无关时, 无需回顾量化/剪枝等前置工作的 deck, 文献引用已过时或不匹配当前领域]
在deck中的位置: 第 2 章，紧跟封面之后，全 deck 方法章节的前置动机
分析状态: claude-opus-4-8
---

# section 2: 研究背景与挑战

## 在 deck 中的位置
第 2 章，紧跟封面之后，全 deck 方法章节的前置动机

## 章内 slide 间的关系
- slide 2 → slide 3: 由章节分隔封面进入正文，抛出 LLM 受关注的大背景
- slide 3 → slide 4: 由 LLM 崛起收窄到 attention/softmax 的计算瓶颈
- slide 4 → slide 5: 由瓶颈问题转入第一条解法——量化
- slide 5 → slide 6: 由量化过渡到第二条解法——动态剪枝
- slide 6 → slide 7: 从动态剪枝回到静态量化，横向对比压缩策略
- slide 7 → slide 8: 由静态量化并列到剪枝，补全现有方法版图
- slide 8 → slide 9: 由方法评述收束到参考文献，为动机部分作结

## 整章可复用的场景
- 任何需铺陈 LLM 推理压缩背景的 motivation 章节
- 需并列评述量化 vs 剪枝等现有方案的综述段
- 从计算瓶颈导出新方法必要性的论证结构

## 不适合复用的场景
- 研究主题与 LLM 推理加速无关时
- 无需回顾量化/剪枝等前置工作的 deck
- 文献引用已过时或不匹配当前领域
