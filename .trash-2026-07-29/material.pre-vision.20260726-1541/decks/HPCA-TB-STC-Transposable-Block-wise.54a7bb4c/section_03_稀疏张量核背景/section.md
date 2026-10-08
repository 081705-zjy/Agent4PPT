---
章节标识: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.03
所属deck: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c
章节序号: 3
章节角色: background
标题: 稀疏张量核背景
页码范围: [4, 10]
页数: 7
页ID列表: [slide_04, slide_05, slide_06, slide_07, slide_08, slide_09, slide_10]
章节叙事: "为 TBS 方法铺垫问题背景：从 GPU 硬件与稀疏化基础出发，梳理稀疏张量核演进与现有 N:M 稀疏模式，暴露其只支持前向、难以转置的痛点。"
页间关系: ["slide 4 → slide 5: 由 H200 等 GPU 算力硬件引出稀疏化方法这一软件手段", "slide 5 → slide 6: 由稀疏化方法的重要性过渡到稀疏张量核的硬件演进史", "slide 6 → slide 7: 由 Turing→Hopper 硬件演进落到稀疏张量核的具体工作方式", "slide 7 → slide 8: 由稀疏张量核运作机制引出现有稀疏模式的分类", "slide 8 → slide 9: 由现有稀疏模式过渡到其精度/性能指标的横向对比", "slide 9 → slide 10: 由指标对比引出 MatRaptor 等相关稀疏加速工作"]
适合复用场景: ["论证 N:M 稀疏只支持前向的 background 章节", 梳理稀疏张量核硬件演进的技术背景章节, 对比现有稀疏模式优劣的问题铺垫章节, 面向 GPU 稀疏加速的方法类论文背景]
不适合复用场景: [研究主题与稀疏张量核/GPU 加速无关时, 无需回顾硬件演进的纯算法论述, "受众已熟知 N:M 稀疏、无需背景铺垫时", GPU 代次数据（H200/Hopper）已过时时]
在deck中的位置: 第 3 章 background，承 cover/引言，为后续 TBS 方法与格式设计做铺垫
分析状态: claude-opus-4-8
---

# section 3: 稀疏张量核背景

## 在 deck 中的位置
第 3 章 background，承 cover/引言，为后续 TBS 方法与格式设计做铺垫

## 章内 slide 间的关系
- slide 4 → slide 5: 由 H200 等 GPU 算力硬件引出稀疏化方法这一软件手段
- slide 5 → slide 6: 由稀疏化方法的重要性过渡到稀疏张量核的硬件演进史
- slide 6 → slide 7: 由 Turing→Hopper 硬件演进落到稀疏张量核的具体工作方式
- slide 7 → slide 8: 由稀疏张量核运作机制引出现有稀疏模式的分类
- slide 8 → slide 9: 由现有稀疏模式过渡到其精度/性能指标的横向对比
- slide 9 → slide 10: 由指标对比引出 MatRaptor 等相关稀疏加速工作

## 整章可复用的场景
- 论证 N:M 稀疏只支持前向的 background 章节
- 梳理稀疏张量核硬件演进的技术背景章节
- 对比现有稀疏模式优劣的问题铺垫章节
- 面向 GPU 稀疏加速的方法类论文背景

## 不适合复用的场景
- 研究主题与稀疏张量核/GPU 加速无关时
- 无需回顾硬件演进的纯算法论述
- 受众已熟知 N:M 稀疏、无需背景铺垫时
- GPU 代次数据（H200/Hopper）已过时时
