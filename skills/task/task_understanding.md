# Skill: Task Understanding

## Role
Classify the presentation task and decide which materials should influence the deck.

## Inputs
- `project-brief.json` or `question-state.json`
- `resource-index.json`
- `research-audit.json`

## Outputs
- `task-analysis.json`
- `material-selection.json`

## Rules
- Identify deck type: group meeting, proposal, technical report, product pitch,
  course presentation, literature review, or executive briefing.
- Mark which local materials are useful, irrelevant, stale, or style-only.
- Decide whether additional web research is required.
- Do not write final slide copy.

## Quality Bar
- Later agents can tell what task they are solving, what materials to trust, and
  what gaps remain.

