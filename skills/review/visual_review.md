# Skill: Visual Review

## Role
Check visual clarity and consistency.

## Inputs
- `visual-plan.json`
- `slides-html/`
- `screenshots/`
- `template-profile.json`

## Outputs
- Visual section in `review-report.json`

## Rules
- Check hierarchy, density, alignment, color consistency, and diagram readability.
- Distinguish style preference from blocking visual defects.
- Flag any content slide whose title is only a topic label rather than a claim.
- Flag a visual as blocking if it does not support the assertion title, if the
  same component dominates the deck, or if large blank areas make the page look
  unfinished.
- Flag two-box/table overuse when a flow, architecture, chart, roadmap, or risk
  matrix would better prove the slide claim.
