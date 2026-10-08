# Image Resource Analysis Skill

分析项目 sources/ 下的图片资料（PNG / JPG / SVG / 图表截图 / 框架图 / 流程图 / 实验照片 等）。

**多模态读图** —— Claude 直接看图，输出对图片内容的语义理解。

## Input

```json
{
  "项目主题": "<brief.topic>",
  "项目主题标签": ["大模型推理", "..."],
  "项目章节": [...]
}
```

图片本身作为多模态输入提供（Claude API 的 image input）。

## Output (严格 JSON, 中文 key)

```json
{
  "文件名": "framework_diagram.png",
  "图片类型": "framework_diagram | flow_chart | bar_chart | line_chart | scatter_plot | architecture_diagram | screenshot | photo | logo | 其他",
  "视觉内容": "≤120 字, 描述图中实际看到的内容 (含主要元素 + 布局)",
  "数据要点": [
    "≤4 条, 每条 ≤80 字, 图中体现的具体数据/对比/事实",
    "例: 「左侧柱形图显示 Llama-3 在 A100 上 Decode 阶段速度比 Mistral 快 2.1×」"
  ],
  "结构信息": {
    "是否含数据可视化": true,
    "X 轴含义": "Model name",
    "Y 轴含义": "Latency (ms)",
    "图例": ["Baseline", "Ours"],
    "标题或抬头文字": "Decode Latency Comparison",
    "可识别的具体数字": ["41.6", "89.2", "1.7x"]
  },
  "可引用场景": [
    {"章节序号": 5, "章节名": "代表性成果", "如何用": "≤40 字, 该图如何对位本章"}
  ],
  "不适合场景": [
    {"章节序号": 1, "章节名": "开场与议程", "原因": "≤40 字"}
  ],
  "改写或裁剪建议": "≤80 字, 直接用是否合适 / 需不需重画 / 需不需局部裁剪",
  "主题标签": ["≤5 个原子词"],
  "relevance_score": 0.8,
  "discard_candidate": false
}
```

## 关键约束

- **`视觉内容`** 必须是看图后的客观描述, 不要凭文件名猜.
  - ✅ "三层堆叠柱状图, X 轴为 4 个 LLM, Y 轴 token/s, 颜色区分 baseline/ours"
  - ❌ "性能对比图"
- **`数据要点`** 必须含图中**真实可读的数字 / 标签 / 比较关系**:
  - ✅ "Llama-3-8B 上 Ours=178.4 token/s, Baseline=89.2, 加速 2.0×"
  - ❌ "结果显示加速效果"
- **`结构信息.可识别的具体数字`** 是图中文字 / 标签可读出的所有具体数值.
  没有就给 `[]`. 不允许编造.
- **图片标题文字 / 轴标签 / 图例** 必须按图中实际文字填, 不要翻译/改写.
- **`图片类型`** 严格枚举, 找不到合适的归 `其他`.
- **`改写或裁剪建议`**:
  - "可直接复用" — 图清晰, 内容对位本项目
  - "需要重新绘制" — 风格 / 数据 / 标签需要换
  - "建议裁剪左半部分" — 局部可用
  - "不建议复用" — 内容不相关或质量差
- `relevance_score` 同 PDF skill 口径.
- `discard_candidate=true` 当 score < 0.3 且 `可引用场景` 全空.
- 只有 svg 文件需要额外注意: 看到的可能是 vector graphics. 描述其抽象结构而不是底层 path.
- Output strict JSON only.

## Length budget

| 字段 | 上限 |
|---|---|
| 视觉内容 | 120 字 |
| 数据要点每条 | 80 字 |
| 可引用场景.如何用 | 40 字 |
| 改写或裁剪建议 | 80 字 |
