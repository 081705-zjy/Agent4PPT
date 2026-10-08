# Render Backend Conformance Spec

A single contract every render backend must satisfy so the orchestrator can treat them
interchangeably and gate deck quality uniformly. Driven through `scripts/export-pptx.sh`
(subcommands `render` / `validate`).

## Inputs (read from the run dir)
- `manuscript.md` — slide-separated source of truth (titles + on-slide copy).
- `visual-plan.json` — per-slide `layout_type` + `editable_elements` + local `assets`.
- `style-guide.md` — palette / typography / layout / chart / image / icon / accessibility.
- `chart-spec.json` + rendered `charts/` — data-derived factual charts (AC-13).
- localized assets under `assets/`; run `config/default_config.json` (backend, ratios).

## Outputs (written to the run dir)
- `deck.pptx` — editable PPTX (native text boxes / shapes / charts / tables).
- `slides-html/` — per-slide HTML preview; `screenshots/` — standard-size PNGs.
- `render-log.md` — frontmatter: `render_mode` (`stub`|`real`), `backend`, `slide_count`,
  `page_count`, `page_count_ok`, `openable`, `assets_ok`, `aggregate_editable_ratio`,
  `min_editable_ratio`; body: per-slide `editable_ratio`.
- `structural-validation.md` (via `validate`) — page-count/openability/assets/overflow,
  `measured_aggregate_editable_ratio` vs `render_log_aggregate_editable_ratio`,
  `editability_gate_pass`, `deck_quality_pass`.

## Capability matrix
| Backend | render_mode | editable objects | charts | screenshots/HTML | creds |
|---------|-------------|------------------|--------|------------------|-------|
| `stub` | `stub` | native text boxes | data-derived SVG (via gen-charts) | HTML + placeholder PNG | none |
| `native-svg` | `real` | Fused SVG/DrawingML renderer | data-derived | HTML + real PNG | none/local |
| `ppt-master` compatibility alias | `real` | Same as `native-svg` | data-derived | HTML + real PNG | none/local |
| `gpt-image2` | `real` (assets) | + concept pictures | never factual charts | — | image API |

## Validation hooks / gate
- `STRUCTURAL_VALIDATION` recomputes editability from the reopened `deck.pptx`; the gate
  uses the **measured** ratio, never a render-log claim.
- Deck-quality acceptance = `render_mode == real` AND aggregate `editable_ratio >= 0.8`.
  The `stub` backend therefore never passes the deck-quality gate (orchestration only).
- Every backend MUST emit screenshots/HTML preview so review can inspect visual output.

## Error codes (export-pptx.sh / adapters)
- `0` success; `1` usage / unopenable deck / chart-spec rejected; `2` real backend not wired.

## Adapter command paths
```
bash scripts/export-pptx.sh render   <run-dir> [--smoke] [--backend <name>]
bash scripts/export-pptx.sh validate <run-dir>
```
`--backend` overrides `config.render_backend` for that invocation. `stub` → `render_mode=stub`
(orchestration only); `native-svg` and legacy aliases such as `ppt-master` →
`render_mode=real`. The real path is ppt-agent's fused editable SVG/DrawingML renderer:
it uses vendored ppt-master conversion modules, but runtime generation does not call a
separate ppt-master checkout or delegate the workflow to another project.

When `enable_svg_finalization` is true, the template-skeleton render path runs a controlled
SVG finalization step before DrawingML conversion. The current fused subset flattens
`tspan` structures and validates every generated SVG as well-formed XML; failures block
rendering instead of falling back silently.

## Certification (through the adapter, not hand-built)
The V2 smoke suite checks syntax and render-contract compatibility through
`export-pptx.sh`; render logs are never hand-authored. Real project verification should
also inspect `render-audit.json` for source-asset binding and repeated-layout issues.
