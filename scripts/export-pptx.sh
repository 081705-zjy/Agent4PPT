#!/usr/bin/env bash
# export-pptx.sh — render adapter + structural validator for the PPT pipeline.
#
# Subcommands:
#   render   <run-dir> [--smoke]   Build deck.pptx (+ slides-html/, screenshots/, render-log.md)
#                                   from manuscript.md + visual-plan.json + style-guide.md.
#                                   --smoke renders only the cover + one representative content
#                                   slide into smoke/ for FIRST_SLIDE_SMOKE_TEST.
#   validate <run-dir>             Re-open the rendered deck.pptx, recompute structural checks
#                                   and editability, apply the deck-quality gate, and write
#                                   structural-validation.md.
#
# Backends (config render_backend, or --backend override): `stub` (minimal valid,
# orchestration-only; render_mode=stub) and the real editable SVG/DrawingML renderer
# (`ppt-master` is a compatibility alias because selected ppt-master modules are vendored
# under scripts/lib/ppt_master). Runtime generation does not call a sibling ppt-master
# checkout. Only render_mode=real may pass the deck-quality editability gate.
#
# Editability formula (plan §Render Adapter Contract):
#   editable_ratio = (native text boxes + shapes + charts + tables) / (significant objects),
# where significant objects = that numerator set + placed pictures (background fills and purely
# decorative full-bleed rasters excluded). Deck-quality acceptance requires render_mode=real AND
# aggregate editable_ratio >= min_editable_ratio (0.8); the stub therefore never passes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

usage() { echo "Usage: export-pptx.sh {render|validate} <run-dir> [--smoke]" >&2; }

if [[ $# -lt 2 || "$1" == "-h" || "$1" == "--help" ]]; then
    usage
    exit 1
fi

SUBCMD="$1"
RUN_DIR="$2"
shift 2 || true
SMOKE="0"
BACKEND_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --smoke)   SMOKE="1" ;;
        --backend)
            if [[ -z "${2:-}" ]]; then log_error "export-pptx: --backend requires a value (e.g. stub|native-svg|ppt-master)"; exit 1; fi
            BACKEND_OVERRIDE="$2"; shift ;;
        *)         log_error "export-pptx: unknown arg: $1"; exit 1 ;;
    esac
    shift
done

if [[ ! -d "$RUN_DIR" ]]; then
    log_error "run dir not found: $RUN_DIR"
    exit 1
fi

CFG="$(load_config)"
BACKEND="$(get_config_value "$CFG" render_backend "stub")"
# An explicit --backend overrides config (used to certify a real adapter through this path).
if [[ -n "$BACKEND_OVERRIDE" ]]; then BACKEND="$BACKEND_OVERRIDE"; fi
MIN_RATIO="$(get_config_value "$CFG" min_editable_ratio "0.8")"
SVG_FINALIZATION="$(get_config_value "$CFG" enable_svg_finalization "true")"

export PPT_RUN_DIR="$RUN_DIR" PPT_BACKEND="$BACKEND" PPT_SMOKE="$SMOKE" PPT_MIN_RATIO="$MIN_RATIO" \
    PPT_SVG_FINALIZATION="$SVG_FINALIZATION"

case "$SUBCMD" in
    render)   python3 "$SCRIPT_DIR/lib/pptx_backend.py" render ;;
    validate) python3 "$SCRIPT_DIR/lib/pptx_backend.py" validate ;;
    *) usage; exit 1 ;;
esac
