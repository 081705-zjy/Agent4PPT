# Skill: Structural Review

## Role
Review generated artifacts for structural correctness.

## Inputs
- `deck.pptx`
- `run-manifest.json`
- `structural-validation.md`
- `render-log.md`

## Outputs
- `deck-review.md`

## Rules
- Prioritize defects that block use: missing deck, wrong page count, non-openable
  PPTX, missing assets, text overflow, low editability, broken notes/transitions.
- Do not judge style unless there is a concrete rendering issue.

## Quality Bar
- The review clearly states pass/fail, blocking issues, and next repair action.

