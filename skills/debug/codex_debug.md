# Skill: Codex Debug

## Role
Diagnose and repair pipeline/code failures.

## Inputs
- `app-state.json`
- `route-log.jsonl`
- `run-manifest.json`
- `structural-validation.md`
- recent job JSON files

## Outputs
- `devops/codex-debug-report.md`
- Optional code patch when explicitly allowed

## Rules
- Treat Codex as an engineering repair agent, not as slide copy writer.
- Collect failure context before proposing changes.
- Prefer small, testable patches.

## Quality Bar
- The report identifies the failing component, evidence, patch summary, and verification.

