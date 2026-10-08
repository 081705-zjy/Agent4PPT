# Draft Review Skill

Inspect the draft deck against the plan. This catches plan-execution drift
before GAP_ANALYSIS, so that GAP_ANALYSIS is reasoning about real gaps rather
than execution mistakes.

## Inputs

- `draft-assembly-plan.json` — what was supposed to happen.
- `draft-manuscript.md` — what actually got written.
- `draft-visual-plan.json` — what visuals/assets actually got bound.
- `slide-plan.json` — the page-level contract.
- `reuse-decision-audit.json` — what reuse was authorized.

## Output: `draft-review.json`

```json
{
  "slides": [
    {
      "slide_index": 8,
      "covered_slide_plan": true,
      "reuse_within_audit": true,
      "direct_copy_risk": false,
      "remaining_placeholders": ["chart_data", "citation"],
      "missing_evidence": ["KV cache 显存复杂度"],
      "broken_visual_logic": false,
      "issues": [
        {
          "kind": "missing_placeholder_resolution|copied_without_rewrite|visual_inconsistent|claim_drift",
          "detail": "..."
        }
      ]
    }
  ],
  "overall_pass": false,
  "blocking_issues": ["..."]
}
```

## Hard rules

- `covered_slide_plan=false` means the draft did not address one of
  `claim_to_prove / proof_structure / visual_intent` from slide-plan.
- `reuse_within_audit=false` means the draft used a resource action that was
  NOT approved by reuse-decision-audit. This is a high-severity issue.
- `direct_copy_risk=true` means original text from the source slide was carried
  over verbatim where rewrite was required.
- `overall_pass` is false if any `blocking_issues` exists; otherwise true.
  Blocking issues include any `reuse_within_audit=false` or any
  `direct_copy_risk=true`.
- Output strict JSON only.
