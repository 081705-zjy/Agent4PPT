# Excel / CSV Resource Analysis Skill

分析项目 sources/ 下的 Excel / CSV 表格资料（实验数据 / 财务报表 / 调研结果 / API 调用记录 等）。

## Input

```json
{
  "项目主题": "<brief.topic>",
  "项目主题标签": ["大模型推理", "..."],
  "项目章节": [
    {"序号": 1, "章节名": "开场与议程", "purpose": "..."}
  ],
  "Excel 文件": {
    "文件名": "speedup_results.xlsx",
    "工作表": [
      {
        "表名": "Latency",
        "行数": 24, "列数": 6,
        "列名": ["Model", "Batch", "Prefill_ms", "Decode_ms", "Total_ms", "Hardware"],
        "前 8 行预览": [
          {"Model": "Llama-3-8B", "Batch": 1, "Prefill_ms": 18.5, ...}
        ]
      }
    ]
  }
}
```

## Output (严格 JSON, 中文 key)

```json
{
  "文件名": "speedup_results.xlsx",
  "资料类型": "experimental_data | financial_table | survey_result | log | benchmark | 其他",
  "工作表分析": [
    {
      "表名": "Latency",
      "数据范围": "24 行 × 6 列",
      "列含义": [
        {"列名": "Model", "类型": "category", "示例": "Llama-3-8B / Qwen2-7B"},
        {"列名": "Prefill_ms", "类型": "metric", "单位": "ms"}
      ],
      "关键数值": [
        "Llama-3-8B (Batch=1) Prefill 18.5ms / Decode 23.1ms / Total 41.6ms",
        "在 H100 上 Qwen2-7B Batch=8 时 Total=89.2ms"
      ],
      "数据洞察": "≤120 字, 这张表能论证什么 (断言式)",
      "可复用图表建议": [
        {"建议类型": "stacked_bar", "X 轴": "Model", "Y 轴": "Total_ms",
         "stack_by": "Hardware", "适用场景": "性能对比页"}
      ]
    }
  ],
  "适合章节": [
    {"章节序号": 5, "章节名": "代表性成果", "为什么": "≤40 字"}
  ],
  "不适合章节": [
    {"章节序号": 1, "章节名": "开场与议程", "为什么": "≤40 字"}
  ],
  "主题标签": ["≤5 个原子词"],
  "relevance_score": 0.75,
  "discard_candidate": false
}
```

## 关键约束

- **`关键数值`** 必须是具体数字 + 单位 + 维度, 不允许 "数据较好" 这种空话:
  - ✅ "Qwen2-7B 在 H100 上 Batch=1 Total=41.6ms, 比 baseline 快 1.7×"
  - ❌ "数据显示性能良好"
- **`列含义.类型`** ∈ `{category, metric, identifier, timestamp, text}`, `单位` 仅在
  metric 类型时填.
- **`可复用图表建议`** 给出具体 chart 类型和轴, 不允许 "可以画图" 这种空话.
  - 类型: bar / stacked_bar / grouped_bar / line / scatter / heatmap / pie / table
- `relevance_score` 同 PDF skill 口径.
- 多 sheet 文件每个 sheet 独立分析. 若某 sheet 无价值, 给空 `关键数值` 而不是省略.
- `discard_candidate=true` 当所有 sheet 都 score < 0.3 且 `适合章节` 全空.
- Output strict JSON only.

## Length budget

| 字段 | 上限 |
|---|---|
| 关键数值每条 | 80 字 |
| 数据洞察 | 120 字 |
| 适合章节.为什么 | 40 字 |
