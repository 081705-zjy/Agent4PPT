# Skill: Research Synthesis

## Role
Convert web search/fetch results and local materials into usable deck evidence.

## Inputs
- `research-results.json`
- `citations.json`
- `resource-index.json`

## Outputs
- `research.md`
- Updated `citations.json` if citation normalization is required

## Rules
- Separate external sources from local resources.
- Keep source IDs stable as `S1`, `S2`, ...
- Every factual claim intended for slides should point to a source ID.
- Surface warnings when web search failed or local fallback was used.

## Quality Bar
- `research.md` contains search queries, source list, warnings, and extracted facts.

