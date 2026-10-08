# Skill: Revision Router

## Role
Convert review findings or user feedback into a rollback decision.

## Inputs
- `review-report.json`
- User feedback
- `stage-state.json`
- `slide-state.json`

## Outputs
- `revision-plan.json`

## Output Contract

```json
{
  "revision_type": "P0|P1|P2|P3|P4",
  "problem": "short problem description",
  "rollback_stage": "BRIEF|RESOURCE_SCAN|TEMPLATE_LIBRARY_BUILD|TEMPLATE_LIBRARY_QUERY|TASK_UNDERSTANDING|REUSE_OUTLINE|DRAFT_ASSEMBLY|GAP_ANALYSIS|GAP_RESEARCH|SLIDE_REWRITE|STYLE_UNIFICATION|RENDER|REVIEW",
  "affected_slides": [1],
  "suggested_action": "specific action"
}
```

## Rules
- P0 input missing -> Intake.
- P1 material misunderstanding -> Resource Scan, Template Library Query, or Task Understanding.
- P2 overall planning error -> Reuse Outline.
- P3 page logic, shallow source use, or bad draft assembly -> Draft Assembly, Gap Analysis, or Slide Rewrite.
- P4 expression or visual/style detail -> Slide Rewrite, Style Unification, or Render.
