---
章节标识: tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74.sec.03
所属deck: tpl.内部组会科研交流.LOAC-An-Autoregressive-Video-Generation-Accelerator-with-Str.9b94bd74
章节序号: 3
章节角色: motivation
标题: AR+扩散范式演进
页码范围: [7, 18]
页数: 12
页ID列表: [slide_07, slide_08, slide_09, slide_10, slide_11, slide_12, slide_13, slide_14, slide_15, slide_16, slide_17, slide_18, slide_19]
章节叙事: 承接研究背景，梳理视频生成从双向注意力到 AR+扩散范式的演进：论证双向注意力的局限，逐步引出 Diffusion Forcing、Self Forcing 与滑动窗口方案，为后文稀疏注意力/KV 压缩埋下动机。
页间关系: ["slide 7 → slide 8: 由双向注意力视频模型引入，递进展开其机制细节", "slide 8 → slide 9: 由双向注意力的局限过渡到「现在都在探索」的转向", "slide 9 → slide 10: 从探索方向具体落到 Diffusion Forcing 方案", "slide 10 → slide 11: 由 Diffusion Forcing 深入到 Diffusion 本身的展开", "slide 11 → slide 12: 由方案描述转入「主要原因」的归因分析", "slide 12 → slide 13: 由原因分析引出 Self Forcing 应对方案", "slide 13 → slide 14: 由 Self Forcing 过渡到「由于…」的推理与代价", "slide 14 → slide 15: 延续「由于…」逻辑，进一步补充其影响", "slide 15 → slide 16: 由前述铺垫收敛到 AR+Diffusion 范式本体", "slide 16 → slide 17: 由 AR+Diffusion 引出基于滑动窗口的具体做法", "slide 17 → slide 18: 由滑动窗口方案回扣「视频生成模型」整体小结", "slide 18 → slide 19: 由小结页过渡到章节收尾/翻页衔接下一章"]
适合复用场景: [需论证视频生成范式演进的 motivation 章节, 从双向注意力过渡到 AR 生成的背景铺垫, 引出 Diffusion Forcing/Self Forcing 技术脉络, 为稀疏注意力/KV 压缩方案做前提论证]
不适合复用场景: [研究主题与视频生成无关, 无需 AR+扩散范式背景的方法章节, 受众已熟悉该范式演进, 篇幅要求精简、无法容纳 13 页递进]
在deck中的位置: 第 3 章 motivation，紧跟前置背景，为方法章节铺垫
分析状态: claude-opus-4-8
---

# section 3: AR+扩散范式演进

## 在 deck 中的位置
第 3 章 motivation，紧跟前置背景，为方法章节铺垫

## 章内 slide 间的关系
- slide 7 → slide 8: 由双向注意力视频模型引入，递进展开其机制细节
- slide 8 → slide 9: 由双向注意力的局限过渡到「现在都在探索」的转向
- slide 9 → slide 10: 从探索方向具体落到 Diffusion Forcing 方案
- slide 10 → slide 11: 由 Diffusion Forcing 深入到 Diffusion 本身的展开
- slide 11 → slide 12: 由方案描述转入「主要原因」的归因分析
- slide 12 → slide 13: 由原因分析引出 Self Forcing 应对方案
- slide 13 → slide 14: 由 Self Forcing 过渡到「由于…」的推理与代价
- slide 14 → slide 15: 延续「由于…」逻辑，进一步补充其影响
- slide 15 → slide 16: 由前述铺垫收敛到 AR+Diffusion 范式本体
- slide 16 → slide 17: 由 AR+Diffusion 引出基于滑动窗口的具体做法
- slide 17 → slide 18: 由滑动窗口方案回扣「视频生成模型」整体小结
- slide 18 → slide 19: 由小结页过渡到章节收尾/翻页衔接下一章

## 整章可复用的场景
- 需论证视频生成范式演进的 motivation 章节
- 从双向注意力过渡到 AR 生成的背景铺垫
- 引出 Diffusion Forcing/Self Forcing 技术脉络
- 为稀疏注意力/KV 压缩方案做前提论证

## 不适合复用的场景
- 研究主题与视频生成无关
- 无需 AR+扩散范式背景的方法章节
- 受众已熟悉该范式演进
- 篇幅要求精简、无法容纳 13 页递进
