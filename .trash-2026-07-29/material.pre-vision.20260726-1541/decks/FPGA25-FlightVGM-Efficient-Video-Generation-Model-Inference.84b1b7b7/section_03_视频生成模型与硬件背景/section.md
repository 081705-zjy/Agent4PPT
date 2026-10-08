---
章节标识: tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7.sec.03
所属deck: tpl.本组论文与科研成果.FPGA25-FlightVGM-Efficient-Video-Generation-Model-Inference.84b1b7b7
章节序号: 3
章节角色: motivation
标题: 视频生成模型与硬件背景
页码范围: [4, 9]
页数: 6
页ID列表: [slide_04, slide_05, slide_06, slide_07, slide_08, slide_09]
章节叙事: 作为方法章节前的背景铺垫：先立起「VGM 推理开销大」这一动机，再从生成式 AI→Sora→VGM 结构→与 LLM 差异→GPU 低精度硬件趋势层层递进，为后文稀疏/混合精度/调度三技术埋下问题伏笔。
页间关系: ["slide 4 → slide 5: 由生成式 AI 大趋势收敛到 Sora 这一视频生成标杆案例", "slide 5 → slide 6: 由 Sora 效果切入 VGM 的内部结构剖析", "slide 6 → slide 7: 由 VGM 结构过渡到 LLM 与 VGM 的计算特性对比", "slide 7 → slide 8: 由模型侧差异转到硬件侧，引出 Blackwell FP4 新精度格式", "slide 8 → slide 9: 由单代新精度扩展到 NVIDIA GPU 的持续演进脉络"]
适合复用场景: [需要论证「视频生成模型推理开销大」的 motivation 章, 从生成式 AI 大势层层收敛到具体模型的背景铺垫, 需对比 LLM 与 VGM 计算特性的技术背景章, 引出 GPU 低精度（FP4）硬件趋势的动机章]
不适合复用场景: [研究主题与视频生成/VGM 无关时, 无需铺垫硬件精度趋势的纯算法章, Sora/Blackwell 等案例已过时时]
在deck中的位置: 第 1 内容章（4-9 页），紧跟 cover/agenda，为方法章铺垫
分析状态: claude-opus-4-8
---

# section 3: 视频生成模型与硬件背景

## 在 deck 中的位置
第 1 内容章（4-9 页），紧跟 cover/agenda，为方法章铺垫

## 章内 slide 间的关系
- slide 4 → slide 5: 由生成式 AI 大趋势收敛到 Sora 这一视频生成标杆案例
- slide 5 → slide 6: 由 Sora 效果切入 VGM 的内部结构剖析
- slide 6 → slide 7: 由 VGM 结构过渡到 LLM 与 VGM 的计算特性对比
- slide 7 → slide 8: 由模型侧差异转到硬件侧，引出 Blackwell FP4 新精度格式
- slide 8 → slide 9: 由单代新精度扩展到 NVIDIA GPU 的持续演进脉络

## 整章可复用的场景
- 需要论证「视频生成模型推理开销大」的 motivation 章
- 从生成式 AI 大势层层收敛到具体模型的背景铺垫
- 需对比 LLM 与 VGM 计算特性的技术背景章
- 引出 GPU 低精度（FP4）硬件趋势的动机章

## 不适合复用的场景
- 研究主题与视频生成/VGM 无关时
- 无需铺垫硬件精度趋势的纯算法章
- Sora/Blackwell 等案例已过时时
