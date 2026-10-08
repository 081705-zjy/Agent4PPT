#!/usr/bin/env bash
# gen-image.sh — cover/concept image adapter (AC-4).
#
# Interface for generating ONLY decorative cover / section-divider / concept pictures
# (placed as native picture objects). It MUST NOT be used for factual charts — those are
# data-derived via gen-charts.sh (AC-13).
#
# Real backend: `gpt-image2` (needs credentials). Credential-free (default / dry-run), it
# does not fabricate an image; it records an explicit asset gap and exits 0, so downstream
# stages proceed without a non-existent local asset (visual-plan must not reference one).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

if [[ $# -lt 2 || "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Usage: gen-image.sh <run-dir> <concept-prompt> [out-name]" >&2
    exit 1
fi

RUN_DIR="$1"
PROMPT="$2"
OUT_NAME="${3:-concept}"
GAPS_FILE="$RUN_DIR/asset-gaps.md"

CFG="$(load_config)"
ENABLED="$(get_config_value "$CFG" enable_generated_images "true")"

# Without credentials we never fabricate a factual-looking asset; record the gap instead.
PPT_IMAGE_API_KEY="${PPT_IMAGE_API_KEY:-${OPENAI_API_KEY:-}}"
if [[ -z "${PPT_IMAGE_API_KEY:-}" ]]; then
    {
        echo "- gap: concept image not generated (no PPT_IMAGE_API_KEY); enabled=$ENABLED"
        echo "  intended: assets/${OUT_NAME}.png  prompt: ${PROMPT}"
    } >> "$GAPS_FILE"
    log_info "gen-image: no credentials — recorded asset gap for '${OUT_NAME}' in $GAPS_FILE"
    echo "GAP:${OUT_NAME}"
    exit 0
fi

mkdir -p "$RUN_DIR/assets"
OUT_PATH="$RUN_DIR/assets/${OUT_NAME}.png"
BASE_URL="${PPT_IMAGE_BASE_URL:-${OPENAI_BASE_URL:-https://api.openai.com/v1}}"
MODEL="${PPT_IMAGE_MODEL:-image2}"

TMP_JSON="$(mktemp)"
TMP_BODY="$(mktemp)"
python3 - "$PROMPT" "$MODEL" > "$TMP_BODY" <<'PY'
import json, sys
prompt = sys.argv[1]
model = sys.argv[2]
print(json.dumps({
    "model": model,
    "prompt": prompt,
    "size": "1536x864",
    "n": 1,
    "response_format": "b64_json",
}, ensure_ascii=False))
PY

code="$(curl -sS -w '%{http_code}' -o "$TMP_JSON" \
    -H "Authorization: Bearer ${PPT_IMAGE_API_KEY}" \
    -H "Content-Type: application/json" \
    -X POST "${BASE_URL%/}/images/generations" \
    --data-binary "@$TMP_BODY" || true)"
if [[ "$code" != "200" ]]; then
    {
        echo "- gap: image2 generation failed; http_status=$code model=$MODEL"
        echo "  intended: assets/${OUT_NAME}.png  prompt: ${PROMPT}"
        echo "  response: $(head -c 300 "$TMP_JSON" 2>/dev/null || true)"
    } >> "$GAPS_FILE"
    log_error "gen-image: image2 request failed with HTTP $code"
    echo "GAP:${OUT_NAME}"
    exit 0
fi

python3 - "$TMP_JSON" "$OUT_PATH" <<'PY'
import base64, json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
items = data.get("data") or []
if not items or not items[0].get("b64_json"):
    raise SystemExit("missing b64_json")
raw = base64.b64decode(items[0]["b64_json"])
open(sys.argv[2], "wb").write(raw)
PY
echo "assets/${OUT_NAME}.png"
