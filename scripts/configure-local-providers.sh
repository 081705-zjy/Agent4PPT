#!/usr/bin/env bash
# Configure local provider secrets without committing them to the repo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

read_secret() {
    local label="$1"
    local value=""
    read -rsp "$label: " value
    printf '\n' >&2
    printf '%s' "$value"
}

read_default() {
    local label="$1"
    local default="$2"
    local value=""
    read -rp "$label [$default]: " value
    printf '%s' "${value:-$default}"
}

echo "This script writes local secrets to ~/.claude, ~/.codex, and .env.local."
echo "Leave a prompt empty to skip that credential."

ANTHROPIC_AUTH_TOKEN="$(read_secret "ANTHROPIC_AUTH_TOKEN")"
ANTHROPIC_BASE_URL="$(read_default "ANTHROPIC_BASE_URL" "https://center.soruxgpt.com/api/cc")"
OPENAI_API_KEY="$(read_secret "OPENAI_API_KEY for Codex mirror")"
CODEX_BASE_URL="$(read_default "Codex mirror base_url" "https://chat.soruxgpt.com/codex")"
CODEX_MODEL="$(read_default "Codex model" "gpt-5.5")"
INFINI_API_KEY="$(read_secret "INFINI_API_KEY")"

umask 077
mkdir -p "$HOME/.claude" "$HOME/.codex"

if [[ -n "$ANTHROPIC_AUTH_TOKEN" ]]; then
    ANTHROPIC_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN" \
    ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path.home() / ".claude" / "settings.json"
data = {}
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
env = dict(data.get("env") or {})
env["ANTHROPIC_AUTH_TOKEN"] = os.environ["ANTHROPIC_AUTH_TOKEN"]
env["ANTHROPIC_BASE_URL"] = os.environ["ANTHROPIC_BASE_URL"]
data["env"] = env
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
fi

CODEX_MODEL="$CODEX_MODEL" CODEX_BASE_URL="$CODEX_BASE_URL" python3 - <<'PY'
import os
from pathlib import Path

path = Path.home() / ".codex" / "config.toml"
text = f'''model = "{os.environ["CODEX_MODEL"]}"
model_provider = "mirror"

[model_providers.mirror]
name = "mirror"
base_url = "{os.environ["CODEX_BASE_URL"]}"
wire_api = "responses"
requires_openai_auth = true
'''
path.write_text(text, encoding="utf-8")
path.chmod(0o600)
PY

if [[ -n "$OPENAI_API_KEY" ]]; then
    OPENAI_API_KEY="$OPENAI_API_KEY" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path.home() / ".codex" / "auth.json"
path.write_text(json.dumps({"OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]}, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
fi

ANTHROPIC_AUTH_TOKEN="$ANTHROPIC_AUTH_TOKEN" \
ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
INFINI_API_KEY="$INFINI_API_KEY" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
python3 - "$ROOT/.env.local" <<'PY'
import os
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
values = {
    "ANTHROPIC_AUTH_TOKEN": os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
    "ANTHROPIC_BASE_URL": os.environ.get("ANTHROPIC_BASE_URL", ""),
    "INFINI_API_KEY": os.environ.get("INFINI_API_KEY", ""),
    "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
    "PPT_CLAUDE_TIMEOUT_SECONDS": "60",
    "PPT_AGENT_RESEARCH_TIMEOUT_SECONDS": "90",
    "PPT_AGENT_FETCH_TIMEOUT_SECONDS": "35",
    "PPT_AGENT_MODEL_TIMEOUT_SECONDS": "90",
    "PPT_AGENT_HOST": "127.0.0.1",
    "PPT_AGENT_PORT": "8765",
}
lines = ["# Local secrets for ppt-agent. Do not commit this file."]
for key, value in values.items():
    if value:
        lines.append(f"{key}={shlex.quote(value)}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
path.chmod(0o600)
PY

echo "Configured local provider files."
echo "Next: bash scripts/start-app.sh"
