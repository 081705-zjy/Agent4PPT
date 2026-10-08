#!/usr/bin/env bash
# claude-fetch.sh — web-fetch adapter for ppt_agent_app/research.py.
# Contract: receives a URL as argv and prints concise factual notes.
set -euo pipefail

URL="$*"
if [[ ! "$URL" =~ ^https?:// ]]; then
    echo "ERROR: URL must start with http:// or https://" >&2
    exit 2
fi

TIMEOUT_SECONDS="${PPT_CLAUDE_TIMEOUT_SECONDS:-20}"

if [[ "${PPT_AGENT_HEALTHCHECK:-}" == "1" ]]; then
    echo "claude-fetch adapter is configured"
    exit 0
fi

PROMPT=$(cat <<EOF
Fetch this source and extract citation-worthy factual notes for a technical PPT:

$URL

Return concise plain text only, under 800 words. Include publication/source identity when visible.
If web fetch is unavailable, return no content and briefly write the reason to stderr.
EOF
)

timeout "$TIMEOUT_SECONDS" claude \
    -p \
    --output-format text \
    --no-session-persistence \
    --allowedTools "WebFetch" \
    -- \
    "$PROMPT"
