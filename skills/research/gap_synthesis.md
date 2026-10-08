# Gap Synthesis Skill

Turn raw research results into per-slide evidence packs. SLIDE_REWRITE may only
consume `per-slide-evidence-pack.json` as evidence — so this stage must produce
high-fidelity, slide-targeted facts with verifiable citations.

## Inputs

- `raw-research-results.json` — output of GAP_RESEARCH tool calls
  (web_search/web_fetch/local_resource_search hits).
- `slide-gap-plan.json` — per-slide gap declarations and research_queries.
- `research-query-plan.json` — query intent, target evidence kind, preferred
  source types.

## Output

- `per-slide-evidence-pack.json` — what SLIDE_REWRITE may use, per page.
- `citations.json` — flat citation table referenced by ID.
- `research.md` — human-readable research summary.
- `research-audit.json` — counts of web_results, gap_query_count,
  unsupported_query_count.

### per-slide-evidence-pack.json schema

```json
{
  "packs": [
    {
      "slide_index": 8,
      "usable_facts": [
        {
          "fact": "KV cache memory grows with sequence length and number of layers.",
          "source_id": "citation_003",
          "supports": "claim_to_prove",
          "confidence": 0.85,
          "verbatim_quote": "...optional..."
        }
      ],
      "chartable_data": [
        {"label": "...", "values": [...], "source_id": "citation_004"}
      ],
      "source_refs": ["citation_003", "citation_004"],
      "unsupported_claims": [
        "原 slide-plan 中要求的某条 claim，研究没有找到支撑"
      ],
      "remaining_gaps": [
        "若 unsupported_claims 非空，下一步建议（缩小范围 / 改写 claim / 标记低置信）"
      ]
    }
  ]
}
```

## Hard rules

- Every `source_id` must correspond to an entry in `citations.json` with
  url/title/access_date.
- Do not paraphrase numbers — if a number wasn't in the source, do not invent
  it. If only a range is available, record it as a range.
- `unsupported_claims` is REQUIRED whenever the original slide-plan claim
  cannot be backed by retrieved evidence. SLIDE_REWRITE will use this to
  downgrade or rewrite the claim.
- `research.md` must list which queries returned zero useful evidence — this
  feeds the SYSTEM_REVIEW citation check.
- `research-audit.json` counts must accurately reflect raw-research-results.
- Output strict JSON for all `.json` files.
