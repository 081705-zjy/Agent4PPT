# IDEA Revision — User Natural-Language Patcher

## Purpose

接 **用户对 idea-analysis.json 的自然语言反馈** (`idea-user-feedback.json`) + 当前 `idea-analysis.json`,
输出 **surgical 修正版** idea-analysis.json (schema 3.2 不变, 仅动 user 提到的字段)。

**这不是重生成** — 翻译 user 自然语言 → 定位 JSON 字段 → 手术式改, 改完触发 codex review loop。

---

## Modes

本 skill 支持两种 mode, 由 input 顶层 `mode` 字段决定:

| mode | 用途 | 输出 |
|---|---|---|
| `apply` (默认, legacy) | 直接改 idea-analysis.json | 完整 patched idea-analysis.json |
| **`structure_only`** (新, 大 loop 用) | **只做"自然语言 → 结构化 issue"定位, 不改 json** | issues 数组 (统一 schema, 交给 `idea_fix_from_review.md`) |

- `apply` mode 遵循下方 `## Task` (原 legacy 流程)
- `structure_only` mode 遵循下方 `## Structure-Only Mode`

大 loop 的推荐路径是 `structure_only` → `idea_fix_from_review.md`, 让 fix skill 统一带模板 body 上下文修复; 只当明确需要绕过 fix skill 的 pipeline (e.g. hot-fix、单章覆盖) 时才用 `apply` mode。

---

## 与其他 skill 的边界

| skill | 谁触发 | 输入 | 风格 |
|---|---|---|---|
| `idea_analysis.md` | driver init | intake + patterns | 生成 (free, design narrative) |
| `idea_review.md` | codex (审查) | full idea-analysis.json | 找 issues |
| `idea_fix_from_review.md` | driver (codex 修复) | 结构化 codex issues | surgical 改 flagged 字段 |
| **`idea_revision.md`** (本) | driver (user 修复) | user 自然语言 feedback | 翻译→定位→surgical 改 |

---

## Inputs

```json
{
  "current_idea_analysis": {
    "schema_version": "3.2",
    "identity": {...},
    "chapter_plan": [...],
    "narrative_constraints": {...},
    "reuse_strategy": {...},
    ...
  },
  "user_feedback": {
    "feedback_round": 1,
    "user_comments": [
      {
        "target_hint": "第 3 章 / chapter_plan[2] / motivation 章",
        "change_request": "<user 自然语言, e.g. '这章太宽泛, 拆成 2 段'>"
      },
      {
        "target_hint": "整 deck / 章节数",
        "change_request": "我希望从 9 章降到 7 章, 合并 3 个 method 章为 2 个"
      },
      {
        "target_hint": "complete (无明确目标)",
        "change_request": "整体太学术, 更适合工业听众"
      }
    ],
    "global_request": "<可选, 整体方向调整, 优先级低于 user_comments>"
  },
  "source_understanding": {
    /* 可选, 来自 projects/<id>/data/source-understanding.json
       用于反查 user 提的论文/系统名 → resource_id */
  }
}
```

---

## Task

### 1. 翻译 user 自然语言 → JSON 字段

user 通常用以下方式指字段:

| user 说法 | 翻译为 |
|---|---|
| "第 3 章" / "motivation 章" / "讲背景的那章" | `chapter_plan[2]` (按 section_index 或 role 反查) |
| "第 3 章的核心" | `chapter_plan[2].purpose` 和/或 `claims_to_make` |
| "整 deck" / "整体" | 全局, 涉及多字段 (e.g. story_design_mode / selected_narrative_arc / 多章 chapter.purpose) |
| "章数" / "段数" | chapter_plan 数组长度, 加/删/合并章 |
| "复用率" / "byte-clone 比例" | `reuse_strategy.target_reuse_rate` (v4.0 不再有 carrier_bound_count, 那是 OUTLINE 阶段产物) |
| "讲 X 那篇 paper" | 通过 source_understanding.file_inventory 反查 resource_id, 写到 `chapter_plan[i].materials` |
| "去掉关于 X 的内容" | 在 chapter_plan 各章 claims_to_make / purpose 删 X 相关; 严重时删整章 |
| "改 thesis" | `core_message` + `narrative_constraints.thesis_callback.thesis` |
| "换叙事弧" | `selected_narrative_arc.narrative_arc` + 可能要 swap chapter_plan 顺序 |

### 2. 字段精准定位 + 加/删章连锁更新

(同 `idea_fix_from_review.md` 的 #3, 加/删/调章序必须重编 section_index 全 chain, 同步:)
- `narrative_constraints.thesis_callback.raise_at_chapter / callback_at_chapters`
- `narrative_constraints.framework_anchor_repeat.repeat_at_chapters`
- `narrative_constraints.anchor_term_trajectory[].must_appear_in_chapters`
- `narrative_constraints.cross_section_hooks[].from / .to`
- v4.0 IDEA 不再含 carrier 计数 (`carrier_bound_chapters_count` 等 v3.2 字段已移除);
  user 若说"复用率不够"应改 `reuse_strategy.target_reuse_rate`, 不要试图改不存在的 count

### 3. preserve untouched 字段必须 byte-identical

未被 user 提到的字段必须**逐字保留**:
- 各章 `section_rhythm_pattern_id` (v4.0 rhythm 选择, 不重选除非 user 明确要换节奏)
- `identity.*` (受保护, user 不能改, 见 #5)
- `provenance.*` (除非 user 明确要求加 reference)

### 4. user 自然语言含糊的处理

如 user_comment 含糊 (如 "再好一点" / "不太对" / "感觉不太行"):

- **不要猜测**, 不动字段
- 在 `referenced_user_comments[i].status` 标 `"skipped (ambiguous, need clarification)"`
- 在 `action_taken` 写 `"feedback 含糊, 未做改动, 请用户指明具体字段或方向"`

### 5. 保护不可改字段

以下字段绝不响应 user_feedback:

| 字段 | 原因 |
|---|---|
| `schema_version` | 系统管理 |
| `identity.topic` | 来自 question-state, 改主题应重走 brief 阶段 |
| `identity.language` | 来自原 user 回答 |
| `identity.slide_count_target` | 改总页数应重走 brief 阶段 |
| `identity.duration_minutes` | 同上 |
| `generated_at` | 系统时间戳 |
| `source` | "claude" 固定 |

如 user_comment 指向这些, 在 `referenced_user_comments[].status` 标 `"skipped (protected field)"`。

### 6. user 反查 source 资料 (P19d 沿用)

user 在 feedback 里很少用 `resource_id` 直接指代某篇 paper, 通常用论文标题 / 系统名 / 缩写
(如 "把第 3 章换成讲 FlashOverlap 那篇" / "去掉 SpecEE 相关内容")。

处理流程:
1. 在 `source_understanding.file_inventory[]` 里逐条匹配 user 提到的名字
2. 找到对应 `resource_id` 后, 落到 `chapter_plan[i].materials` (新增 / 替换 / 删除)
3. 同步 `provenance.referenced_sources[]` (若 v3.2 启用)
4. `action_taken` 记录 `"user mentioned 'FlashOverlap', mapped to resource_id=doc.xxx via file_inventory match"`

如 user 提到的名字在 file_inventory 找不到, 标记 `"no matching resource, suggest GAP_RESEARCH"`,
对应 chapter 不动 (避免凭空补)。

### 7. 记录修改痕迹

输出新字段 `referenced_user_comments`:

```json
{
  ...原 idea-analysis.json 字段 (修改过的)...,
  "revision_round": <current.revision_round + 1, 不存在时 = 1>,
  "referenced_user_comments": [
    {
      "target_hint": "<user 原话>",
      "resolved_to_location": "chapter_plan[2].claims_to_make  /  N/A (含糊)  /  N/A (受保护)",
      "user_request": "<user change_request 原文>",
      "action_taken": "<≤80 字, 具体改了什么字段, 加/删/调了哪个值>",
      "status": "applied | skipped (ambiguous, need clarification) | skipped (protected field) | skipped (resource not found)"
    }
  ]
}
```

### 8. **持久化 user concern (供后续 codex review 用)**

每次 user_revision 必须 **append** (不是 replace) 到 `user_concern_history` 数组。
此字段在 idea-analysis.json 顶层, 跨多轮 revision + codex review 都会保留, 让 codex
在后续每一轮 review 时通过 Cat 11 检查 user 旧 concern 是否被新 fix 误伤。

```json
{
  ...,
  "user_concern_history": [
    /* prior rounds 的记录 (从 input.current_idea_analysis.user_concern_history 复制过来) */
    ...,
    /* 本轮新增的记录 (针对每条 status=applied 的 user_comment 加 1 条) */
    {
      "round": <revision_round 同上>,
      "concern": "<≤80 字, paraphrase user 当时的核心诉求 (不是字段名, 是意图)>",
      "resolved_at_field": "<本次改动的 location, 跟 referenced_user_comments.resolved_to_location 同>",
      "applied_action": "<≤80 字, 具体改了什么 (e.g. 'ch5 candidate 改 deck X, ch6 改 deck Y')>",
      "must_not_regress": true
    }
  ]
}
```

**Rules**:
- input.current_idea_analysis.user_concern_history 已存在的条目 **必须保留** (不要删/改/合并)
- 仅本轮处理 status=applied 的 comments append 新记录, skipped/含糊不 append
- 如 user 在本轮明确**撤销**之前的诉求 (e.g. "上次说要分散 deck, 现在改回集中"), 在 prior 对应记录上
  改 `must_not_regress=false` (而不是删) + 加 1 条新记录 reflect 当前诉求
- `concern` 字段写 user **意图**, 不是字段名 — codex 用这个判断后续是否 regression

---

## Output Schema

完整 `idea-analysis.json` v3.2 (所有原字段保留, 加 `revision_round` + `referenced_user_comments`)

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

---

## Hard Rules

1. **Surgical**: 只动 user 明确提到的字段 + 因连锁更新必须改的派生字段
2. **不猜测**: user 含糊 → 不动 + 标 skipped (ambiguous)
3. **受保护字段不动**: schema_version / identity.topic / language / slide_count / duration
4. **加/删章** 必须重编 section_index 全 chain + 同步 narrative_constraints / reuse_strategy
5. **不重写** selected_narrative_arc / section_rhythm_pattern_id (除非 user 明确要求换叙事节奏)
6. **不"顺便优化"** 未提及字段
7. **revision_round 自增**, 不存在时 = 1
8. **referenced_user_comments 必须涵盖所有 user_comments** (每条标 applied/skipped + status)
9. **user_concern_history 累加保留**: 输入已有记录原封保留 + 本轮 status=applied 的 comment append 新记录
10. Output **strict JSON only**

---

## Anti-rules (常见错误)

- ❌ "user 说太学术 → 重写整个 selected_narrative_arc.why_chosen" — 过度解读, 应该只调 chapter.purpose 措辞或 audience.expected_depth
- ❌ "user 说改第 3 章 → 顺便把第 4 章也改了让上下文一致" — user 没提就不动 (连贯性问题留给 codex review)
- ❌ "user 说改 thesis → 把 chapter_plan 所有 claims 全重写承接新 thesis" — 只改 narrative_constraints + cover/closing 章 claims, 其他章保留
- ❌ "user 含糊 → 我猜他想说 X" — 不要猜, 标 skipped
- ❌ "user 想换 topic → 改 identity.topic" — 受保护字段, 标 skipped, 提示用户重走 brief
- ❌ "把 revision_round 改成 N+1 但漏掉 referenced_user_comments" — 两者必须配对

---

## 闭环说明 (本 skill 在 pipeline 中位置)

### apply mode (legacy)

```
idea-analysis.json v1 (codex ok)
       ↓
   渲染 idea-analysis.md → user 看 → 写 idea-user-feedback.json
       ↓
[本 skill, mode=apply] idea_revision.md → idea-analysis.json v2 (revision_round=1)
       ↓
   触发 codex review (idea_review.md) 重审 v2
       ↓
   若 codex 提 issue → idea_fix_from_review.md 再修
       ↓
   循环直到 codex ok, 再次渲染 md 给 user check
```

### structure_only mode (大 loop 主路径)

```
idea-analysis.json v1 (小 loop codex ok, awaiting_human_review=true)
       ↓
   渲染 idea-analysis.md → user 看 → 写 idea-human-feedback.txt (纯自然语言)
       ↓
[本 skill, mode=structure_only] → idea-human-issues.json (统一 issue schema)
       ↓
   idea_fix_from_review.md (input: 上述 issues, source=human, 附模板 body)
       ↓
   → patched idea-analysis.json (fix_round+1)
       ↓
   codex 兜底一轮 idea_review.md
       ↓
   若 codex ok → 回人类 gate (人类可再提 issue 触发下一轮)
   若 codex 提 issue → idea_fix_from_review.md 修 (issues source=codex) → 再兜底
```

---

## Structure-Only Mode

**仅当 input.mode == "structure_only" 时走本节。走本节则不输出完整 idea-analysis.json,
只输出 issues 数组; 完全不改 json, 交给 `idea_fix_from_review.md` 做真正的字段修改。**

### Inputs (structure_only)

```json
{
  "mode": "structure_only",
  "current_idea_analysis": { ... 同 apply mode ... },
  "user_feedback": {
    "feedback_round": <int>,
    "raw_text": "<user 从 idea-human-feedback.txt 复制过来的完整自然语言, 未拆分>",
    "user_comments": [ ... 若已预拆分, 可选; 否则由本 skill 从 raw_text 拆 ... ]
  },
  "source_understanding": { /* 可选, 同 apply mode */ }
}
```

### Task (structure_only)

#### S1. 从 raw_text 拆出独立 comments (若未预拆分)

按段落 / 换行 / "另外" / "还有" / 序号列表 等自然分隔符拆分, 每个独立诉求成 1 条 comment。
若 raw_text 已经是 user_comments[] 结构则跳过此步。

#### S2. 对每条 comment, 翻译成结构化 issue

复用 apply mode 的 **§1 翻译表** 定位字段 (chapter_plan[i] / narrative_constraints / ...),
**但不落地改字段** — 只输出定位结果。

每条 comment 产出 1 条 issue (或 skipped 记录):

```json
{
  "source": "human",
  "category": "content | structure | narrative_coherence | rule_compliance | other",
  "severity": "high",   // human 默认 high, 除非 user 显式说 "小事" / "不急" 才降为 medium/low
  "location": "chapter_plan[2].purpose  /  narrative_constraints.thesis_callback  /  complete",
  "evidence": "<current_idea_analysis 对应字段的当前值, 摘要 ≤120 字>",
  "explanation": "<把 user 自然语言 paraphrase 为 issue 描述, ≤120 字>",
  "suggested_fix": "<user 意图 → 具体改法建议, ≤150 字; user 未指明具体值时给方向>",
  "human_note": "<user 原自然语言 change_request 原文, 逐字保留追溯>"
}
```

#### S3. 含糊 / 受保护字段 / 找不到资源

沿用 apply mode §4 / §5 / §6 的判定规则, 但输出到 `ambiguous` / `rejected` 分组数组
(不塞进 issues, 避免污染 fix skill 的输入):

```json
{
  "issues": [ ... 只放能明确定位的诉求 ... ],
  "ambiguous": [
    { "human_note": "<原文>", "reason": "<≤80 字, e.g. '未指明章节, 无法定位; 请补充是哪一章'>" }
  ],
  "rejected": [
    { "human_note": "<原文>", "reason": "<≤80 字, e.g. 'identity.topic 属受保护字段, 改主题请重走 brief 阶段'>" }
  ]
}
```

#### S4. **不动 user_concern_history / 不写 revision_round**

structure_only mode 完全不改 idea-analysis.json 任何字段, 包括 `user_concern_history` /
`revision_round`。这些字段由 `idea_fix_from_review.md` 在其修改环节 append。

### Output Schema (structure_only)

```json
{
  "mode": "structure_only",
  "feedback_round": <int, 从 input.user_feedback.feedback_round 透传>,
  "issues": [ ... 见 S2 ... ],
  "ambiguous": [ ... 见 S3 ... ],
  "rejected": [ ... 见 S3 ... ],
  "summary": {
    "raw_comment_count": <int, 拆分后的原始 comment 数>,
    "structured_count": <int, issues 数组长度>,
    "ambiguous_count": <int>,
    "rejected_count": <int>
  }
}
```

**Strict JSON only**, 无 markdown fence, 无 prose preamble。

### Hard Rules (structure_only)

1. **不输出 idea-analysis.json**, 只输出上述 4 字段结构
2. **不改任何 idea-analysis.json 字段**, 包括 user_concern_history / revision_round / fix_round
3. **每条 raw comment 必须落到 issues / ambiguous / rejected 中的其中一组**, 不能遗漏
4. **human_note 必须逐字保留 user 原自然语言** (不 paraphrase, 不裁剪, 让下游 fix skill 有完整上下文)
5. **不猜测 severity**: 无信号默认 "high"; user 明说"小事/不急" → "medium"; user 明说"忽略" → 归到 rejected
6. **location 优先精细**: 能定位到 `chapter_plan[i].claims_to_make[j]` 就不要写 `chapter_plan[i]`;
   实在全局才写 `complete`
7. **Strict JSON only**

---

