# IDEA Analysis Human Summary — One-Glance Markdown Renderer

## Purpose

读 `idea-analysis.json` (v3.2), 输出 **`idea-analysis.md`** — 给项目负责人/汇报人**一眼判断是否符合要求**的精炼 markdown。

**核心**: user 看完 md (~30 秒), 应该能判断:
1. 故事弧线对不对 (节 1)
2. 每章想说啥对不对 (节 2 表格)
3. 有没有明显风险 (节 3)

不需要 6 节 / 不需要 provenance / 不需要 dump 字段 — 只要 user 能在 30 秒内决策 "OK 继续 / 需要改"。

---

## CRITICAL: Output Format

**你的整个 response 就是 `idea-analysis.md` 的 markdown 内容**。

第一个字符**必须**是 `#` (H1 标题字符)。

**绝对不要**写以下内容:

❌ `"以下是 idea-analysis.md 内容:"`
❌ `"我将输出一份 markdown 总结..."`
❌ ` ```markdown ... ``` ` (不要包 code fence)
❌ `"写入 idea-analysis.md (~1.2 KB)。包含 3 节..."` (这是元描述, 不是真内容)
❌ `"本 md 包含 N 章逻辑速览..."`
❌ 任何 "我会..." / "本文档..." / "下面是..." 类描述性开头

✅ **正确开头示例**:
```
# IDEA · 大模型软硬件协同

> 软硬件协同是大模型推理 10× 提效的唯一现实路径

> 9 章 / 50 页 / 30 分钟 / 学术汇报
...
```

---

## Inputs

```json
{
  "idea_analysis": { /* idea-analysis.json v3.2 完整内容 */ }
}
```

---

## Output Structure (固定 3 节, 目标 1-1.5 KB)

```markdown
# IDEA · {identity.topic}

> {core_message}

> {N}章 / {slide_count_target}页 / {duration_minutes}分钟 / {audience.primary}
> 模板: `{selected_narrative_arc.primary_pattern_id}` ({len(borrowed)} 借鉴)

---

## 故事弧

**{ch1.chapter} → {ch2.chapter} → {ch3.chapter} → ... → {chN.chapter}**

主轴 thesis: "{narrative_constraints.thesis_callback.thesis}"
Framework 锚点: "{narrative_constraints.framework_anchor_repeat.anchor}" (章 {repeat_at_chapters} 复现)

---

## 章节速览

| # | role | 章节 | 一句话核心 | 页 | 节奏 |
|---|------|------|-----------|----|------|
| 1 | cover | {chapter_plan[0].chapter} | {Claude paraphrase ≤25 字} | {pages} | 🎵 `{section_rhythm_pattern_id 短名}` ({source_count}) |
| 2 | agenda | ... | ... | ... | ... |
...

---

## ⚠️ 主要疑虑

(Claude 主诊断, 2-3 条, 越具体越好):

- ⚠️ **{字段名/章名}**: {≤50 字, 描述什么不足, 为何 user 应注意}
- ⚠️ **{...}**: {...}
- (若实在没有重大疑虑, 写 1 条 "✅ 无明显疑虑, 章序/节奏选择/承接均符合 41 hard rules")
```

---

## 渲染规则细节

### 头部 (4 行内)

- H1: `# IDEA · {topic}` (从 identity.topic)
- blockquote 1: core_message 原文
- blockquote 2: `{N}章 / {pages}页 / {duration}分钟 / {audience}` (单行紧凑)
- blockquote 3: 模板信息 `模板: \`{primary_pattern_id}\` ({borrowed count} 借鉴)`

### 节 1: 故事弧 (≤5 行)

- 1 行: 章序流水 (用 → 连接), **粗体**
- 1 行: thesis (用引号包)
- 1 行: framework anchor (若 narrative_constraints 无, 跳过)

### 节 2: 章节速览表 (核心, N 行)

表头固定 6 列: `#` `role` `章节` `一句话核心` `页` `节奏`

- **"一句话核心"** 列: Claude 基于 chapter_plan[i].**purpose** + section_role 提炼 ≤25 字
  **抽象方向短句**, **不照搬 purpose 原文, 不拷 claims_to_make 里任何具体技术词**。优先策略:
  - cover/agenda/closing → 写作用 (如 "立主题" / "5 章导览" / "致谢+展望")
  - motivation → 写"立的痛点轴" (如 "推理 token 量爆炸的能效缺口")
  - framework → 写"提的分解视角" (如 "算法/系统/硬件三层分解" — 抽象 axes, 不写具体 tech)
  - method → 写"本章**抽象方向**" (如 "算法层降算力主要手段" / "硬件层加速器主要方向")
    — **严禁**列具体技术名 (FPGA/ASIC/3D集成/稀疏/量化/投机解码), 这是 IDEA 阶段刻意保留的
    抽象, 具体技术名留给 OUTLINE 阶段读 source 后填到 slide.target_claim
  - discussion/outlook → 写"展望维度" (如 "标准化与产业机会" — 抽象方向, 不列具体公司/方案名)

  **质检 (生成后自查)**: 该列每格扫一遍, 含 "FPGA / ASIC / 稀疏 / 量化 / 投机 / FlightLLM /
  推理引擎 / PD 分离 / 3D 集成" 等具体技术词 → 改成抽象方向再 emit。
- **"节奏"** 列 (v4.0 IDEA 不绑具体 PPT, 只选叙事节奏 pattern):
  - 格式: 🎵 + ` 反引号包 rhythm_pattern_id 短名 ` + `(source_count)`
  - 取 `chapter.section_rhythm_pattern_id` 字段, 短化到 ≤28 字符 (去 prefix 如 "method_" 后保留尾部)
  - 例: `method_framework_recap_then_papers_with_efficiency_summary` → `framework_recap_then_papers`
  - 后面跟 `(N)` 表示该 rhythm 在 corpus 中被多少 deck 实证过 (source_count)
  - **不再含 deck_id / carrier** — 具体 source slide 由 OUTLINE 阶段选

### 节 3: 主要疑虑 (2-3 条)

**Claude 主诊断**, 不是照搬 codex review issues (review 已通过)。诊断点示例:

#### ✅ 该写的疑虑 (优先级从高到低)

- ⚠️ **章命名 placeholder 嫌疑**: ≥1 个 method 章 title 含 "代表性成果一/二" / "方法 N" / "工作 N"
  类 placeholder, 表明 Claude 没用上 source_materials 中的具体术语 — 待 OUTLINE 阶段
  反查 rhythm.carriers 看 slide 后命名才会具体化
  section_narrative 后命名才会具体化
- ⚠️ **method 章 rhythm 选择单一**: ≥3 个 method 章用同一个 `section_rhythm_pattern_id`,
  叙事节奏可能单调 — 但 v4.0 IDEA 不绑具体 PPT, 是否会真的"复用同一 deck" 由 OUTLINE 阶段
  反查 rhythm.carriers 决定
- ⚠️ **某章 expected_pages 偏离 rhythm 推荐**: 例如 motivation 仅 4 页 (rhythm pattern 推荐 8-11 页),
  或 method 单章 12 页超 p75 — 仅当某章页数偏离对应 chapter_role 的合理区间时报
- ⚠️ **总页数**: expected_pages_indicative 是 IDEA 参考值, 由 Stage 1a 根据库容量决定, 无需在此报"总页数偏离"疑虑
- ⚠️ **OPTIONAL 章升维过陡 / 一章塞多轴**: 检查 discussion/outlook/case_study 等 OPTIONAL 章,
  若 claims_to_make 涉及 ≥3 个不同主题轴 (deployment/scale/industry/time/paradigm/domain 等) →
  写疑虑 "ch X 一章塞 N 个不同维度 (列出 axes), 升维过陡风险, OUTLINE 阶段考虑拆章或聚焦单轴"
- ⚠️ **framework-method binding 偏弱**: framework 章定义 N 维分解, method 章命名只 cover ≤ N/2
  (但 codex 已通过的话说明已可接受, 仅作 minor flag)

#### ❌ 不该写的疑虑

- ❌ "总页数 50 vs intake 50 恰好对齐" — 这不是疑虑, 是按设计
- ❌ "总页数偏离 intake.slide_count X%" — v28 起页数由库驱动, 无需硬对齐 intake
- ❌ codex 已修过的 issue (review final_ok=true 后不要重提)
- ❌ cross_section_hooks 数量是否够 (codex review 已查)
- ❌ "claims 缺 baseline / 量化数字" — v28 库驱动生成, 不允许"待补外部数据"; claim 库无支撑就应删或改成能力性描述, 不是 IDEA 缺陷标签

若 chapter_plan + narrative_constraints + rhythm 选择 全面合理, 不要硬找疑虑, 写 1 条 ✅
"无明显疑虑, 章序/复用/承接均符合 41 hard rules"。

---

## Hard Rules

1. **第一个字符必须是 `#`**, 不要任何前置 prose / code fence
2. **3 节固定顺序**: 故事弧 → 章节速览 → 主要疑虑 (不要加 provenance / 不要加 复用策略统计 / 不要加 已知不足以外的节)
3. **章节速览表 6 列固定**: # / role / 章节 / 一句话核心 / 页 / 复用
4. **"一句话核心" ≤25 字**, 不允许照搬 chapter.purpose 字段
5. **疑虑 2-3 条**, 每条 ≤50 字, 必须具体 (引用字段名 / 章名 / 数值)
6. **不写**: provenance / referenced_rule_ids / reuse_strategy 数字统计 / cross_section_hooks 列表 / anti_patterns / anchor_term_trajectory 详情
7. **目标 1-1.5 KB** (9 章 deck 约 1.2 KB), 超过 2 KB = 太啰嗦
8. **数值只能从 idea_analysis 读**, 不允许估算 / 编造
9. **Output 是 raw markdown**, 不要 JSON wrap, 不要 code fence 包裹

---

## Anti-rules (常见错误)

- ❌ 输出元描述 ("我将输出..." / "本 md 包含 N 章...")
- ❌ 包 ` ```markdown ` code fence
- ❌ 把 chapter.purpose / claims_to_make 字段值原文 dump 进表格
- ❌ 加"已知不足"节超过 3 条 (太啰嗦, 让 user 看不完)
- ❌ 加 provenance / candidate 完整列表 (太长, IDEA 阶段不需要审计追溯)
- ❌ 写演讲话术 / 章内详细 outline (那是 OUTLINE 阶段的事)
- ❌ 表格 "复用" 列写完整 deck_id (如 `tpl.topic.对外汇报展示.08e803e6b7eb` 太长) — 取人类可读的 deck_title 截断

---

## 输出大小预期

完整 markdown 1-1.5 KB:
- 头部 (H1 + 3 blockquote): ~150 字
- 节 1 故事弧: ~100 字
- 节 2 章节速览 (9 行 × 80 字): ~720 字
- 节 3 疑虑 (3 条 × 50 字): ~150 字
- **合计: ~1.1 KB**

超过 2 KB 说明你写太啰嗦或加了不该加的节。
