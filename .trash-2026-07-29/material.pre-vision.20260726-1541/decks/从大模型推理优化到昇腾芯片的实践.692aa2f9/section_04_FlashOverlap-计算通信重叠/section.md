---
章节标识: tpl.主题学术报告.从大模型推理优化到昇腾芯片的实践.692aa2f9.sec.04
所属deck: tpl.主题学术报告.从大模型推理优化到昇腾芯片的实践.692aa2f9
章节序号: 4
章节角色: method
标题: FlashOverlap 计算通信重叠
页码范围: [12, 22]
页数: 11
页ID列表: [slide_12, slide_13, slide_14, slide_15, slide_16, slide_17, slide_18, slide_19, slide_20, slide_21, slide_22]
章节叙事: method 首章。先立「分布式推理通信开销不可忽略」这一痛点，再由 GEMM 与通信重叠思路收敛到 FlashOverlap 基于信号的重叠方案，末页给实测效果，为后续 semi-PD 铺路。
页间关系: ["slide 12 → slide 13: 由背景挑战小节页收束到通信开销痛点陈述", "slide 13 → slide 14: 由通信开销问题引出 GEMM 与通信重叠思路", "slide 14 → slide 15: 同一重叠思路的递进展开（承接前页）", "slide 15 → slide 16: 由重叠思路过渡到细粒度、计算无干扰方法要点", "slide 16 → slide 17: 由方法要点引出 FlashOverlap 基于信号方案", "slide 17 → slide 18: FlashOverlap 方案逐层展开（递进）", "slide 18 → slide 19: 继续深入信号驱动重叠的机制细节", "slide 19 → slide 20: FlashOverlap 机制说明延续", "slide 20 → slide 21: FlashOverlap 方案收尾补充", "slide 21 → slide 22: 由方法阐述过渡到重叠效果与测试配置"]
适合复用场景: [论证「分布式推理通信开销不可忽略」的痛点, 计算通信重叠类方法的技术方案讲解章, 问题→思路→方案→效果的方法叙事章, GEMM 与集合通信重叠优化主题]
不适合复用场景: [研究与分布式/多卡通信无关时, 无需 5 页展开方案细节的短篇, 面向非技术受众的高层汇报]
在deck中的位置: 第 4 章，承接背景挑战章，为后续 semi-PD 方案铺垫
分析状态: claude-opus-4-8
---

# section 4: FlashOverlap 计算通信重叠

## 在 deck 中的位置
第 4 章，承接背景挑战章，为后续 semi-PD 方案铺垫

## 章内 slide 间的关系
- slide 12 → slide 13: 由背景挑战小节页收束到通信开销痛点陈述
- slide 13 → slide 14: 由通信开销问题引出 GEMM 与通信重叠思路
- slide 14 → slide 15: 同一重叠思路的递进展开（承接前页）
- slide 15 → slide 16: 由重叠思路过渡到细粒度、计算无干扰方法要点
- slide 16 → slide 17: 由方法要点引出 FlashOverlap 基于信号方案
- slide 17 → slide 18: FlashOverlap 方案逐层展开（递进）
- slide 18 → slide 19: 继续深入信号驱动重叠的机制细节
- slide 19 → slide 20: FlashOverlap 机制说明延续
- slide 20 → slide 21: FlashOverlap 方案收尾补充
- slide 21 → slide 22: 由方法阐述过渡到重叠效果与测试配置

## 整章可复用的场景
- 论证「分布式推理通信开销不可忽略」的痛点
- 计算通信重叠类方法的技术方案讲解章
- 问题→思路→方案→效果的方法叙事章
- GEMM 与集合通信重叠优化主题

## 不适合复用的场景
- 研究与分布式/多卡通信无关时
- 无需 5 页展开方案细节的短篇
- 面向非技术受众的高层汇报
