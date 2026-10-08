---
章节标识: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.05
所属deck: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c
章节序号: 5
章节角色: method
标题: TBS 模式与编解码架构
页码范围: [15, 28]
页数: 14
页ID列表: [slide_15, slide_16, slide_17, slide_18, slide_19, slide_20, slide_21, slide_22, slide_23, slide_24, slide_25, slide_26, slide_27, slide_28]
章节叙事: 全 deck 方法核心。先提出可转置分块稀疏模式 TBS，再论证现有存储格式无法支持转置，进而给出自适应编解码格式与 I/O-aware 可配置架构，末尾用块间/块内调度落地为完整加速方案。
页间关系: ["slide 15 → slide 16: 由本章目录/议程切入，引出 TBS 稀疏模式主张", "slide 16 → slide 17: 由 TBS 概念定义过渡到 TS(N=2,M=4) 转置示意图", "slide 17 → slide 18: 由 TBS 模式细节转到与其他 N:M 稀疏模式对比", "slide 18 → slide 19: 由模式对比引出现有存储格式的短板", "slide 19 → slide 20: 由存储格式问题过渡到 GPU SM/寄存器硬件背景", "slide 20 → slide 21: 由 GPU 硬件层级引出存储格式的核心挑战", "slide 21 → slide 22: 由挑战陈述过渡到编解码方案的结构示意图", "slide 22 → slide 23: 由编解码示意图过渡到自适应编解码架构的即时能力", "slide 23 → slide 24: 由架构能力概述深入到 flag 编码/数据格式细节", "slide 24 → slide 25: 由编码格式转到 I/O-aware 可配置架构设计", "slide 25 → slide 26: 由可配置架构过渡到块间调度机制", "slide 26 → slide 27: 由块间调度过渡到块内调度机制", "slide 27 → slide 28: 延续块内调度，进一步细化调度实现"]
适合复用场景: [需要「先提模式再补硬件存储方案」的 method 章节, 论证稀疏/量化模式与 GPU 存储格式协同设计的章节, 含编解码架构 + 多级调度的系统方法章节, 需与多种同类方案横向对比来立论的方法章节]
不适合复用场景: [研究不涉及 GPU/硬件存储的纯算法章节, 只需单页讲清方法、无需多级展开的场景, 无对比基线、缺硬件背景铺垫的方法章节, 章节内不含调度/编解码细节的浅层方法]
在deck中的位置: 第 5 章 method 核心，承接 background/motivation，为后续实验章节提供被验证对象
分析状态: claude-opus-4-8
---

# section 5: TBS 模式与编解码架构

## 在 deck 中的位置
第 5 章 method 核心，承接 background/motivation，为后续实验章节提供被验证对象

## 章内 slide 间的关系
- slide 15 → slide 16: 由本章目录/议程切入，引出 TBS 稀疏模式主张
- slide 16 → slide 17: 由 TBS 概念定义过渡到 TS(N=2,M=4) 转置示意图
- slide 17 → slide 18: 由 TBS 模式细节转到与其他 N:M 稀疏模式对比
- slide 18 → slide 19: 由模式对比引出现有存储格式的短板
- slide 19 → slide 20: 由存储格式问题过渡到 GPU SM/寄存器硬件背景
- slide 20 → slide 21: 由 GPU 硬件层级引出存储格式的核心挑战
- slide 21 → slide 22: 由挑战陈述过渡到编解码方案的结构示意图
- slide 22 → slide 23: 由编解码示意图过渡到自适应编解码架构的即时能力
- slide 23 → slide 24: 由架构能力概述深入到 flag 编码/数据格式细节
- slide 24 → slide 25: 由编码格式转到 I/O-aware 可配置架构设计
- slide 25 → slide 26: 由可配置架构过渡到块间调度机制
- slide 26 → slide 27: 由块间调度过渡到块内调度机制
- slide 27 → slide 28: 延续块内调度，进一步细化调度实现

## 整章可复用的场景
- 需要「先提模式再补硬件存储方案」的 method 章节
- 论证稀疏/量化模式与 GPU 存储格式协同设计的章节
- 含编解码架构 + 多级调度的系统方法章节
- 需与多种同类方案横向对比来立论的方法章节

## 不适合复用的场景
- 研究不涉及 GPU/硬件存储的纯算法章节
- 只需单页讲清方法、无需多级展开的场景
- 无对比基线、缺硬件背景铺垫的方法章节
- 章节内不含调度/编解码细节的浅层方法
