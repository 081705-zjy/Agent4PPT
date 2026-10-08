---
页标识: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_14"
所属章节: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.sec.04"
所属deck: "tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c"
页序号: 14
源文件: "templates/本组论文与科研成果/HPCA  TB-STC Transposable Block-wise.pptx"
页面角色: "content_candidate"
标题: "前向矩阵乘的稀疏结构"
核心论断: "前向稀疏结构规整可加速，但转置后将被破坏"
本页讲什么: "本页聚焦 Forward 前向阶段的矩阵乘 W×Input=Output，强调此时权重的 N:M 稀疏结构规整、可直接加速。作为本 section 收尾，为下一章反向阶段「转置破坏稀疏、无法复用」的痛点立靶——前向能做，反向才是问题所在。"
关键文字: "[Forward, W × Input = Output]"
视觉骨架: "[前向矩阵乘示意图, 稀疏权重块标注, Forward 阶段标签]"
资源ID列表: "[tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_14.asset.01, tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_14.asset.02, tpl.本组论文与科研成果.HPCA-TB-STC-Transposable-Block-wise.54a7bb4c.slide_14.asset.03]"
适合复用场景: "[前向稀疏计算讲解页, 引出反向转置痛点的铺垫页]"
不适合复用场景: "[含 baseline 数值的对比页, 多主题混合的总结页]"
上页角色: "content_candidate"
下页角色: "toc_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "closer"
视觉文本层次:
  - {"位置": "上方标签", "内容": "Forward 阶段标识"}
  - {"位置": "中间主体", "内容": "W × Input = Output 矩阵乘示意图，标注 N:M 稀疏权重块"}
alternate_claims:
  - "前向阶段 N:M 稀疏权重结构规整，可直接被稀疏张量核加速"
layout_tag: "block_diagram"
---
# slide 14: 前向矩阵乘的稀疏结构

**核心论断**: 前向稀疏结构规整可加速，但转置后将被破坏

## 本页讲什么
本页聚焦 Forward 前向阶段的矩阵乘 W×Input=Output，强调此时权重的 N:M 稀疏结构规整、可直接加速。作为本 section 收尾，为下一章反向阶段「转置破坏稀疏、无法复用」的痛点立靶——前向能做，反向才是问题所在。

## 关键文字片段
- Forward
- W × Input = Output

## 视觉骨架
- 前向矩阵乘示意图
- 稀疏权重块标注
- Forward 阶段标签

## 可复用到
- 前向稀疏计算讲解页
- 引出反向转置痛点的铺垫页

## 不适合复用的场景
- 含 baseline 数值的对比页
- 多主题混合的总结页
