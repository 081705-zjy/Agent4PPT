---
章节标识: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.04
所属deck: tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c
章节序号: 4
章节角色: problem
标题: 反向转置的痛点
页码范围: [11, 14]
页数: 4
页ID列表: [slide_11, slide_12, slide_13, slide_14]
章节叙事: "承接背景章，聚焦训练反向阶段的核心痛点：N:M 稀疏前向可加速，但转置后稀疏结构被破坏，反向难复用，为后文 TBS 可转置模式立靶。"
页间关系: ["slide 11 → slide 12: 由目录切入，落到 dense baseline 性能基准", "slide 12 → slide 13: 由 baseline 引出权重矩阵乘 W 的稀疏化表达", "slide 13 → slide 14: 由稀疏矩阵乘展开到 forward 计算，暗示反向转置断点"]
适合复用场景: ["论证 N:M 稀疏『前向可加速、反向难转置』矛盾的 problem 章", 需以 dense baseline 对比引出稀疏瓶颈的动机段, 训练全流程稀疏加速类工作的痛点铺垫]
不适合复用场景: [只做推理稀疏、不涉及反向传播的主题, 非张量核/GPU 稀疏硬件方向, 无 dense baseline 对比数据可填充时]
在deck中的位置: 第 4 章 problem，紧跟 background，为方法章 TBS 铺垫
分析状态: claude-opus-4-8
---

# section 4: 反向转置的痛点

## 在 deck 中的位置
第 4 章 problem，紧跟 background，为方法章 TBS 铺垫

## 章内 slide 间的关系
- slide 11 → slide 12: 由目录切入，落到 dense baseline 性能基准
- slide 12 → slide 13: 由 baseline 引出权重矩阵乘 W 的稀疏化表达
- slide 13 → slide 14: 由稀疏矩阵乘展开到 forward 计算，暗示反向转置断点

## 整章可复用的场景
- 论证 N:M 稀疏『前向可加速、反向难转置』矛盾的 problem 章
- 需以 dense baseline 对比引出稀疏瓶颈的动机段
- 训练全流程稀疏加速类工作的痛点铺垫

## 不适合复用的场景
- 只做推理稀疏、不涉及反向传播的主题
- 非张量核/GPU 稀疏硬件方向
- 无 dense baseline 对比数据可填充时
