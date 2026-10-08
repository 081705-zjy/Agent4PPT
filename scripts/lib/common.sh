#!/usr/bin/env bash
# common.sh — shared shell helpers for V2 support scripts.
set -euo pipefail

[[ -n "${_COMMON_SH_LOADED:-}" ]] && return 0
_COMMON_SH_LOADED=1

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$_COMMON_DIR/../.." && pwd)"

log_info()  { echo "[ppt-agent] INFO: $*"  >&2; }
log_warn()  { echo "[ppt-agent] WARN: $*"  >&2; }
log_error() { echo "[ppt-agent] ERROR: $*" >&2; }

load_config() {
    local config_file="${PROJECT_ROOT}/config/default_config.json"
    if [[ ! -f "$config_file" ]]; then
        log_error "Config file not found: $config_file"
        return 1
    fi
    if ! jq empty "$config_file" 2>/dev/null; then
        log_error "Malformed config: $config_file"
        return 1
    fi
    cat "$config_file"
}

get_config_value() {
    local config_json="$1"
    local key="$2"
    local default="${3:-}"
    local val
    val=$(printf '%s' "$config_json" | jq -r ".${key} // empty")
    if [[ -z "$val" ]]; then
        echo "$default"
    else
        echo "$val"
    fi
}
