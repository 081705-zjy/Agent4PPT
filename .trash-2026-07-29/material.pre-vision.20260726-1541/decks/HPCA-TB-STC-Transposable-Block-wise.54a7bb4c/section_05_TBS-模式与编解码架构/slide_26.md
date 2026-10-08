---
页标识: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_26"
所属章节: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.05"
所属deck: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c"
页序号: 26
源文件: "templates/本组论文与科研成果/HPCA  TB-STC Transposable Block-wise.pptx"
页面角色: "content_candidate"
标题: "块间调度（Inter-block scheduling）"
核心论断: "块间调度通过重排稀疏块提升负载均衡"
本页讲什么: "本页讲解 Inter-block scheduling 的 Key idea：在块级别对稀疏块进行调度与重排，均衡不同计算单元的负载、减少访存冲突，是 I/O-aware 架构落地加速的第一层调度机制。"
关键文字: "[Inter-block scheduling, Key idea]"
视觉骨架: "[块间调度示意图, 块重排数据流]"
资源ID列表: "[tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_26.asset.01, tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_26.asset.02]"
适合复用场景: "[加速器块级调度机制页, 负载均衡调度图解页]"
不适合复用场景: "[稀疏模式定义页, 存储格式缺陷页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题", "内容": "块间调度（Inter-block scheduling）"}
  - {"位置": "下方主体", "内容": "Key idea 说明 + 块重排示意图"}
alternate_claims:
  - "块级调度可减少访存冲突"
  - "是 I/O-aware 架构的第一层调度机制"
layout_tag: "block_diagram"
---
# slide 26: 块间调度（Inter-block scheduling）

**核心论断**: 块间调度通过重排稀疏块提升负载均衡

## 本页讲什么
本页讲解 Inter-block scheduling 的 Key idea：在块级别对稀疏块进行调度与重排，均衡不同计算单元的负载、减少访存冲突，是 I/O-aware 架构落地加速的第一层调度机制。

## 关键文字片段
- Inter-block scheduling
- Key idea

## 视觉骨架
- 块间调度示意图
- 块重排数据流

## 可复用到
- 加速器块级调度机制页
- 负载均衡调度图解页

## 不适合复用的场景
- 稀疏模式定义页
- 存储格式缺陷页
