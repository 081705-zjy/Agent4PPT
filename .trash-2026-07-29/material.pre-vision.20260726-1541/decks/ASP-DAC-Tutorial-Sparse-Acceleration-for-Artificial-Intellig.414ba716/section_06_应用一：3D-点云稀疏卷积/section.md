---
章节标识: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716.sec.06
所属deck: tpl.本组论文与科研成果.ASP-DAC-Tutorial-Sparse-Acceleration-for-Artificial-Intellig.414ba716
章节序号: 6
章节角色: case_study
标题: 应用一：3D 点云稀疏卷积
页码范围: [35, 48]
页数: 14
页ID列表: [slide_35, slide_36, slide_37, slide_38, slide_39, slide_40, slide_41, slide_42, slide_43, slide_44, slide_45, slide_46, slide_47, slide_48]
章节叙事: deck 首个 case study，用「稠密基线→三组 Observation/Solution→实验」范式落地稀疏卷积，把前文稀疏算子思想具化到 3D 点云硬件加速。
页间关系: ["slide 35 → slide 36: 由论文封面进入点云应用背景与方法综述", "slide 36 → slide 37: 由应用背景引出 Dense Computing 稠密基线（feature×weight）", "slide 37 → slide 38: 由稠密基线暴露 Observation 1（冗余加载）", "slide 38 → slide 39: Observation 1 延展，深挖冗余加载开销", "slide 39 → slide 40: 由问题转入 Solution 1（Coded-CSR 格式映射存储）", "slide 40 → slide 41: 由解法引出 Observation 2（顺序算 FGMS 利用率低）", "slide 41 → slide 42: Observation 2 延展，强调硬件 under-utilization", "slide 42 → slide 43: 由问题转入 Solution 2（indicator 辅助 FGMS 融合）", "slide 43 → slide 44: 由解法引出 Observation 3", "slide 44 → slide 45: Observation 3 延展补充", "slide 45 → slide 46: 由问题转入 Solution 3", "slide 46 → slide 47: 由方法转入端到端实验（超 TorchSparse 1.64x/1.23x）", "slide 47 → slide 48: 由端到端结果转入消融与补充实验"]
适合复用场景: [需展示「稠密基线→观察→解法→实验」范式的算法优化章节, 任何点云/稀疏卷积硬件加速的 case study, 以多组 Observation/Solution 递进论证的技术章节, 需体现算子级问题定位与格式/调度优化的工作]
不适合复用场景: [研究与稀疏卷积/点云无关时, 只需单点结论、无需递进论证的短章节, 缺少可复现加速比数据支撑时, 面向非硬件/系统受众的高层综述]
在deck中的位置: 第 6 章，方法/思想铺垫后首个代表性工作，开启系列 case study。
分析状态: claude-opus-4-8
---

# section 6: 应用一：3D 点云稀疏卷积

## 在 deck 中的位置
第 6 章，方法/思想铺垫后首个代表性工作，开启系列 case study。

## 章内 slide 间的关系
- slide 35 → slide 36: 由论文封面进入点云应用背景与方法综述
- slide 36 → slide 37: 由应用背景引出 Dense Computing 稠密基线（feature×weight）
- slide 37 → slide 38: 由稠密基线暴露 Observation 1（冗余加载）
- slide 38 → slide 39: Observation 1 延展，深挖冗余加载开销
- slide 39 → slide 40: 由问题转入 Solution 1（Coded-CSR 格式映射存储）
- slide 40 → slide 41: 由解法引出 Observation 2（顺序算 FGMS 利用率低）
- slide 41 → slide 42: Observation 2 延展，强调硬件 under-utilization
- slide 42 → slide 43: 由问题转入 Solution 2（indicator 辅助 FGMS 融合）
- slide 43 → slide 44: 由解法引出 Observation 3
- slide 44 → slide 45: Observation 3 延展补充
- slide 45 → slide 46: 由问题转入 Solution 3
- slide 46 → slide 47: 由方法转入端到端实验（超 TorchSparse 1.64x/1.23x）
- slide 47 → slide 48: 由端到端结果转入消融与补充实验

## 整章可复用的场景
- 需展示「稠密基线→观察→解法→实验」范式的算法优化章节
- 任何点云/稀疏卷积硬件加速的 case study
- 以多组 Observation/Solution 递进论证的技术章节
- 需体现算子级问题定位与格式/调度优化的工作

## 不适合复用的场景
- 研究与稀疏卷积/点云无关时
- 只需单点结论、无需递进论证的短章节
- 缺少可复现加速比数据支撑时
- 面向非硬件/系统受众的高层综述
