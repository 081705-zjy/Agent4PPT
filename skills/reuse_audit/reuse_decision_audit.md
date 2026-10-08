# Reuse Decision Audit Skill

Audit every page's reuse decision before it reaches DRAFT_ASSEMBLY. This is a
HARD GATE: a slide with an unapproved or unsafe reuse must not be assembled.

## Inputs

- `slide-plan.json` — per-page claim, proof_structure, reuse_binding.
- `matched-resource-pack.json` — original match metadata with confidence and
  risks.
- `data/resources_library/template/semantic-profiles.json` — the resource's semantic
  reusability rating and do_not_reuse_when conditions.

## Output: `reuse-decision-audit.json`

```json
{
  "audits": [
    {
      "slide_index": 8,
      "resource_id": "slide.<id>",
      "decision": "approved|approved_with_rewrite|rejected",
      "allowed_use": "layout_and_chart_structure|caption_pattern|full|none",
      "not_allowed": ["original_claim", "original_numeric_values"],
      "required_actions": [
        "rewrite title",
        "replace data",
        "regenerate caption",
        "cite updated source"
      ],
      "risk_level": "low|medium|high",
      "audit_basis": [
        "claim_match",
        "object_or_metric_match",
        "caption_match",
        "context_match",
        "low_misleading_risk"
      ]
    }
  ],
  "approved_resource_ids": ["..."],
  "rejected_resource_ids": ["..."]
}
```

## Hard rules

- The 5 audit_basis dimensions (claim/object/caption/context/misleading) must
  all be satisfied for `decision = approved`. Missing any → `approved_with_rewrite`
  with the unmet dimensions listed in `required_actions`.
- If `data/resources_library/template/semantic-profiles.json` says the source slide is
  `reusability=hard_topic` and the target page is NOT same-topic, decision must
  be `rejected` or `approved_with_rewrite` with `allowed_use=layout_only`.
- `risk_level=high` requires either `decision=rejected` or human override
  documented in `required_actions`.
- `approved_resource_ids` is the FINAL list of resources downstream may use.
  Anything not in this list must not appear in DRAFT_ASSEMBLY_PLAN.
- Output strict JSON only.
