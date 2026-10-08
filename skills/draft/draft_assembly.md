# Draft Assembly Skill

Create a draft deck plan from the reuse-first outline.

The draft may mix styles and contain placeholders. Its job is to preserve and
test reuse decisions before final rewriting.

This stage is tool-only: it may read `outline.json`, `gap-cards.json`,
`slide-plan.json`, `reuse-first-outline.json`, and `draft-assembly-plan.json`,
but it must not invent new narrative or re-run semantic selection.

Each slide must include:

- draft_action
- source_lineage
- copied_slide_refs
- copied_asset_refs
- placeholder_slots
- rewrite_instructions
- gap_notes
- speaker_note_feedback

Do not hide gaps. Put page-specific revision notes into speaker notes or the
draft assembly plan.
