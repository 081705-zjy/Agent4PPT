---
页标识: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_20"
所属章节: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.05"
所属deck: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c"
页序号: 20
源文件: "templates/本组论文与科研成果/HPCA  TB-STC Transposable Block-wise.pptx"
页面角色: "content_candidate"
标题: "GPU SM 与存储层次背景"
核心论断: "GPU SM 内存层次决定稀疏访存的硬件约束"
本页讲什么: "本页补充 GPU 硬件背景，介绍 Streaming Multiprocessor（SM）的寄存器文件、Warp 调度器、Operand Collector、FP64/FP32 单元等结构，为理解 I/O-aware 架构与转置访存的硬件代价打基础。"
关键文字: "[GPU Streaming Multiprocessor (SM), Register Files, Warp Scheduler, Operand Collector, FP64 FP32]"
视觉骨架: "[GPU SM 硬件结构框图, 寄存器与调度单元标注]"
资源ID列表: "[tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_20.asset.01, tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_20.asset.02]"
适合复用场景: "[GPU 微架构背景介绍页, 硬件存储层次讲解页]"
不适合复用场景: "[稀疏模式定义页, 端到端加速比结果页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "worker_intro"
视觉文本层次:
  - {"位置": "上方标题", "内容": "GPU SM 与存储层次背景"}
  - {"位置": "下方主体", "内容": "SM 硬件结构框图 (寄存器文件/Warp Scheduler/Operand Collector/FP 单元)"}
alternate_claims:
layout_tag: "block_diagram"
---
# slide 20: GPU SM 与存储层次背景

**核心论断**: GPU SM 内存层次决定稀疏访存的硬件约束

## 本页讲什么
本页补充 GPU 硬件背景，介绍 Streaming Multiprocessor（SM）的寄存器文件、Warp 调度器、Operand Collector、FP64/FP32 单元等结构，为理解 I/O-aware 架构与转置访存的硬件代价打基础。

## 关键文字片段
- GPU Streaming Multiprocessor (SM)
- Register Files
- Warp Scheduler
- Operand Collector
- FP64 FP32

## 视觉骨架
- GPU SM 硬件结构框图
- 寄存器与调度单元标注

## 可复用到
- GPU 微架构背景介绍页
- 硬件存储层次讲解页

## 不适合复用的场景
- 稀疏模式定义页
- 端到端加速比结果页
