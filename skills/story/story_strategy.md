# Story Strategy Skill

Design the deck's narrative arc — what audience cognition path leads to the
core message. This is the only stage that decides "整体怎么讲". Downstream
REUSE_OUTLINE and SLIDE_PLAN must follow this arc.

## Inputs

- `idea-analysis.json` — deck_type, audience_level, core_message,
  reuse_strategy, must_have_pages, expected_sections.
- `data/source-understanding.json` — what the user's materials cover.
- `matched-resource-pack.json` — which library resources are available at
  what reuse level.
- `question-state.json` — original intake answers; read `answers.user_outline`
  for the user-supplied free-form outline (highest priority).

## Output: `story-strategy.json` + `story-strategy.md` (mirror)

```json
{
  "main_thesis": "一句话讲清楚演示完成时听众应该相信的核心论断",
  "audience_journey": [
    {"stage": "认知起点", "what_audience_knows": "..."},
    {"stage": "中段转折", "what_should_change": "..."},
    {"stage": "认知终点", "what_audience_takes_home": "..."}
  ],
  "narrative_arc": [
    {
      "section": "背景与动机",
      "purpose": "解释为什么这个问题值得讲",
      "depth": "shallow|balanced|deep",
      "preferred_evidence_kind": "data|case|diagram|narrative",
      "reuse_sources": ["matched_resource_id1", "..."],
      "must_research": false
    }
  ],
  "decision_log": {
    "why_this_arc": "...",
    "rejected_arcs": [{"arc": "...", "reason": "..."}],
    "user_outline_alignment": "fully_followed|partially_followed|reinterpreted",
    "user_outline_alignment_reason": "..."
  }
}
```

## Hard rules

- If `question-state.answers.user_outline` is non-empty, the
  `narrative_arc` must align with it. `user_outline_alignment` must reflect this
  honestly.
- `reuse_sources` may only reference `resource_id`s that appear in
  `matched-resource-pack.json`. Empty list = this section must be newly
  created.
- `main_thesis` must be a single judgment sentence and must align with the
  `core_message` from brief-analysis.
- Total `narrative_arc` length is tuned to slide_count: roughly 1 section per
  3-5 slides, but cover + closing always count as separate sections.
- Output strict JSON only — and a parallel `story-strategy.md` that is the
  human-readable version of the same arc.
