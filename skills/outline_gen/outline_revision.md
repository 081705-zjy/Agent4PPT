# OUTLINE Revision — User Natural-Language Patcher (v2.0)

## Purpose

接 **用户对 outline.json 的自然语言反馈** (`outline-user-feedback.json` 或 `outline-human-feedback.txt`)
+ 当前 `outline.json`, 输出 **surgical 修正版** outline.json 或 **结构化 issues 列表**
(见下方 Modes)。

**这不是重生成** — 翻译 user 自然语言 → 定位 slide/字段 → 手术式改 (apply) 或输出 issue
定位结果 (structure_only), 改完触发 codex review loop。

---

## Modes

本 skill 支持两种 mode, 由 input 顶层 `mode` 字段决定:

| mode | 用途 | 输出 |
|---|---|---|
| `apply` (默认, legacy) | 直接改 outline.json | 完整 patched outline.json |
| **`structure_only`** (新, 大 loop 用) | **只做"自然语言 → 结构化 issue"定位, 不改 json** | issues 数组 (统一 schema, 交给 `outline_fix_from_review.md`) |

- `apply` mode 遵循下方 `## Task` (原 legacy 流程)
- `structure_only` mode 遵循下方 `## Structure-Only Mode`

大 loop 推荐路径是 `structure_only` → `outline_fix_from_review.md`, 让 fix skill 统一带模板
body 上下文修复; 只当明确需要绕过 fix skill 的 pipeline 时才用 `apply` mode。

---

## 与其他 OUTLINE skill 的边界

| skill | 谁触发 | 输入 | 风格 |
|---|---|---|---|
| `outline_chapter_stub.md` | driver Stage 1a | per chapter context | 生成 stub |
| `outline_slide_detail.md` | driver Stage 1b | stub + slide briefs | 生成 detail |
| `outline_review.md` | codex (审查) | full outline.json | 找 issues |
| `outline_fix_from_review.md` | driver (codex 修复) | 结构化 codex issues | surgical 改 flagged 字段 |
| **`outline_revision.md`** (本) | driver (user 修复) | user 自然语言 feedback | 翻译→定位→surgical 改 |

---

## Inputs

```json
{
  "current_outline": {
    "schema_version": "1.0",
    "slides": [...],
    "chapter_to_slide_map": {...},
    "narrative_constraints_realization": {...},
    "provenance": {...},
    "user_concern_history": [...]
  },
  "user_feedback": {
    "feedback_round": 1,
    "user_comments": [
      {
        "target_hint": "第 12 页 / slide 12 / ch4 第 3 张 / 讲 X 的那页",
        "change_request": "<user 自然语言, e.g. '这页太挤, 拆 2 页' / '改 target_claim 不要含数字' / '换 source slide'>"
      }
    ],
    "global_request": "<可选, 整体方向调整 (优先级低于 user_comments)>"
  },
  "idea_analysis": { /* idea-analysis.json — 上游契约, 用作 chapter 反查 */ },
  "source_understanding": { /* 可选, projects/<id>/data/source-understanding.json
                             用于反查 user 提的论文/系统名 → resource_id */ }
}
```

---

## Task

### 1. 翻译 user 自然语言 → slide/字段

user 通常用以下方式指字段:

| user 说法 | 翻译为 |
|---|---|
| "第 12 页" / "slide 12" | `slides[i]` where slide_index=12 |
| "ch4 第 3 张" / "method 章首页" | 按 chapter_to_slide_map[4] + chapter 内 index 反查 |
| "讲 X 的那页" | 按 target_title / target_claim 反查 |
| "ch7 那几页" | `slides[i] for i in chapter_to_slide_map[7]` (整章范围) |
| "framework recap 页" | 按 archetype 含 `framework_overview_*` 反查 |
| "整 deck" / "整体" | 全局 (e.g. 整体风格 / 所有 cover slide 加日期) |
| "页数" / "总页数" | slides 数组长度, 加/删/合并 slide |
| "复用率" / "byte-clone 比例" | 各 slide.source_carrier_resource_kind 统计 |
| "讲 X 那篇 paper 的页" | 通过 source_understanding 反查 resource_id 反查相关 slide |
| "去掉关于 X 的内容" | 在相关 slide 的 target_claim / key_points 删 X |
| "改 claim" | slide.target_claim |
| "换 source slide" | slide.source_resource_ids[0] 重选 from alternates 或 candidate |
| "加 evidence" | slide.needed_evidence append |

### 2. 字段精准定位 + 加/删 slide 连锁更新

同 `outline_fix_from_review.md` 的 #3, 加/删/调 slide 必须重编 slide_index 全 chain, 同步:
- `chapter_to_slide_map` 受影响 chapter range
- `rhythm_adherence_log` 该 chapter 的 page_to_rhythm_node_map / slide_count
- `narrative_constraints_realization` 涉及的 slide_index 引用
- 反向: 若改了 chapter slide 数 → 看是否还符合 expected_pages_indicative ±30%

### 3. preserve untouched 字段必须 byte-identical

未被 user 提到的字段必须**逐字保留**:
- 各 slide 的 `archetype` 数组 (除非 user 明确要换)
- 各 slide 的 `source_resource_ids` 内每条 (除非 user 明确要换 source)
- `identity.*` (受保护)
- `provenance.*` (除非 user 明确要求加 reference)
- 全部 user_concern_history 旧条目

### 4. user 自然语言含糊的处理

如 user_comment 含糊 (如 "再好一点" / "不太对" / "感觉不太行"):

- **不要猜测**, 不动字段
- 在 `referenced_user_comments[i].status` 标 `"skipped (ambiguous, need clarification)"`
- 在 `action_taken` 写 `"feedback 含糊, 未做改动, 请用户指明具体 slide 或方向"`

### 5. 保护不可改字段

以下字段绝不响应 user_feedback:

| 字段 | 原因 |
|---|---|
| `schema_version` | 系统管理 |
| `identity.*` | 来自 IDEA, 改主题/页数 / 受众应回 IDEA 阶段 |
| `idea_analysis.*` (引用) | 上游契约, OUTLINE 不动 |
| `generated_at` | 系统时间戳 |
| `source` | "claude" 固定 |
| `provenance.intake_light_path` | 系统管理 |
| user_concern_history 旧条目 | 只追加, 不改 |

如 user_comment 指向这些, 标 `"skipped (protected field)"`。

### 6. 跨阶段守护: IDEA 阶段 chapter 级 issue 应回 IDEA

若 user_comment 实际是 chapter 级问题 (e.g. "ch7 整章方向不对应该合并到 ch5"), OUTLINE 阶段无法
独立解决 — chapter_plan 是 IDEA 阶段定的。处理:
- 在 `referenced_user_comments[i].status` 标 `"escalate_to_IDEA"`
- action_taken 写 "该反馈涉及 chapter 级结构 (chapter_plan), 应回 IDEA 阶段 user_revision, OUTLINE 暂不动"
- 不做 OUTLINE 侧改动

### 7. user 反查 source 资料 (镜像 idea_revision)

user 在 feedback 里很少用 `resource_id` 直接指代某篇 paper, 通常用论文标题 / 系统名 / 缩写
(如 "把第 12 页 source 换成讲 FlashOverlap 那篇")。处理流程:

1. 在 `source_understanding.file_inventory[]` 里匹配 user 提到的名字
2. 找到对应 `resource_id` 后, 落到 `slide.source_resource_ids` 或 `slide.needed_evidence`
3. 同步 `provenance.referenced_sources[]` (若 schema 启用)
4. `action_taken` 记录 `"user mentioned 'FlashOverlap', mapped to resource_id=doc.xxx"`

如 user 提到的名字找不到, 标 `"no matching resource in library"`, 对应 slide
建议改 target_claim 为能力性描述或 kind=new (v28: 库驱动生成, 不允许待补外部数据).

### 8. 记录修改痕迹

输出新字段 `referenced_user_comments`:

```json
{
  ...原 outline.json 字段 (修改过的)...,
  "revision_round": <current.revision_round + 1, 不存在时 = 1>,
  "referenced_user_comments": [
    {
      "target_hint": "<user 原话>",
      "resolved_to_location": "slides[12].target_claim  /  N/A (含糊)  /  N/A (受保护)  /  escalate_to_IDEA",
      "user_request": "<change_request 原文>",
      "action_taken": "<≤80 字, 具体改了什么>",
      "status": "applied | skipped (ambiguous) | skipped (protected) | skipped (resource not found) | escalate_to_IDEA"
    }
  ]
}
```

### 9. **持久化 user concern (供后续 codex review Cat 10)**

每次 user_revision 必须 **append** (不是 replace) 到 `user_concern_history` 数组, 标
`stage: "OUTLINE"` 区分 IDEA 阶段的 concern:

```json
{
  ...,
  "user_concern_history": [
    /* prior IDEA + prior OUTLINE rounds 记录, 全部保留 */
    ...,
    /* 本轮新增 (针对每条 status=applied 的 user_comment 加 1 条) */
    {
      "stage": "OUTLINE",
      "round": <revision_round 同上>,
      "concern": "<≤80 字, paraphrase user 意图>",
      "resolved_at_field": "<本次改动 location>",
      "applied_action": "<≤80 字, 改了什么>",
      "must_not_regress": true
    }
  ]
}
```

**Rules**:
- prior 已存在条目 (含 IDEA stage 留下的) **必须保留**
- 仅本轮 status=applied 的 comment append, skipped/escalate 不 append
- 若 user 撤销之前的诉求 (e.g. "上次说要拆这页, 现在改回不拆"), 在 prior 对应记录加
  `superseded_at_revision_round: N` (不删) + 加新记录 reflect 当前诉求

---

## Output Schema

完整 `outline.json` v1.0 (所有原字段保留, schema_version 不变, 加 `revision_round` +
`referenced_user_comments` + 累加 `user_concern_history`)

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

---

## Hard Rules

1. **Surgical**: 只动 user 明确提到的字段 + 因连锁更新必须改的派生字段
2. **不猜测**: user 含糊 → 不动 + 标 skipped (ambiguous)
3. **受保护字段不动**: schema_version / identity / idea_analysis 引用 / 系统时间戳
4. **加/删 slide** 必须重编 slide_index 全 chain + 同步 chapter_to_slide_map / rhythm /
   narrative_constraints_realization
5. **不重写** archetype / source_resource_ids 内每条 (除非 user 明确要求换)
6. **不"顺便优化"** 未提及字段
7. **chapter-level 反馈 escalate** 到 IDEA, 不在 OUTLINE 强改
8. **revision_round 自增**, 不存在时 = 1
9. **referenced_user_comments 必须涵盖所有 user_comments** (每条标 applied/skipped/escalate + status)
10. **user_concern_history 累加保留**: 输入已有记录 (含 IDEA stage) 原封保留 + 本轮 applied
    comment append 新记录 (stage="OUTLINE")
11. Output **strict JSON only**

---

## Anti-rules

- ❌ "user 说改第 12 页 → 顺便把第 11/13 页也调一致" — user 没提就不动 (连贯性问题留给 codex review)
- ❌ "user 说太学术 → 重写所有 slide.delivery_hint 风格" — 过度解读, 只改 user 提的
- ❌ "user 含糊 → 我猜他想说 X" — 不要猜, 标 skipped
- ❌ "user 想改 chapter_plan → 改 OUTLINE 不动 IDEA" — 应 escalate, 不在 OUTLINE 硬改 IDEA 决策
- ❌ "把 user_concern_history 旧条目 must_not_regress 改 false 让 codex 通过" — 严禁, supersede
  必须由 user 自己提
- ❌ "user 说改 ch7 单轴 → 直接改 chapter.purpose" — chapter.purpose 是 IDEA 阶段字段, OUTLINE
  只能改 ch7 对应 slides 的 target_claim/key_points (让 slides 围绕新单轴), 不能动 chapter_plan

---

## 闭环说明 (本 skill 在 pipeline 中位置)

### apply mode (legacy)

```
outline.json v1 (codex ok)
       ↓
   渲染 outline.md → user 看 → 写 outline-user-feedback.json
       ↓
[本 skill, mode=apply] outline_revision.md → outline.json v2 (revision_round=1, user_concern_history++)
       ↓
   触发 codex review (outline_review.md) 重审 v2
       (Cat 10 user_concern_regression 守护 IDEA + OUTLINE 累计 concerns)
       ↓
   若 codex 提 issue → outline_fix_from_review.md 再修 (含 regression guard)
       ↓
   循环直到 codex ok, 再次渲染 md 给 user check
```

### structure_only mode (大 loop 主路径)

```
outline.json v1 (小 loop codex ok, awaiting_human_review=true)
       ↓
   渲染 outline.md → user 看 → 写 outline-human-feedback.txt (纯自然语言)
       ↓
[本 skill, mode=structure_only] → outline-human-issues.json (统一 issue schema)
       ↓
   outline_fix_from_review.md (input: 上述 issues, source=human, 附模板 body)
       ↓
   → patched outline.json (fix_round+1)
       ↓
   codex 兜底一轮 outline_review.md
       ↓
   若 codex ok → 回人类 gate (人类可再提 issue 触发下一轮, 大 loop 不限次数)
   若 codex 提 issue → outline_fix_from_review.md 修 (issues source=codex) → 再兜底
```

---

## Structure-Only Mode

**仅当 input.mode == "structure_only" 时走本节。走本节则不输出完整 outline.json,
只输出 issues 数组; 完全不改 json, 交给 `outline_fix_from_review.md` 做真正的字段修改。**

### Inputs (structure_only)

```json
{
  "mode": "structure_only",
  "current_outline": { ... 同 apply mode ... },
  "user_feedback": {
    "feedback_round": <int>,
    "raw_text": "<user 从 outline-human-feedback.txt 复制过来的完整自然语言, 未拆分>",
    "user_comments": [ ... 若已预拆分, 可选; 否则由本 skill 从 raw_text 拆 ... ]
  },
  "idea_analysis": { /* 上游契约, chapter 反查 */ },
  "source_understanding": { /* 可选, 论文/系统名 → resource_id */ }
}
```

### Task (structure_only)

#### S1. 从 raw_text 拆出独立 comments (若未预拆分)

按段落 / 换行 / "另外" / "还有" / 序号列表 等自然分隔符拆分, 每个独立诉求成 1 条 comment。
若 raw_text 已经是 user_comments[] 结构则跳过此步。

#### S2. 对每条 comment, 翻译成结构化 issue

复用 apply mode 的 **§1 翻译表** 定位字段 (slides[i] / chapter_to_slide_map / archetype / ...),
**但不落地改字段** — 只输出定位结果。

每条 comment 产出 1 条 issue (或 skipped 记录):

```json
{
  "source": "human",
  "category": "slide_content | source_matching | structure | narrative_coherence | rule_compliance | other",
  "severity": "high",    // human 默认 high, 除非 user 显式说 "小事" / "不急" 才降为 medium/low
  "location": "slides[12].target_claim  /  chapter_to_slide_map.4  /  complete",
  "evidence": "<current_outline 对应字段的当前值, 摘要 ≤120 字>",
  "explanation": "<把 user 自然语言 paraphrase 为 issue 描述, ≤120 字>",
  "suggested_fix": "<user 意图 → 具体改法建议, ≤150 字; user 未指明具体值时给方向>",
  "human_note": "<user 原自然语言 change_request 原文, 逐字保留追溯>"
}
```

#### S3. 含糊 / 受保护字段 / 找不到资源 / chapter-level escalate

沿用 apply mode §4 / §5 / §6 / §7 的判定规则, 但输出到分组数组 (不塞进 issues, 避免污染
fix skill 的输入):

```json
{
  "issues": [ ... 只放能明确定位到 outline 字段的诉求 ... ],
  "ambiguous": [
    { "human_note": "<原文>", "reason": "<≤80 字, e.g. '未指明 slide, 无法定位'>" }
  ],
  "rejected": [
    { "human_note": "<原文>", "reason": "<≤80 字, e.g. 'identity.slide_count_target 受保护'>" }
  ],
  "escalate_to_idea": [
    { "human_note": "<原文>", "reason": "<≤80 字, e.g. '该反馈涉及 chapter_plan 结构, 应回 IDEA 阶段 revision'>" }
  ]
}
```

#### S4. **不动 user_concern_history / 不写 revision_round**

structure_only mode 完全不改 outline.json 任何字段, 包括 `user_concern_history` /
`revision_round`。这些字段由 `outline_fix_from_review.md` 在其修改环节 append。

### Output Schema (structure_only)

```json
{
  "mode": "structure_only",
  "feedback_round": <int, 从 input.user_feedback.feedback_round 透传>,
  "issues": [ ... 见 S2 ... ],
  "ambiguous": [ ... 见 S3 ... ],
  "rejected": [ ... 见 S3 ... ],
  "escalate_to_idea": [ ... 见 S3 ... ],
  "summary": {
    "raw_comment_count": <int>,
    "structured_count": <int>,
    "ambiguous_count": <int>,
    "rejected_count": <int>,
    "escalate_count": <int>
  }
}
```

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

### Hard Rules (structure_only)

1. **不输出 outline.json**, 只输出上述结构
2. **不改任何 outline.json 字段**, 包括 user_concern_history / revision_round / fix_round
3. **每条 raw comment 必须落到 issues / ambiguous / rejected / escalate_to_idea 中的其中一组**, 不能遗漏
4. **human_note 必须逐字保留 user 原自然语言** (不 paraphrase, 不裁剪, 让下游 fix skill 有完整上下文)
5. **不猜测 severity**: 无信号默认 "high"; user 明说"小事/不急" → "medium"; user 明说"忽略" → 归到 rejected
6. **location 优先精细**: 能定位到 `slides[i].target_claim` 就不要写 `slides[i]`;
   实在全局才写 `complete`
7. **chapter-level 反馈归 escalate_to_idea 组**, 不产 issue (fix skill 无权动 chapter_plan)
8. **Strict JSON only**

---
