#!/usr/bin/env bash
# gen-charts.sh — DATA_CHART_SPEC sub-pipeline runner (AC-13).
#
# Renders every factual chart in <run-dir>/chart-spec.json into <run-dir>/charts/ as a
# data-derived SVG and writes <run-dir>/chart-validation.md tracing each value to a source.
# Factual charts must be data-derived (never image-generated) and every value must carry a
# source; otherwise this exits non-zero and chart-validation.md records the rejection.
# An empty `charts: []` spec is valid and renders nothing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Usage: gen-charts.sh <run-dir>" >&2
    exit 1
fi

RUN_DIR="$1"
if [[ ! -f "$RUN_DIR/chart-spec.json" ]]; then
    log_error "no chart-spec.json in $RUN_DIR"
    exit 1
fi

PPT_RUN_DIR="$RUN_DIR" python3 "$SCRIPT_DIR/lib/chart_render.py"
