# Research Deck Optimization

Research decks use the V2 evidence chain:

```text
reuse outline -> draft assembly -> gap analysis -> gap research
-> slide rewrite -> style unification -> render audit
```

Each technical slide should preserve:

- claim or assertion title
- evidence need
- source lineage
- primary visual role
- citations or explicit gap
- approved source asset bindings when images/tables/PPT pages are reused

Missing proof is handled by `GAP_ANALYSIS` and `GAP_RESEARCH`; the renderer must not
invent data or citations.
