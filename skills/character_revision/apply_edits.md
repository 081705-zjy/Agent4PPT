# Character Revision — Apply Gap-Card Edits Skill (v3.0)

## Purpose

给定一张 slide 的**可编辑元素表**（含视觉字段）和 gap_card 里的**修订指令**，
输出 JSON 动作列表，让 Python 用 python-pptx 精确执行。

**v3.0 核心边界（2026-07-29）**：
- ✅ **只改文字内容**（replace_text）
- ✅ **只改文字颜色**（recolor_text — 用于目录页当前章高亮）
- ✅ 可以删段落 / 删整个 shape（remove_bullet / remove_shape）
- ✅ 可以追加段落（append_bullet）
- ❌ **不动图片**（不许出 replace_image 动作）
- ❌ **不动字体名 / 字号**（不许出这类动作，也不许由 replace_text 隐式引起）
- ❌ 不改布局 / 位置 / shape 尺寸

---

## 输入 schema

```json
{
  "slide_index": 15,
  "elements": [
    {
      "id": "shape_0",
      "kind": "shape_meta",
      "position": {"left": 457200, "top": 182880, "width": 8229600, "height": 731520},
      "fill_color": null,
      "line_color": null,
      "is_title": true,
      "has_text": true,
      "is_picture": false
    },
    {
      "id": "para_0.0",
      "kind": "text",
      "text": "SpecEE 效果",
      "char_count": 7,
      "container_id": "shape_0",
      "is_title": true,
      "color": "002060",
      "size_pt": 24.0
    },
    {
      "id": "shape_1",
      "kind": "shape_meta",
      "fill_color": "FFFF00",
      "line_color": "FFC000",
      "is_title": false,
      "has_text": true
    },
    {
      "id": "para_1.0",
      "kind": "text",
      "text": "🎯 编辑标注: 换标题",
      "container_fill": "FFFF00"
    },
    {
      "id": "img_3",
      "kind": "image",
      "desc": "架构图",
      "position": {...}
    }
  ],
  "gap_card": { ... },
  "agenda_directive": { ... }   // 只在目录/章前页才出现
}
```

---

## 输出 schema（严格 JSON）

```json
{
  "actions": [
    {"op": "replace_text", "id": "para_0.0", "text": "SpecEE 加速性能",
     "is_title": true, "original_text": "SpecEE 效果"},
    {"op": "recolor_text", "id": "para_1.2", "color": "000000"},
    {"op": "remove_bullet", "id": "para_2.1"},
    {"op": "append_bullet", "container_id": "shape_2", "text": "推理开销降低 15%"},
    {"op": "remove_shape", "id": "shape_1"}
  ],
  "rationale": "换标题, 高亮第 3 章, 删占位, 删黄框"
}
```

---

## 5 个允许的原子动作

| op | 参数 | 何时用 |
|---|---|---|
| `replace_text` | `id, text, is_title?, original_text?` | 替换段落文字（术语统一/标题改写/must_replace） |
| `recolor_text` | `id, color` (6-hex, 无 #) | 改段落文字色（**目录页高亮当前章 → 000000; 其他 → FFFFFF**） |
| `remove_bullet` | `id` | 删单个段落 |
| `append_bullet` | `container_id, text` | 追加要点（container_id 必须是 `shape_<N>` 且 has_text=true） |
| `remove_shape` | `id` (shape_<N>) | 删整个 shape（黄框、编辑标注框等） |

**禁止**：`replace_image`（图片一律不动）、任何字体或字号修改。

---

## 决策优先级

### 第 1 步：目录/章前页 → 用 agenda_directive
如果 input 有 `agenda_directive` 字段，**遵守它**（详见下面单独章节）。

### 第 2 步：黄色标注框 → `remove_shape`
`fill_color` 或 `line_color` 在 `FFFF00`(纯黄) / `FFC000`(琥珀) 附近，且 shape 内文字含 emoji 或"编辑/待办/TODO/标注/DEBUG"：
→ 出 `{"op": "remove_shape", "id": "shape_N"}`。**不要**再对这个 shape 里的 para 做 replace_text。

### 第 3 步：标题字数守卫
`is_title=true` → 新文字 `char_count` ≤ 原文 × **1.2**。超限会被 Python 拒绝，让你重写。

### 第 4 步：正文改写
`is_title=false` → 新文字 ≤ 原文 × 2。尽量简洁（≤ 30 字/bullet 理想）。

### 第 5 步：must_add → append_bullet
container_id 必须是 elements 里存在的 `shape_<N>` 且 `has_text=true`。**不要往待 remove 的黄框里 append**。

### 第 6 步：must_remove → remove_bullet 或 remove_shape
- 删一条 → remove_bullet
- 删整个警示框 → remove_shape

---

## 硬约束（违反 = 拒绝重试）

1. **只用列表里 5 个 op**。绝不 `replace_image`、`change_font`、`change_size`。
2. **id 只能从 elements 里选**。
3. **is_title 段落新长度 ≤ 原长 × 1.2**（Python 强制守卫）。
4. **remove_shape 优先于 replace_text**：一个 shape 已 remove → 别再动它的 para。
5. **图片不动**：`kind="image"` 的 element 直接跳过。
6. **color 参数是 6-hex-char，无 `#`**：正确 `"000000"`；错误 `"#000000"`。
7. **rationale ≤ 50 字**。

---

## 特殊：目录页 (agenda / chapter_divider)

driver 会在 input 里塞 `agenda_directive`，说明本 slide 是目录页 + 章名列表 + 高亮哪章。

```json
"agenda_directive": {
  "role": "chapter_divider",
  "shared_chapter_list": [
    "01 背景动机",
    "02 跨层次软硬件协同框架",
    "03 算法/模型层代表工作",
    "04 系统层代表工作",
    "05 硬件加速层代表工作",
    "06 讨论与展望"
  ],
  "highlight_chapter_index": 3,      // 1-based; null = 全部黑
  "colors": {
    "highlight": "000000",           // 当前章
    "muted": "FFFFFF"                // 其他章
  }
}
```

### 规则
1. **章名严格照 `shared_chapter_list` 输出**（数量、顺序、措辞均不改）
2. **章名映射到 elements 里的 para**：按 elements 中段落的**出现顺序**依次对应到 shared_chapter_list（第 1 段 → 第 1 章，依此类推）
3. **同时出 replace_text 和 recolor_text**：
   - `replace_text` 把段落文字改成对应章名
   - `recolor_text` 设色：`highlight_chapter_index == N` → 该章 para 用 `colors.highlight`；其他 para 用 `colors.muted`
   - `highlight_chapter_index=null` → 所有段落都用 `colors.highlight`（主 TOC 全黑）
4. **章数 vs 段落数不匹配时**：
   - 段落多于章数 → 多余段落不动（也不删）
   - 章数多于段落数 → 段落全部映射到前 N 章名；无法补齐的章不出 append_bullet（避免破坏原布局）

### 例子：主 TOC（highlight=null 全黑）
```json
{
  "actions": [
    {"op": "replace_text", "id": "para_1.0", "text": "01 背景动机"},
    {"op": "recolor_text", "id": "para_1.0", "color": "000000"},
    {"op": "replace_text", "id": "para_1.1", "text": "02 跨层次软硬件协同框架"},
    {"op": "recolor_text", "id": "para_1.1", "color": "000000"},
    {"op": "replace_text", "id": "para_1.2", "text": "03 算法/模型层代表工作"},
    {"op": "recolor_text", "id": "para_1.2", "color": "000000"},
    {"op": "replace_text", "id": "para_1.3", "text": "04 系统层代表工作"},
    {"op": "recolor_text", "id": "para_1.3", "color": "000000"},
    {"op": "replace_text", "id": "para_1.4", "text": "05 硬件加速层代表工作"},
    {"op": "recolor_text", "id": "para_1.4", "color": "000000"},
    {"op": "replace_text", "id": "para_1.5", "text": "06 讨论与展望"},
    {"op": "recolor_text", "id": "para_1.5", "color": "000000"}
  ],
  "rationale": "主 TOC: 6 章名统一, 全黑"
}
```

### 例子：章前页 highlight=3
```json
{
  "actions": [
    {"op": "replace_text", "id": "para_0.0", "text": "第三章: 算法/模型层代表工作",
     "is_title": true, "original_text": "算法层"},
    {"op": "replace_text", "id": "para_1.0", "text": "01 背景动机"},
    {"op": "recolor_text", "id": "para_1.0", "color": "FFFFFF"},
    {"op": "replace_text", "id": "para_1.1", "text": "02 跨层次软硬件协同框架"},
    {"op": "recolor_text", "id": "para_1.1", "color": "FFFFFF"},
    {"op": "replace_text", "id": "para_1.2", "text": "03 算法/模型层代表工作"},
    {"op": "recolor_text", "id": "para_1.2", "color": "000000"},
    {"op": "replace_text", "id": "para_1.3", "text": "04 系统层代表工作"},
    {"op": "recolor_text", "id": "para_1.3", "color": "FFFFFF"},
    {"op": "replace_text", "id": "para_1.4", "text": "05 硬件加速层代表工作"},
    {"op": "recolor_text", "id": "para_1.4", "color": "FFFFFF"},
    {"op": "replace_text", "id": "para_1.5", "text": "06 讨论与展望"},
    {"op": "recolor_text", "id": "para_1.5", "color": "FFFFFF"}
  ],
  "rationale": "章前 3, 6 章统一, 高亮第 3 章"
}
```

---


---

## 关键: 图文一致性 (source_slide_brief)

如果 input 里有 `source_slide_brief`, 说明这张 draft slide 是从库源 slide byte-clone 来的.
brief 里包含源 slide 的**视觉结构描述**:

```json
"source_slide_brief": {
  "本页讲什么": "抛出主线公式「AI应用算力=芯片算力×稀疏度」...下方三列并列给出计算机视觉(CNN)、图神经网络(GNN)、大模型(Transformer)三类任务...",
  "视觉文本层次": [
    {"位置": "上方蓝色公式条", "内容": "主线等式: AI应用算力 = 芯片算力 × 稀疏..."},
    {"位置": "中部三列 panel", "内容": "CNN / GNN / Transformer 三类任务的 输入→模型→输出 流程"},
    {"位置": "底部 vs. 对比", "内容": "稠密计算 vs 稀疏计算"}
  ],
  "视觉骨架": ["顶部主线公式蓝条", "3 列任务模型并列 panel", "各列输入→模型→输出流程图", "底部 vs. 稠密/稀疏对比"],
  "关键文字": ["AI应用算力 = 芯片算力 × 稀疏（稀疏度不改变模型功能）", "计算机视觉 CNN", ...],
  "适合复用场景": ["稀疏计算研究思路的总纲页", "跨CV/GNN/大模型的方法总览页"],
  "不适合复用场景": ["单一模型的方法细节页", "含具体benchmark数字的结果页"]
}
```

### 硬规则

1. **改文字前必须先看 `本页讲什么` + `视觉文本层次`**:
   识别源 slide 的**语义结构** (这张 slide 是"CV/GNN/LLM 三领域" 还是 "算法/系统/硬件三层"? 还是 "问题→方案→效果"?)

2. **判断 gap 目标是否与源结构匹配**:
   - gap.target_title / target_claim 隐含的语义结构 vs 源 slide 语义结构
   - 若**结构相同** (如源是"三层框架"、gap 也是"三层框架"): 正常改文字
   - 若**结构不同** (如源是"CV/GNN/LLM 三领域"、gap 是"算法/系统/硬件三层"): **拒绝改中部三列的文字**, 只改标题, 保留原文本内容; rationale 里标 `image_text_mismatch: <说明>`

3. **看 `不适合复用场景`**: 如果 gap 目标恰好落在 "不适合" 类别里
   (如源不适合 "单一模型的方法细节页", 而 gap 是要把它改成 "SpecEE 方法详情"),
   → 只做最保守的修改 (标题 + 术语统一), 保留正文原文; rationale 标 `source_reuse_violation: <场景>`

4. **图片 shape 一定不改** (本来就是硬规则, 这里强调): 不出 replace_image 动作;
   如果图文实在不匹配无法救, 出 `remove_shape` 删掉不匹配的图/框, 只保留能对上的文字

### 例子: slide 15 (v26 真实案例)

**Input**:
```json
"gap_card": {
  "target_title": "工作预告: 三条主线对应三层框架",
  "must_replace": ["把'计算机视觉/图神经网络/大模型'换成'算法层/系统层/硬件层'"]
},
"source_slide_brief": {
  "本页讲什么": "...下方三列并列给出计算机视觉(CNN)、图神经网络(GNN)、大模型(Transformer)三类任务, 各配「计算功耗=计算量/功耗（/J）」等能效度量...",
  "视觉文本层次": [
    {"位置": "中部三列 panel", "内容": "CNN / GNN / Transformer 三类任务的输入→模型→输出流程"}
  ],
  "不适合复用场景": ["单一模型的方法细节页"]
}
```

**判断**:
- 源结构 = "CV/GNN/LLM 三类任务" (视觉上是 3 张对应领域的插图 + 各自的输入→模型→输出流程图)
- gap 结构 = "算法/系统/硬件三层" (完全不同的抽象轴)
- 三列 panel 的插图配的是 CV/GNN/LLM 的视觉素材, **改文字成 "算法/系统/硬件" 会图文脱节**

**正确 output**:
```json
{
  "actions": [
    {"op": "replace_text", "id": "para_0.0", "text": "工作预告: 三条主线对应三层框架", "is_title": true, "original_text": "研究思路: 软硬件协同"}
  ],
  "rationale": "image_text_mismatch: 源三列 panel 是 CV/GNN/LLM, 不匹配新'三层'语义, 只改标题, 三列文字+图片保留源样;可考虑上游换源"
}
```

**错误 output** (v3 就是这样的):
```json
{
  "actions": [
    {"op": "replace_text", "id": "para_0.0", "text": "工作预告: 三条主线..."},
    {"op": "replace_text", "id": "para_1.0", "text": "算法层"},       ← 破坏图文
    {"op": "replace_text", "id": "para_1.1", "text": "系统层"},       ← 破坏图文
    {"op": "replace_text", "id": "para_1.2", "text": "硬件层"},       ← 破坏图文
    ...
  ]
}
```

---

## 错误重试

driver 会把失败信息传回：
```
Prior attempt 1/3 failed:
  [action={"op":"replace_text","id":"para_0.0",...}] new text too long: 25 chars vs orig 7 (limit ×1.2)
```
只修失败动作，成功的不重复列（driver 只重跑失败）。

---

## 返回格式硬规则

- 严格 JSON：`{` 开头 `}` 结尾。无 markdown code fence，无前缀说明。
- 顶层字段只有 `actions` 和 `rationale`。
- `actions` 每项只能是 5 个允许 op 之一，不许发明。
- **不许输出**：`comments` / `explain` / `summary` / `notes` 等额外字段。
