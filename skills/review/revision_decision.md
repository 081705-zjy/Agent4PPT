# Revision Decision Skill

Decide where to roll back when SYSTEM_REVIEW reports issues. This is the
explicit decision stage that replaces the prior inline `_apply_revision_budget`
logic.

## Inputs

- `system-review-report.json` — verdict + per-dimension issues + suggested
  rollback stages.
- `review-report.json` — backward-compatible review summary.
- `render-audit.json` — render-time validation results.
- `revision-state.json` — cumulative rounds + last_rollback target + history.

## Output: `revision-plan.json`

```json
{
  "revision_type": "NONE|P1|P2|P3|P4|ESCALATE",
  "problem": "issues 简明合并描述",
  "rollback_stage": "RENDER|STYLE_UNIFICATION|SLIDE_REWRITE|GAP_SYNTHESIS|GAP_RESEARCH|GAP_ANALYSIS|DRAFT_REVIEW|DRAFT_ASSEMBLY_PLAN|REUSE_DECISION_AUDIT|SLIDE_PLAN|REUSE_OUTLINE|STORY_STRATEGY|SLIDE_MATCHING|SECTION_MATCHING|DECK_MATCHING|null",
  "route_candidates": ["..."],
  "issues": [...],
  "affected_slides": [...],
  "suggested_action": "Roll back to X, fix Y, regenerate, then rerun SYSTEM_REVIEW",
  "budget_state": {
    "round": 3,
    "max_rounds": 8,
    "stall_streak": 1,
    "circuit_breaker_threshold": 3,
    "escalate_now": false
  }
}
```

## Rollback routing table

| Failed dimension | Rollback target |
|---|---|
| structural / render_audit / svg_visual_scan | RENDER |
| fact_citation | GAP_SYNTHESIS (or GAP_RESEARCH if no candidates returned) |
| visual / visual_spec / citation_footer | STYLE_UNIFICATION |
| component_binding / content_depth / text_density / claim_quality | SLIDE_REWRITE |
| source_usage | DRAFT_ASSEMBLY_PLAN |
| plan_review | SLIDE_PLAN |
| logic / duration_density / audience_fit | STORY_STRATEGY |
| resource_match_misalignment | SLIDE_MATCHING |

## Hard rules

- Pick the EARLIEST upstream stage among all blocking issues — never roll back
  to a downstream stage of where the issue originates.
- If `budget_state.round >= max_rounds` OR
  `budget_state.stall_streak >= circuit_breaker_threshold`, set
  `revision_type=ESCALATE` and produce an escalation note in `suggested_action`.
- If review verdict is `pass`, set `revision_type=NONE` and
  `rollback_stage=null`. Pipeline advances to FINAL_ACCEPT.
- Output strict JSON only.
