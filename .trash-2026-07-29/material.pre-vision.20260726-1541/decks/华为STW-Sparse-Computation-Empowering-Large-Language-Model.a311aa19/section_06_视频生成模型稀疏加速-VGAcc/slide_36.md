---
页标识: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_36"
所属章节: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.sec.06"
所属deck: "tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19"
页序号: 36
源文件: "templates/课题组全局汇报/华为STW-Sparse Computation Empowering Large Language Model.pptx"
页面角色: "content_candidate"
标题: "Tech.1:全注意力稀疏计算"
核心论断: "非线性算子线性化几乎不损精度即可稀疏计算"
本页讲什么: "承接总览页的第一项技术:全注意力稀疏计算。核心做法是把非线性算子转为线性算子,在几乎不影响精度的前提下实现稀疏计算,并指出Act-Act等环节带来更多计算,通过线性化予以稀疏化削减。"
关键文字: "[非线性算子转为线性算子,精度影响可忽略, Full Attention Sparse Computing, Act-Act 环节带来更多计算]"
视觉骨架: "[全注意力稀疏计算流程图, 非线性转线性算子示意图]"
资源ID列表: "[tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_36.asset.01, tpl.课题组全局汇报.华为STW-Sparse-Computation-Empowering-Large-Language-Model.a311aa19.slide_36.asset.02]"
适合复用场景: "[注意力稀疏化算法层介绍页, 算子线性化的方法细节页]"
不适合复用场景: "[垂域痛点 motivation 开场页, 整章实测收尾页]"
上页角色: "content_candidate"
下页角色: "content_candidate"
分析状态: "claude-opus-4-8"
页在section中的作用: "method_detail"
视觉文本层次:
  - {"位置": "上方标题区", "内容": "Tech.1:全注意力稀疏计算"}
  - {"位置": "中间主体", "内容": "全注意力稀疏计算流程图 + 非线性转线性算子示意图"}
  - {"位置": "下方结论", "内容": "非线性算子线性化几乎不损精度即可稀疏计算"}
alternate_claims:
  - "Act-Act 环节带来更多计算,通过线性化予以稀疏化削减"
layout_tag: "block_diagram"
---
# slide 36: Tech.1:全注意力稀疏计算

**核心论断**: 非线性算子线性化几乎不损精度即可稀疏计算

## 本页讲什么
承接总览页的第一项技术:全注意力稀疏计算。核心做法是把非线性算子转为线性算子,在几乎不影响精度的前提下实现稀疏计算,并指出Act-Act等环节带来更多计算,通过线性化予以稀疏化削减。

## 关键文字片段
- 非线性算子转为线性算子,精度影响可忽略
- Full Attention Sparse Computing
- Act-Act 环节带来更多计算

## 视觉骨架
- 全注意力稀疏计算流程图
- 非线性转线性算子示意图

## 可复用到
- 注意力稀疏化算法层介绍页
- 算子线性化的方法细节页

## 不适合复用的场景
- 垂域痛点 motivation 开场页
- 整章实测收尾页
