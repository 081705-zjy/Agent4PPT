# Skill: Render Contract

## Role
Define the rendering constraints for editable PPTX output.

## Inputs
- `manuscript.md`
- `visual-plan.json`
- `template-profile.json`
- `asset-catalog.json`
- `template-binding.json`

## Outputs
- `deck.pptx`
- `render-log.md`
- `structural-validation.md`

## Rules
- Use template skeleton rendering when `template_import_dir` exists.
- Preserve editable text and native shapes.
- Validate page count, openability, assets, notes, transitions, overflow, and editability.

## Quality Bar
- `deck_quality_pass=true` and aggregate editable ratio is at least the configured threshold.
