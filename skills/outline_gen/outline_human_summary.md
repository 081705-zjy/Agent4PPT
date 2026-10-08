# OUTLINE Human Summary — One-Glance Markdown Renderer (v1.0)

## Purpose

读 `outline.json` (v1.0), 输出 **`outline.md`** — 给项目负责人/汇报人**一眼判断是否符合要求**的精炼 markdown。

**核心**: user 看完 md (~60 秒, 50 slide 比 8 chapter 略长), 应该能判断:
1. 整体页数节奏对不对 (节 1 概览)
2. **每章每页讲啥对不对** (节 2 表格, 主体)
3. 跨章节奏/回扣是否到位 (节 3)
4. 有没有明显风险 (节 4)

不需要 dump 字段 / 不需要 source 路径详情 / 不需要 provenance — 只要 user 能在 60 秒内决策
"OK 继续 / 需要改"。

---

## CRITICAL: Output Format

**你的整个 response 就是 `outline.md` 的 markdown 内容**。

第一个字符**必须**是 `#` (H1 标题字符)。

**绝对不要**写以下内容:

❌ `"以下是 outline.md 内容:"`
❌ `"我将输出一份 markdown 总结..."`
❌ ` ```markdown ... ``` ` (不要包 code fence)
❌ `"写入 outline.md (~4 KB)。包含 4 节..."` (元描述, 非真内容)
❌ `"本 md 包含 N 章 50 张 slide outline..."`
❌ 任何 "我会..." / "本文档..." / "下面是..." 类描述性开头

✅ **正确开头示例**:
```
# OUTLINE · 大模型软硬件协同研究进展

> 50 slide / 8 章 / codex ok / user concern 2 条守护中
...
```

---

## Inputs

```json
{
  "outline": { /* outline.json v1.0 完整内容 */ }
}
```

---

## Output Structure (固定 4 节, 目标 3-5 KB)

```markdown
# OUTLINE · {identity.topic}

> {一句话整体节奏: e.g. "封面→动机 (7p)→框架 (5p)→3 method 章 (24p)→discussion (8p)→closing (5p)"}

> {N} slide / {chapter_count} 章 / codex {ok|fix-need} / user concern {N} 条守护中
> 模板: `{primary_pattern_id}` · revision_round={N}

---

## 一、整体概览 (页数节奏)

| 章 | role | 章节 | 页数 | rhythm pattern | reuse |
|---|------|------|------|----------------|-------|
| 1 | cover | {chapter} | 1 | (cover) | 🟢 carrier_bound |
| 2 | motivation | {chapter} | 7 | `tokens/J_motivation_pattern` | 🟢 carrier_bound |
| ... |

总 page count: {N} (vs IDEA expected {M}, {±X%})

---

## 二、每章 outline 速览 (主体)

### 章 1 · 封面 (1 slide)
- **slide 1** | cover | `cover_title` | 立主题+课题组身份

### 章 2 · 研究背景 (7 slides, motivation rhythm)
- **slide 2** | motivation | `logo_wall_motivation` | tokens/J 能效鸿沟 (待 GAP 补数字)
- **slide 3** | motivation | `data_chart_with_callout` | 算力供需差距 (待 GAP 补图)
- **slide 4** | motivation | `quantified_chart` | 单层优化收益渐进趋平
- ...
- **slide 8** | motivation | `framework_intro_hook` | 引出软硬件协同分层框架

### 章 3 · 软硬件协同框架 (5 slides, framework rhythm)
- **slide 9** | framework | `framework_overview_layer_stack` | 算法-系统-硬件三层视图 [framework anchor 首现]
- ...

(对每章重复此结构)

---

## 三、节奏与跨章回扣 (narrative_constraints_realization)

### Thesis 回扣
**主轴 thesis**: "{thesis}"
- 章 {raise_at} (slide {N}) 立靶
- 章 {callback_at_chapters} (slides {M, K, L}) 回扣

### Framework 复现
**Framework anchor**: "{anchor}"
- 章 3 (slide {N}) 首现
- 章 4/5/6/7 章首页复现 (slides {a, b, c, d})

### Cross-section hooks
- 章 N 末 → 章 N+1 首: `{hook_type}` — {hook_content ≤30 字}
- (逐 hook 列, 通常 N-1 行)

### Anchor 术语轨迹
- "{anchor 1}" — slides {a, b, c}
- "{anchor 2}" — slides {x, y}

---

## 四、⚠️ 主要疑虑

(Claude 主诊断, 2-4 条, 越具体越好):

- ⚠️ **slide carrier 同质**: ch4/5/6 共 24 slide 中 ≥18 张 top-1 source 锁定同 1 deck section,
  byte-clone 后视觉风格雷同, DRAFT 阶段可考虑 SLIDE_REWRITE 引入 cross-deck 变化
- ⚠️ **N 张 slide 需要文字统一化**: outline 中 X 张 slide 标 style_unification_hint 非空 (涉及
  ch a/b/c), 提醒 SLIDE_REWRITE 阶段做术语/标题/口径统一
- ⚠️ **rhythm node 漏映射**: ch5 的 rhythm pattern 有 N 个 node, OUTLINE 只映射到 M 个 slide
  (跳过 node X), 可能导致章内节奏空缺
- ⚠️ **某章页数偏离**: ch7 设计 8 页但 IDEA expected 7 页 (+14%), 仍在 ±20% 允许范围, 仅作 minor flag

---
```

---

## 渲染规则细节

### 头部 (4-5 行)

- H1: `# OUTLINE · {identity.topic}`
- blockquote 1: 整体节奏一句话 (列出每章 page count 简表)
- blockquote 2: 元信息 (slide 总数 / chapter 数 / codex 状态 / user concern 数 / revision_round)
- blockquote 3: 模板 + revision_round

### 节 1: 整体概览 (表格, N+1 行)

- 表头 6 列: `#` `role` `章节` `页数` `rhythm pattern` `reuse`
- per chapter 1 行
- "页数" 写实际 slide 数, 后括号写 vs IDEA expected (±X%)
- "rhythm pattern" 写 pattern_id 短名 (e.g. `method_framework_recap_papers_summary` → 截 12 字)
- "reuse" 用 emoji + 该 chapter 主导 kind (carrier_bound / matching_fallback / new):
  - 🟢 ≥80% slides carrier_bound
  - 🟡 mixed
  - 🔵 ≥50% slides new

### 节 2: 每章 outline 速览 (核心, 占大头)

per chapter 1 个 h3 节, 内含 N 张 slide bullet list (每 slide 1 行):
- 格式: `- **slide {idx}** | {role} | \`{archetype 主}\` | {target_title 或 简化 target_claim}`
- archetype 显示 top-1 (若多个), 截短到可读
- target_title 优先, 没有用 target_claim 截到 ≤40 字
- 若该 slide 含 style_unification_hint, 末尾加 `(SLIDE_REWRITE 统一 {what})` 简化标记
- 若该 slide 落在 narrative_constraints 关键位 (thesis 立靶/回扣 / framework 首现/复现 / anchor 首现),
  末尾加方括号标 `[thesis 立靶]` / `[framework anchor 首现]` 等

### 节 3: 节奏与跨章回扣

提取 narrative_constraints_realization (若 OUTLINE 有此字段) 或 narrative_constraints (从 idea_analysis):
- Thesis 在哪 slide 立, 哪 slide 回扣
- Framework anchor 在哪 slide 首现, 哪 slide 复现
- Cross-section hooks (从 narrative_constraints.cross_section_hooks)
- Anchor 术语轨迹 (anchor → slide list)

每项简洁, 不超 3 行。

### 节 4: 主要疑虑 (2-4 条, Claude 主诊断)

**Claude 主诊断**, 不是照搬 codex review issues (review 已通过)。诊断点示例:

#### ✅ 该写的疑虑

- ⚠️ **slide carrier 同质度高**: 多 chapter slide top-1 source 锁定同 deck section (≥80% 同源)
- ⚠️ **N 张 slide 待 SLIDE_REWRITE 统一化**: 总 slides 中标 style_unification_hint 非空的数量, 涉及哪些 chapter
- ⚠️ **rhythm node 跳过**: 某 chapter rhythm pattern 的 node_sequence 没全映射到 slide
- ⚠️ **某章页数偏离 expected**: chapter slide 数 vs IDEA expected_pages_indicative 偏 ≥15%
- ⚠️ **archetype 重复**: 某 chapter 内同 archetype 用 ≥3 次, 视觉单调风险
- ⚠️ **closing slide 偏长/短**: closing 2-5 页是合理区间, 超出报疑虑

#### ❌ 不该写的疑虑

- ❌ codex 已通过的 issue (不要重提)
- ❌ "总页数偏离 intake.slide_count" — 已允许 ±20%
- ❌ "claim 缺 baseline / 量化数字" — v28 库驱动生成, 不允许"待补外部数据"; 库无支撑就应直接删/改成能力性描述
- ❌ rhythm pattern 完美对齐 OK 时硬找疑虑

若 outline 全面合理, 不要硬找疑虑, 写 1 条 ✅ "OUTLINE 各项符合 IDEA 约束 + 41 logic rule + 54
archetype rule, 节奏与回扣到位"。

---

## Hard Rules

1. **第一个字符必须是 `#`**, 不要任何前置 prose / code fence
2. **4 节固定顺序**: 概览表 → 每章速览 → 节奏回扣 → 疑虑
3. **节 2 每章子节**: 用 h3 (`### 章 N · {chapter}`), 内含 slide bullet list
4. **slide bullet 格式**: `- **slide {idx}** | {role} | \`{archetype}\` | {title/claim}`
5. **每章页数显示**: 实际数 + 括号 vs IDEA expected (±X%) (若超 ±15% 进疑虑节)
6. **疑虑 2-4 条**, 每条 ≤80 字, 必须具体 (引用 slide_index / chapter / 数值)
7. **不写**: provenance / referenced_rule_ids / rule_relaxed_with_reason / source_resource_ids
   详情 / alternates / delivery_hint / claim_status_link
8. **目标 3-5 KB** (50 slide 约 4 KB), 超过 6 KB = 太啰嗦
9. **数值只能从 outline.json 读**, 不允许估算 / 编造
10. **Output 是 raw markdown**, 不要 JSON wrap, 不要 code fence 包裹

---

## Anti-rules (常见错误)

- ❌ 输出元描述 ("我将输出..." / "本 md 包含 N 章...")
- ❌ 包 ` ```markdown ` code fence
- ❌ 把 slide.target_claim 全文 dump 进表格 (用 title 或 截短 claim)
- ❌ 加 "复用策略统计" / "provenance" / "candidate 完整列表" 等节
- ❌ 写每页 source_resource_ids 完整 deck_id (太长, 截短 deck_title 或 deck 目录名最后 12 字符)
- ❌ 每章子节 (节 2) 写超过 slide 数+2 行 (除非该章必要 narrative 解释)
- ❌ 写 delivery_hint (那是给汇报人的, 非 reviewer 关心点)

---

## 输出大小预期

完整 markdown 3-5 KB:
- 头部 (H1 + 3 blockquote): ~200 字
- 节 1 概览表 (8 行 + header): ~600 字
- 节 2 每章速览 (8 章 × ~5-10 slide × ~80 字): ~2500-3000 字
- 节 3 节奏回扣 (4 段 × ~80 字): ~400 字
- 节 4 疑虑 (3 条 × 80 字): ~250 字
- **合计: ~3.5-4.5 KB**

超过 6 KB 说明你写太啰嗦或加了不该加的节。
