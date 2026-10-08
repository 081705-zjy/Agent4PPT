---
章节标识: tpl.内部组会科研交流.视频生成模型(VGM)技术路径及高效训推.4d4a7714.sec.06
所属deck: tpl.内部组会科研交流.视频生成模型(VGM)技术路径及高效训推.4d4a7714
章节序号: 6
章节角色: framework
标题: 训练框架与训练压缩
页码范围: [21, 30]
页数: 10
页ID列表: [slide_21, slide_22, slide_23, slide_24, slide_25, slide_26, slide_27, slide_28, slide_29, slide_30]
章节叙事: 承接前序方法章节，把视角从模型能力转向训练系统：先铺训练框架与策略，再以稀疏Attention、3D-VAE两条压缩主线论证高效训推，收束回框架整体。
页间关系: ["slide 21 → slide 22: 由VGM技术路线总览切入训练框架主题", "slide 22 → slide 23: 由训练框架概述深入到具体训练策略", "slide 23 → slide 24: 由训练策略转入训练压缩之稀疏Attention", "slide 24 → slide 25: 稀疏Attention机制逐层递进展开", "slide 25 → slide 26: 稀疏Attention继续深化，补充细节或效果", "slide 26 → slide 27: 由稀疏Attention切换到3D-VAE压缩路线", "slide 27 → slide 28: 3D-VAE压缩方法进一步展开", "slide 28 → slide 29: 由具体压缩技术回到训练框架整体", "slide 29 → slide 30: 训练框架层面收束，串联全章要点"]
适合复用场景: [需论证『训练侧高效训推』的framework章节, 并列展开稀疏Attention与3D-VAE两条压缩主线时, 模型能力章节之后承接训练系统的过渡章节, 需要总览+策略+压缩三段式训练叙事时]
不适合复用场景: [研究主题不涉及训练框架或压缩时, 只需推理侧优化、无训练系统内容, 压缩技术非稀疏Attention/3D-VAE路线, 章节篇幅远少于两条压缩主线所需]
在deck中的位置: 第6章，位于方法章节之后、总结展望之前，讲训练侧系统与压缩
分析状态: claude-opus-4-8
---

# section 6: 训练框架与训练压缩

## 在 deck 中的位置
第6章，位于方法章节之后、总结展望之前，讲训练侧系统与压缩

## 章内 slide 间的关系
- slide 21 → slide 22: 由VGM技术路线总览切入训练框架主题
- slide 22 → slide 23: 由训练框架概述深入到具体训练策略
- slide 23 → slide 24: 由训练策略转入训练压缩之稀疏Attention
- slide 24 → slide 25: 稀疏Attention机制逐层递进展开
- slide 25 → slide 26: 稀疏Attention继续深化，补充细节或效果
- slide 26 → slide 27: 由稀疏Attention切换到3D-VAE压缩路线
- slide 27 → slide 28: 3D-VAE压缩方法进一步展开
- slide 28 → slide 29: 由具体压缩技术回到训练框架整体
- slide 29 → slide 30: 训练框架层面收束，串联全章要点

## 整章可复用的场景
- 需论证『训练侧高效训推』的framework章节
- 并列展开稀疏Attention与3D-VAE两条压缩主线时
- 模型能力章节之后承接训练系统的过渡章节
- 需要总览+策略+压缩三段式训练叙事时

## 不适合复用的场景
- 研究主题不涉及训练框架或压缩时
- 只需推理侧优化、无训练系统内容
- 压缩技术非稀疏Attention/3D-VAE路线
- 章节篇幅远少于两条压缩主线所需
