---
页标识: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_10"
所属章节: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.sec.03"
所属deck: "tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4"
页序号: 10
源文件: "templates/本组论文与科研成果/SpecDiff  Accelerating Diffusion Model Inference with Self-Speculation.pptx"
页面角色: "content_candidate"
标题: "Token Merge 合并机制细节"
核心论断: "分类后合并冗余 token 可进一步压缩序列并保留信息"
本页讲什么: "本页承接上一页的 Token Merging 概念，展开合并机制的具体做法：对分类后的 token 执行 Merge 操作，把冗余/相似 token 归并，从而在缩短输入长度(L)的同时尽量保留关键信息，是该路线的方法细节页。"
关键文字: "[\"Related Work: Reduce Input Length (L)\", Token Merge, Classify, Merge, Tokens]"
视觉骨架: "[Token 合并流程图, 分类到合并的步骤示意]"
资源ID列表: "[tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_10.asset.01, tpl.本组论文与科研成果.SpecDiff-Accelerating-Diffusion-Model-Inference-with-Self-Sp.e9787fd4.slide_10.asset.02]"
适合复用场景: "[Token 合并的方法细节展开页, 序列压缩机制的流程说明页]"
不适合复用场景: "[特征缓存路线的方法页, 结果/能效数字对比页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "顶部标题栏", "内容": "Related Work: Reduce Input Length (L)"}
  - {"位置": "下方主体", "内容": "Token Merge 分类→合并流程示意"}
alternate_claims:
layout_tag: "flowchart"
---
# slide 10: Token Merge 合并机制细节

**核心论断**: 分类后合并冗余 token 可进一步压缩序列并保留信息

## 本页讲什么
本页承接上一页的 Token Merging 概念，展开合并机制的具体做法：对分类后的 token 执行 Merge 操作，把冗余/相似 token 归并，从而在缩短输入长度(L)的同时尽量保留关键信息，是该路线的方法细节页。

## 关键文字片段
- Related Work: Reduce Input Length (L)
- Token Merge
- Classify
- Merge
- Tokens

## 视觉骨架
- Token 合并流程图
- 分类到合并的步骤示意

## 可复用到
- Token 合并的方法细节展开页
- 序列压缩机制的流程说明页

## 不适合复用的场景
- 特征缓存路线的方法页
- 结果/能效数字对比页
