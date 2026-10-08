#!/usr/bin/env bash
# validate-artifact.sh — V2 artifact checks for the reuse-first app runtime.
set -euo pipefail

usage() {
    cat <<EOF
Usage: validate-artifact.sh <type> <file>

V2 JSON types:
  reuse-first-outline, draft-assembly-plan, slide-gap-plan, slide-composition,
  visual-plan, template-binding, style-unification-plan

V2 Markdown types:
  manuscript, style-guide, render-log, structural-validation, review-report
EOF
}

if [[ $# -lt 2 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 1
fi

TYPE="$1"
FILE="$2"
ERRORS=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

fail() {
    echo "[ppt-agent] ERROR: $*" >&2
    ERRORS=$((ERRORS + 1))
}

if [[ ! -f "$FILE" ]]; then
    fail "artifact file not found: $FILE"
    exit 2
fi
if [[ ! -s "$FILE" ]]; then
    fail "artifact file is empty: $FILE"
    exit 2
fi

json_req() {
    local filter="$1"
    local desc="$2"
    if ! jq -e "$filter" "$FILE" >/dev/null 2>&1; then
        fail "JSON requirement not met: $desc"
    fi
}

frontmatter() {
    sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$FILE"
}

fm_req() {
    local field="$1"
    if ! frontmatter | grep -q "^${field}:"; then
        fail "missing frontmatter field: $field"
    fi
}

validate_json_common() {
    if ! jq empty "$FILE" >/dev/null 2>&1; then
        fail "invalid JSON: $FILE"
        return
    fi
    json_req 'has("schema_version") and (.schema_version | type == "string")' "schema_version string"
    json_req 'has("generated_at") and (.generated_at | type == "string")' "generated_at string"
}

case "$TYPE" in
    reuse-first-outline)
        validate_json_common
        json_req '.slides | type == "array" and length > 0' "slides non-empty array"
        json_req '.slides | all(has("slide_index") and has("target_title") and has("target_role") and has("selected_reuse"))' \
            "each slide has slide_index/target_title/target_role/selected_reuse"
        json_req '(.slide_count // (.slides | length)) == (.slides | length)' "slide_count matches slides"
        ;;
    draft-assembly-plan)
        validate_json_common
        json_req '.slides | type == "array" and length > 0' "slides non-empty array"
        json_req '.slides | all(has("slide_index") and has("draft_action") and has("selected_reuse") and has("source_lineage") and has("rewrite_instructions"))' \
            "each draft slide has slide_index/draft_action/selected_reuse/source_lineage/rewrite_instructions"
        ;;
    slide-gap-plan)
        validate_json_common
        json_req '.slides | type == "array"' "slides array"
        json_req '.slides | all(has("slide_index") and has("current_state") and has("narrative_gaps") and has("evidence_gaps") and has("visual_gaps") and has("citation_gaps") and has("research_queries") and has("rewrite_plan"))' \
            "each gap slide has V2 gap fields"
        ;;
    slide-composition)
        validate_json_common
        json_req '.slides | type == "array" and length > 0' "slides non-empty array"
        json_req '.slides | all(has("slide_index") and has("claim_to_prove") and has("evidence_need") and has("primary_visual_role"))' \
            "each composition has claim/evidence/visual role"
        ;;
    visual-plan)
        validate_json_common
        json_req '.slides | type == "array" and length > 0' "slides non-empty array"
        json_req '(.slide_count | type == "number") and (.slide_count == (.slides | length))' \
            "slide_count equals slides length"
        json_req '.slides | all(has("slide_index") and has("layout_type") and has("assets") and has("slide_composition") and has("content_blocks") and has("visual_spec"))' \
            "each visual slide has slide_index/layout_type/assets/slide_composition/content_blocks/visual_spec"
        json_req '.slides | all((.assets | type == "array") and (.content_blocks | type == "array") and (.slide_composition | type == "object") and (.visual_spec | type == "object"))' \
            "V2 visual arrays/objects are well typed"
        while IFS= read -r rel; do
            [[ -z "$rel" ]] && continue
            if [[ "$rel" = /* ]]; then
                candidate="$rel"
            elif [[ -e "$(dirname "$FILE")/$rel" ]]; then
                candidate="$(dirname "$FILE")/$rel"
            else
                candidate="$ROOT/$rel"
            fi
            if [[ ! -e "$candidate" ]]; then
                fail "visual-plan references missing local asset: $rel"
            fi
        done < <(jq -r '.slides[].assets[]? | if type == "string" then . else (.local_path // .path // .asset_path // .source_path // empty) end' "$FILE" 2>/dev/null)
        if [[ -f "$(dirname "$FILE")/template-profile.json" ]]; then
            python3 "$(dirname "$0")/lib/template_contract.py" visual-plan "$FILE" || fail "visual-plan violates template-profile contract"
        fi
        ;;
    template-binding)
        validate_json_common
        json_req 'has("base_template") or has("template_id") or has("slides")' \
            "binding has base/template/slides information"
        ;;
    style-unification-plan)
        validate_json_common
        json_req 'has("policy") or has("slides") or has("style_profile")' \
            "style unification plan has policy/slides/style profile"
        ;;
    manuscript)
        fm_req schema_version
        fm_req generated_at
        fm_req slide_count
        if ! grep -q '^##[[:space:]]Slide[[:space:]][0-9]\+:' "$FILE"; then
            fail "manuscript must contain slide sections"
        fi
        for label in "On-slide copy:" "Visual instruction:" "Speaker notes:" "Source references:"; do
            if ! grep -q "$label" "$FILE"; then
                fail "manuscript missing label: $label"
            fi
        done
        ;;
    style-guide)
        fm_req schema_version
        fm_req generated_at
        for section in "Palette" "Typography" "Layout Rhythm" "Chart Style" "Image Treatment" "Accessibility"; do
            if ! grep -qi "^##[[:space:]].*${section}" "$FILE"; then
                fail "style-guide missing section: $section"
            fi
        done
        if [[ -f "$(dirname "$FILE")/template-profile.json" ]]; then
            python3 "$(dirname "$0")/lib/template_contract.py" style-guide "$FILE" || fail "style-guide violates template-profile contract"
        fi
        ;;
    render-log|structural-validation|review-report)
        fm_req schema_version
        fm_req generated_at
        ;;
    *)
        fail "unknown V2 artifact type: $TYPE"
        ;;
esac

[[ "$ERRORS" -eq 0 ]]
