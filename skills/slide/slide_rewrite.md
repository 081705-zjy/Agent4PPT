# Slide Rewrite

Purpose: turn the reuse-first draft into final slide copy, proof composition,
and a renderable visual plan.

## Inputs

- `idea-analysis.json` — provides `slide_writing_rules`, `technical_depth_policy`,
  `citation_policy`, `audience`, `style_signature`. These are the **hard
  constraints** every rewrite must follow.
- `reuse-first-outline.json` / `outline.json`
- `slide-plan.json` (or `draft-assembly-plan.json`)
- `gap-cards.json` — per-page must_replace / must_remove / must_add / evidence_needed
- `gap-research-results.json` — Claude-curated facts/citations to inject
- `source-relevance.json` (project pdf/excel/image/doc analyses) — `可引用片段`
  / `数据洞察` / `实验结果` to use as supporting evidence
- `slide-matches.json` — source PPTX slide bindings
- `template-library-candidates.json`

## Outputs

- `slide-composition.json` — final per-page copy + proof composition
- `manuscript.md` — speaker manuscript (paragraphs per page, derived from
  the speaker-notes that DRAFT_ASSEMBLY already wrote)
- `visual-plan.json` — chart specs / image bindings / asset paths

## brief 字段如何驱动 rewrite (Phase E.A 接线)

`brief.slide_writing_rules` 是**全局硬规则**, 每页 rewrite 时都要遵守:

| brief 字段 | 落地处 |
|---|---|
| `slide_writing_rules.title_rule` | 标题：长度 / 结构 / 是否允许动词 |
| `slide_writing_rules.claim_rule` | 核心论断：必须断言式 / 字数 / 是否允许疑问句 |
| `slide_writing_rules.body_rule` | 正文：bullet 数量 / 缩进 / 是否允许长段 |
| `slide_writing_rules.page_pattern_rule` | 同 chapter 内页面节奏一致性 |
| `slide_writing_rules.evidence_rule` | 数据展示规范（含单位 / 对比 baseline / 来源标注） |
| `slide_writing_rules.citation_rule` | 引用文献插入位置 / 格式 |

`brief.technical_depth_policy` 控制每页深度边界:

| policy 字段 | 落地行为 |
|---|---|
| `assumed_known` | 不要解释这些概念 (听众已知) |
| `must_explain_once` | 整 deck 第一次出现时必须有简短定义页 |
| `deep_dive_allowed_for` | 这些主题可以详细展开 |
| `keep_conceptual_for` | 这些主题保持概念层不下沉到代码/公式 |
| `avoid_or_sanitize` | 这些主题必须脱敏或回避 |

`brief.citation_policy` 决定每页引用呈现方式 (脚注 / inline / 末尾参考列表)。

`brief.audience` 决定术语取舍：
- audience.level=expert → 直接用术语, 不展开
- audience.level=novice → 第一次出现要解释
- audience.what_they_care_about → 重点页要呼应这些点

## Rules

- Preserve the approved slide count and order from outline.
- **每页 rewrite 时必须显式说明本页是否遵守了 `slide_writing_rules` 各 sub-rule**
  (在 slide-composition.json 加 `compliance_check: {title_rule, claim_rule, ...}`)
- **每页若涉及 `claim_status_plan` 中的 claim, 必须从 `gap-research-results.json`
  或 `source-relevance.json.可引用片段` 引用具体证据**, 不允许只是断言而无支撑
- **每页若涉及 `technical_depth_policy.avoid_or_sanitize`** 中的内容，必须脱敏处理
  (改名 / 去具体数据 / 概念化), 在 compliance_check 中标注 `sanitized: true`
- Use project source PPT pages, extracted figures, charts, and tables as first-class
  evidence candidates when their topic, claim, object, caption, and source context
  match the current slide.
- Use topic templates for narrative logic, page structure, component relationships,
  image explanation, and density. Direct copied content is allowed only after semantic
  audit; otherwise rewrite labels, metrics, citations, and conclusions.
- Keep `templates/basic` out of content decisions. Basic identity is applied later in
  `STYLE_UNIFICATION`.
- Do not invent experiment data, paper results, system names, or citations.
- For every body slide, define the proof composition: claim, evidence need, primary
  visual role, source lineage, and unresolved risks.
- Hydrate approved source assets into `visual-plan.json.assets` so `RENDER` can bind
  real PPT/source images instead of fixed internal components.
- Visible text should be final presentation copy, not template text or raw source text.
