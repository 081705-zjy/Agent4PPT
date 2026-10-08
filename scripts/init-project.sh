#!/usr/bin/env bash
# init-project.sh — create a stable PPT project folder before generation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
    cat <<EOF
Usage: scripts/init-project.sh "presentation topic" [--project-dir DIR]

Create a project folder with templates/, sources/, assets/, and reviews/.
Use the browser UI or /api/projects/<id>/run-stage to run the reuse-first V2 flow.
EOF
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 1
fi

TOPIC="$1"
shift
PROJECT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir) PROJECT_DIR="${2:-}"; shift 2 ;;
        --*) echo "[init-project] unknown option: $1" >&2; usage; exit 1 ;;
        *) echo "[init-project] unexpected argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$PROJECT_DIR" ]]; then
    SLUG="$(python3 -c 'import re,sys; s=re.sub(r"[^A-Za-z0-9]+","-",sys.argv[1].strip()).strip("-").lower(); print((s[:48] or "deck"))' "$TOPIC")"
    PROJECT_DIR="$ROOT/projects/$SLUG"
fi

mkdir -p "$PROJECT_DIR/templates" "$PROJECT_DIR/sources" "$PROJECT_DIR/assets" \
    "$PROJECT_DIR/reviews/outline" "$PROJECT_DIR/reviews/style-sample" \
    "$PROJECT_DIR/reviews/screenshot" "$PROJECT_DIR/reviews/deck"

cat > "$PROJECT_DIR/PROJECT.md" <<EOF
# PPT Project

Topic: $TOPIC

Put a user template here before generation:

\`\`\`
$PROJECT_DIR/templates/
\`\`\`

Supported now:
- JSON profile compatible with ppt-templates/*.json
- .pptx reference file; it is recorded as the source template and Claude is instructed
  to inspect it during visual planning
EOF

echo "$PROJECT_DIR"
