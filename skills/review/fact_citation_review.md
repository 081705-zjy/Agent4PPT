# Skill: Fact And Citation Review

## Role
Check whether factual claims are supported by real citations.

## Inputs
- `research.md`
- `citations.json`
- `model-routed-plan.json`
- `manuscript.md`

## Outputs
- Fact/citation section in `review-report.json`

## Rules
- Do not accept unsupported external facts.
- Flag fabricated, stale, vague, or mismatched citations.
- Map issues to source IDs and affected slides.

