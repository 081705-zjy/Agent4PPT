# Slide Matching Skill (Main Entry — Process Orchestrator)

The **third** of three cascade matching passes. For each target page, output a
**ranked list of 1-3 source slide candidates** following a 3-step process.

This file is the **process orchestrator**. The detailed rules for each step
live in dedicated skill files (loaded together in the same prompt):

| Step | Skill file | Job |
|---|---|---|
| 1. Aspect extraction | `slide_aspect_extraction.md` | Break each target into ≤5 aspects |
| 2. Rank-1 semantic selection | `slide_rank1_semantic.md` | Pick the most on-topic candidate |
| 3. Rank-2/3 gap-based selection | `slide_rank23_gap_based.md` | Fill rank-1's residual_gap |

---

## Inputs

```json
{
  "idea_analysis": {... topic/audience/scenario/slide_count/story_style ...},
  "target_pages": [
    {"target_slide_index": 1, "target_role": "cover", "key_points": [...], "anchor_terms": [...]},
    ...
  ],
  "slide_candidates": [
    {"resource_id": "...", "title": "...", "claim": "...",
     "what_this_slide_explains": "...", "_pool_tier": "strong | same_deck | structural_* | default",
     ...},
    ...
  ],
  "section_matches_brief": [...],
  "previous_picks": [
    {"target_slide_index": 17, "candidates": [{"rank": 1, "resource_id": "...", "deck_id": "..."}]}
  ]
}
```

---

## Process (per target_page)

### Step 1: Extract aspects (per `slide_aspect_extraction.md`)

把 target 拆成 1-5 个 aspects:
```json
{"aspects": [{"aspect_id": "a1", "aspect_text": "...", "aspect_type": "claim|method|data|evidence|context"}]}
```

### Step 2: Pick rank-1 (per `slide_rank1_semantic.md`)

**Semantic-first** — 选语义最对题的 source。版式相似仅作 tie-breaker。
**ADJACENCY ACROSS TARGETS** 允许 (rank-1 偏好与 prev_target rank-1 同 deck 邻接)。

输出 rank-1 candidate, 含:
- `covered_aspects`: 本候选覆盖了 target 的哪些 aspect_id
- `residual_gap`: target 中未被本候选覆盖的 aspect_ids
- 其他: score / match_reason / parts_to_reuse / etc.

### Step 3: Pick rank-2/3 (per `slide_rank23_gap_based.md`)

若 `residual_gap == []` → 不出 rank-2/3。
否则:
- rank-2 选最能补 residual_gap 的 candidate
- **NO adjacency / NO cross-deck constraint** (与 rank-1 不同)
- 每个 rank-2/3 必填 `addresses_gap` (说明本候选补哪些 aspect)
- 递归: rank-3 补 rank-1+rank-2 仍未覆盖的 gap
- 若无候选能补 gap → 少出一个 rank, 不硬凑

### archetype 优先匹配 (Phase O 新增, 2026-06-27)
若 target slide 含 `archetype` 字段 (Phase O 后 OUTLINE 必填), 在 rank-1 / rank-2 候选筛选时
**优先** 匹配库中 `slide_role` 或 `适合复用场景` 标签与该 archetype 同义的 source slide。
例: target.archetype="single_paper_title_authors_only" → 优先选库中标 `paper_title_page` /
`work_intro` / `代表作扉页` 的 slide。
仅当显著更适合时才跨 archetype 匹配。

---

## Output Schema

```json
{
  "slide_matches": [
    {
      "target_slide_index": 12,
      "target_role": "method",
      "target_claim": "...",
      "aspects": [
        {"aspect_id": "a1", "aspect_text": "...", "aspect_type": "method"},
        ...
      ],
      "candidates": [
        {
          "rank": 1,
          "resource_id": "...",
          "deck_id": "...",
          "section_id": "...",
          "source_owner": "library | project",
          "score": 0.88,
          "confidence": 0.88,
          "match_reason": "...",
          "covered_aspects": ["a1: ...", "a2: ..."],
          "residual_gap": ["a3: ...", "a4: ...", "a5: ..."],
          "parts_to_reuse": "...",
          "parts_to_drop": "...",
          "relation_to_others": "...",
          "recommended_reuse_mode": "direct_slide_reuse | partial_slide_reuse | style_only",
          "must_rewrite": ["..."],
          "gap_explanation": ""
        },
        {
          "rank": 2,
          "resource_id": "...",
          ...
          "covered_aspects": ["a3: ..."],
          "addresses_gap": ["a3: 接受率公式与数学推导"],
          "relation_to_others": "rank-1 给框架; 本候选补公式 (gap a3)",
          ...
        },
        {
          "rank": 3,
          ...
          "addresses_gap": ["a4: ...", "a5: ..."],
          ...
        }
      ]
    }
  ]
}
```

---

## Global Hard Rules (适用于所有 ranks)

- Output ONE entry per `target_pages` element. Length must equal `len(target_pages)`.
- **SEMANTIC PRIORITY (HARDEST RULE)**: 所有 ranks 的选源必须由 topic/claim
  alignment 驱动。`salient_visuals / template_svg / slide_role` 等版式信号
  **不参与选源决策**, 仅作 tie-breaker。

- **ROLE ISOLATION** (避免目录式版式跑到内容页):
  - Structural source slides (`slide_role` IN {cover_candidate, toc_candidate,
    chapter_candidate, ending_candidate}) 只能被以下 target 选:
    - `target_role = cover` → cover_candidate
    - `target_role = agenda` → toc_candidate
    - `target_role = section_divider` → toc_candidate / chapter_candidate
    - `target_role = closing` → ending_candidate
    - `target_role = references` → ending_candidate
  - Content target pages (motivation/problem/method/comparison/result/...)
    **MUST** pick `content_candidate` (即 _pool_tier=strong / same_deck /
    default 中 slide_role=content_candidate 的)

- **STRUCTURAL PAGES** (cover/agenda/section_divider/closing/references):
  最多 1 个 candidate (不需要 rank-2/3)。

- **CONTENT PAGES**: 1-3 candidates per process logic above。

- **NO CROSS-TARGET DEDUP**: 同一 source slide 可作为多 target 的 candidate。

- **placeholder** (无合适候选): 输出 `candidates: []` + plan_note。
  允许情况:
  - 所有 candidates 的最高 score < 0.5
  - 真正的 user-supplied content page

- Output **strict JSON only**.

---

## Quick Reference

| 场景 | 行为 |
|---|---|
| rank-1 完全覆盖 target | 不出 rank-2/3 |
| rank-1 score < 0.5 | candidates=[] (placeholder) |
| 没候选能补 residual_gap | 只出 rank-1 (or rank-1+2 if rank-2 found) |
| 结构页 | 1 candidate, 取自对应 structural pool |
| 内容页有 3+ aspects | 通常出 rank-1 + rank-2 (+rank-3) 互补 |
| score 0.50-0.69 | `gap_explanation` 必填 (≤120 字) |
