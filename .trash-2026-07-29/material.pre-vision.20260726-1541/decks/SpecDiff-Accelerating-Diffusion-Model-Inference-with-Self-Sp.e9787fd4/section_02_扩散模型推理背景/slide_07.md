---
页标识: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_07"
所属章节: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.sec.02"
所属deck: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4"
页序号: 7
源文件: "templates/本组论文与科研成果/SpecDiff  Accelerating Diffusion Model Inference with Self-Speculation.pptx"
页面角色: "content_candidate"
标题: "缩短输入长度即可加速推理"
核心论断: "Attention 与 FFN 均为 compute-bound，减小 L 即加速"
本页讲什么: "承接上页得出结论：Attention 与 FFN 都是 compute-bound 的，因此减少输入长度 L 就能直接带来加速。这一断言为整章画上句号，也直接指向 SpecDiff 的加速思路，过渡到后续方法。"
关键文字: "[Both Attention and FFN are compute-bound, Reduce input length(L) will speedup]"
视觉骨架: "[compute-bound 结论标注, 加速逻辑箭头示意]"
资源ID列表: "[tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_07.asset.01, tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_07.asset.02]"
适合复用场景: "[加速动机结论 closer 页, compute-bound 到缩短 L 的论证]"
不适合复用场景: "[纯背景概述 opener 页, 含多组 benchmark 的数据页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "closer"
视觉文本层次:
alternate_claims:
layout_tag: "bullet_list_conceptual"
---
# slide 7: 缩短输入长度即可加速推理

**核心论断**: Attention 与 FFN 均为 compute-bound，减小 L 即加速

## 本页讲什么
承接上页得出结论：Attention 与 FFN 都是 compute-bound 的，因此减少输入长度 L 就能直接带来加速。这一断言为整章画上句号，也直接指向 SpecDiff 的加速思路，过渡到后续方法。

## 关键文字片段
- Both Attention and FFN are compute-bound
- Reduce input length(L) will speedup

## 视觉骨架
- compute-bound 结论标注
- 加速逻辑箭头示意

## 可复用到
- 加速动机结论 closer 页
- compute-bound 到缩短 L 的论证

## 不适合复用的场景
- 纯背景概述 opener 页
- 含多组 benchmark 的数据页
