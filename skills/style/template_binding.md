# Skill: Template Style Binding

## Role
Bind slide plans and visual plans to available template layouts and style rules.

## Inputs
- `template-profile.json`
- `model-routed-plan.json`
- `visual-plan.json`
- `resource-index.json`
- `template-library-candidates.json`
- `style-unification-plan.json`

## Outputs
- `template-binding.json`
- `style-profile.json`

## Rules
- Use real template affordances from `template-profile.json`.
- Choose layouts based on slide role, density, visual type, and available slots.
- Preserve user-provided template identity.
- Do not override factual slide content.
- Enforce template priority: `templates/basic` is the locked shell; topic templates
  are reuse candidates only when approved by the V2 reuse decision.
- Never bind topic-template assets unless `SLIDE_REWRITE` already approved them in
  `visual-plan.json.assets`.
- Bind slides to semantic components such as `research_agenda.v1`,
  `background_trend.v1`, `challenge_quantification.v1`,
  `related_work_matrix.v1`, `key_insight_mechanism.v1`,
  `method_overview.v1`, `technique_detail.v1`, `experiment_result.v1`,
  `ablation_comparison.v1`, `risk_boundary.v1`, and `summary_takeaway.v1`.

## Quality Bar
- Every slide has a selected template layout or a clear fallback reason.
- Binding output makes clear which elements are locked by basic and which are
  approved source/template reuse decisions.
