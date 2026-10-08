#!/usr/bin/env bash
# claude-search.sh — web-search adapter for ppt_agent_app/research.py.
# Contract: receives a search query as argv and prints lines:
#   url | title | snippet
set -euo pipefail

QUERY="$*"
if [[ -z "${QUERY//[[:space:]]/}" ]]; then
    echo "ERROR: empty query" >&2
    exit 2
fi

TIMEOUT_SECONDS="${PPT_CLAUDE_TIMEOUT_SECONDS:-20}"
MAX_RESULTS="${WEBSEARCH_MAX_RESULTS:-5}"

if [[ "${PPT_AGENT_HEALTHCHECK:-}" == "1" ]]; then
    echo "https://example.com | healthcheck | claude-search adapter is configured"
    exit 0
fi

PROMPT=$(cat <<EOF
Use available web search/fetch tools to find citation-worthy sources for this PPT research query:

$QUERY

Return at most $MAX_RESULTS results. Output only plain text lines in this exact format:
url | title | snippet

Rules:
- Prefer papers, official docs, standards, reputable technical reports, or primary sources.
- Prefer English sources for technical PPT evidence; include Chinese sources only when they
  are primary, highly relevant, or cover China-specific systems.
- Snippet must be one concise factual sentence useful for a slide citation.
- Do not include markdown bullets, numbering, explanation, or code fences.
- If web search/fetch is unavailable, return no results and briefly write the reason to stderr.
EOF
)

RAW="$(
    timeout "$TIMEOUT_SECONDS" claude \
        -p \
        --output-format text \
        --no-session-persistence \
        --allowedTools "WebSearch WebFetch" \
        -- \
        "$PROMPT"
)"

if grep -qi 'WEB_SEARCH_UNAVAILABLE\|permission.denied\|permission-denied\|permission denied' <<<"$RAW"; then
    printf '%s\n' "$RAW" >&2
    exit 3
fi

PARSED="$(
    awk -F'|' '
    function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
    NF >= 4 && tolower(trim($1)) == "url" {
        url=trim($2); title=trim($3); snippet=trim($4);
        if (url ~ /^https?:\/\//) print url " | " title " | " snippet;
        next
    }
    NF >= 3 {
        url=trim($1); title=trim($2); snippet=trim($3);
        if (url ~ /^https?:\/\//) print url " | " title " | " snippet;
    }' <<<"$RAW"
)"

if [[ -z "${PARSED//[[:space:]]/}" ]]; then
    printf 'ERROR: Claude search returned no parseable web sources. Raw output:\n%s\n' "$RAW" >&2
    exit 4
fi

printf '%s\n' "$PARSED"
