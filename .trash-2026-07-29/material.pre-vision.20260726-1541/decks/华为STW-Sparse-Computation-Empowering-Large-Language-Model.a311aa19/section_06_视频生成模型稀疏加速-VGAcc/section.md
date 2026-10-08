---
章节标识: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.06
所属deck: tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19
章节序号: 6
章节角色: method
标题: "视频生成模型稀疏加速:VGAcc"
页码范围: [33, 38]
页数: 6
页ID列表: [slide_33, slide_34, slide_35, slide_36, slide_37, slide_38]
章节叙事: 承接算子/硬件层,把稀疏计算下沉到视频生成这一垂域。先立视频生成的高算力痛点,再拆出全注意力稀疏计算与稀疏感知PE两项技术,末页用VGAcc实测收尾,补齐稀疏三层加速的模型层案例。
页间关系: ["slide 33 → slide 34: 由两个视频生成模型实例过渡到其稀疏加速的总体切入", "slide 34 → slide 35: 由稀疏加速的问题定性过渡到利用稀疏降算力开销的机会", "slide 35 → slide 36: 由稀疏机会引出技术1——非线性算子线性化的全注意力稀疏计算", "slide 36 → slide 37: 由算子级技术1过渡到硬件级技术2——稀疏感知PE", "slide 37 → slide 38: 由两项技术过渡到VGAcc实验结果验证"]
适合复用场景: [需论证某垂域模型可用稀疏加速的method章, 算子级+硬件级双技术并列展开的方案章, 视频/扩散生成模型加速的技术介绍, 以实验结果收尾的single-work method章]
不适合复用场景: [研究对象非视频/生成类模型时, 只有单一技术、无双层展开时, 无实测数据支撑收尾页时, 面向非稀疏的加速路线时]
在deck中的位置: 第6章method,前接FlightLLM等硬件章,后接MoE/MoD新范式章
分析状态: claude-opus-4-8
---

# section 6: 视频生成模型稀疏加速:VGAcc

## 在 deck 中的位置
第6章method,前接FlightLLM等硬件章,后接MoE/MoD新范式章

## 章内 slide 间的关系
- slide 33 → slide 34: 由两个视频生成模型实例过渡到其稀疏加速的总体切入
- slide 34 → slide 35: 由稀疏加速的问题定性过渡到利用稀疏降算力开销的机会
- slide 35 → slide 36: 由稀疏机会引出技术1——非线性算子线性化的全注意力稀疏计算
- slide 36 → slide 37: 由算子级技术1过渡到硬件级技术2——稀疏感知PE
- slide 37 → slide 38: 由两项技术过渡到VGAcc实验结果验证

## 整章可复用的场景
- 需论证某垂域模型可用稀疏加速的method章
- 算子级+硬件级双技术并列展开的方案章
- 视频/扩散生成模型加速的技术介绍
- 以实验结果收尾的single-work method章

## 不适合复用的场景
- 研究对象非视频/生成类模型时
- 只有单一技术、无双层展开时
- 无实测数据支撑收尾页时
- 面向非稀疏的加速路线时
