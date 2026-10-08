# Skill: Research Query Generation

## Role
Turn the project topic and brief into high-signal search queries.

## Inputs
- `question-state.json`
- `resource-index.json`

## Outputs
- `search-queries.json` or an equivalent query list in `research-results.json`

## Rules
- Prefer authoritative sources: papers, surveys, technical reports, standards,
  official documentation, and major conference material.
- Generate both broad survey queries and specific mechanism queries.
- Do not fabricate URLs or citations.

## Quality Bar
- Queries cover background, architecture, mechanisms, benchmarks, challenges,
  and recent work.

