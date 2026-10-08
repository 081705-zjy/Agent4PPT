# ppt-master Fusion Strategy

This project should not treat `ppt-master` as an external product to call at runtime.
The useful approach is to understand the reusable capabilities from ppt-master, vendor
or port the right modules into ppt-agent, and expose them through ppt-agent's own
contracts: artifacts, validators, render adapter, template profile, and review loop.

## Current State

`ppt-agent-v1` already includes a curated copy of ppt-master code under
`scripts/lib/ppt_master/`. Runtime generation does not depend on a sibling checkout.

The fused capabilities currently used are:

- PPTX template ingestion:
  `pptx_template_import.py`, `pptx_to_svg/`, and `template_import/manifest.py` parse a
  user `.pptx` template into `manifest.json`, extracted assets, layout SVGs, master SVGs,
  and flat slide SVGs.
- Template profile derivation:
  `scripts/lib/template_ingest.py` converts the imported manifest into
  `template-profile.json` and `spec_lock.md`, which are native ppt-agent contracts.
- Template-inheriting rendering:
  `scripts/lib/svg_skeleton_render.py` injects ppt-agent content into imported layout
  skeletons, then exports the result through the vendored SVG-to-DrawingML converter.
- Editable PPTX export:
  `scripts/lib/ppt_master/svg_to_pptx/` converts SVG text, shapes, paths, tables, and
  media into native PowerPoint XML so the final `deck.pptx` remains editable.

This is a partial fusion, not a full architectural merge.

## Capabilities Worth Fusing Next

### 1. Template Intelligence

Bring more of ppt-master's template understanding into ppt-agent planning.

Useful pieces:
- Master/layout/slide inheritance graph.
- Placeholder geometry and placeholder type inference.
- Theme color and font extraction.
- Common asset detection.
- Page type candidates: cover, content, chapter, ending.

Target ppt-agent contract:
- Strengthen `template-profile.json` with richer layout capabilities.
- Add layout slots such as title, subtitle, body, image, table, chart, footer, logo,
  page number, and section label.
- Make `visual-plan.json` choose layouts based on real template affordances instead of
  generic names like `title-and-body`.

Why this matters:
PPT quality improves when content planning knows the actual available regions and visual
grammar of the user's template before copy and layout decisions are made.

### 2. SVG Finalization Pipeline

ppt-master has useful SVG cleanup utilities in `svg_finalize/`.

Useful pieces:
- `flatten_tspan.py`
- `embed_images.py`
- `align_embed_images.py`
- `fix_image_aspect.py`
- `crop_images.py`
- `svg_rect_to_path.py`
- `embed_icons.py`

Target ppt-agent contract:
- Add a deterministic `SVG_FINALIZATION` sub-step inside render.
- Validate every generated SVG before conversion.
- Normalize text spans, image references, crop behavior, and icon embedding.

Why this matters:
This reduces conversion failures and visual drift between HTML/SVG preview and final PPTX.

### 3. Native DrawingML Renderer

The SVG-to-PPTX converter is the strongest reusable ppt-master capability.

Useful pieces:
- `drawingml_converter.py`
- `drawingml_elements.py`
- `drawingml_paths.py`
- `drawingml_styles.py`
- `pptx_builder.py`
- `pptx_media.py`
- `pptx_slide_xml.py`

Target ppt-agent contract:
- Treat this as ppt-agent's native editable renderer, not as a foreign backend.
- Keep `scripts/export-pptx.sh` as the adapter boundary.
- Use `native-svg` as the public renderer name, while keeping `ppt-master` as a
  compatibility alias.

Why this matters:
The product promise is editable PPT generation. DrawingML export is the core capability
that makes that promise real.

### 4. Animation, Transitions, Notes, and Narration

ppt-master includes animation, transition, notes, timing, and narration helpers.

Useful pieces:
- `pptx_animations.py`
- `svg_to_pptx/animation_config.py`
- `svg_to_pptx/pptx_notes.py`
- `svg_to_pptx/pptx_narration.py`

Target ppt-agent contract:
- Add optional artifacts such as `animation-plan.json`, `speaker-notes.md`, and
  `narration-plan.json`.
- Keep these off by default for business decks; enable them explicitly per use case.
- Validate that animations do not damage editability or create review ambiguity.

Why this matters:
It opens a path toward training decks, narrated decks, demos, and auto-presentable decks
without weakening the default editable static deck path.

### 5. Media and Asset Handling

ppt-master's media layer can improve asset robustness.

Useful pieces:
- Content type detection.
- Relationship insertion.
- Image conversion/caching.
- Support for common raster/vector formats.

Target ppt-agent contract:
- Make `asset-manifest.json` stricter: dimensions, content type, local path, usage,
  editability impact, and citation/evidence role.
- Reject unsupported media before render.
- Track whether an asset is decorative, evidentiary, template furniture, or generated.

Why this matters:
Decks fail in practice when media references are brittle. Asset handling should be a
first-class pipeline capability, not a renderer side effect.

## Capabilities To Avoid Fusing Blindly

- ppt-master CLI workflow as-is.
  ppt-agent already has its own state machine and artifact contracts.
- User/global config from ppt-master such as `~/.ppt-master`.
  ppt-agent runs should remain reproducible from the run directory and repo config.
- Unbounded visual freedom from arbitrary SVG.
  ppt-agent should generate within validated layout contracts to preserve readability.
- Animation-by-default.
  Most professional decks should stay clean and inspectable unless motion is requested.

## Recommended Roadmap

1. Stabilize naming:
   use `native-svg` as the default renderer name and keep `ppt-master` as an internal
   compatibility alias.

2. Upgrade template profile:
   extend `template-profile.json` from basic title/body regions to typed slots and
   layout affordances derived from the manifest.

3. Insert SVG finalization:
   run a controlled subset of `svg_finalize/` before DrawingML conversion and validate
   the generated SVGs. Initial fused subset: `flatten_tspan` plus XML well-formedness
   validation.

4. Add layout selection intelligence:
   make `visual-plan.json` choose from real imported layouts based on slide role,
   content density, asset needs, chart/table needs, and placeholder availability.

5. Add optional presentation features:
   notes first, then transitions, then animations/narration, each behind explicit config
   and validation.

6. Refactor module boundaries:
   gradually wrap `scripts/lib/ppt_master/*` behind ppt-agent modules such as
   `template_importer`, `editable_renderer`, `media_registry`, and `animation_exporter`.
   Do not expose raw ppt-master internals to generation stages.

## Architectural Principle

The direction is:

`ppt-master capability -> ppt-agent contract -> ppt-agent validation -> final deck`

not:

`ppt-agent -> call ppt-master project -> accept output`

This keeps ppt-agent responsible for planning, evidence, quality gates, and user-facing
workflow, while reusing the parts of ppt-master that are genuinely hard and valuable:
OOXML parsing, template reconstruction, and editable DrawingML generation.
