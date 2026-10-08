#!/usr/bin/env bash
# start-app.sh — run the local ppt-agent software UI/API.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$ROOT/.env.local" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ROOT/.env.local"
    set +a
fi

HOST="${PPT_AGENT_HOST:-127.0.0.1}"
PORT="${PPT_AGENT_PORT:-8765}"
PORT_RANGE="${PPT_AGENT_PORT_RANGE:-20}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            HOST="${2:?missing value for --host}"
            shift 2
            ;;
        --port)
            PORT="${2:?missing value for --port}"
            shift 2
            ;;
        --port-range)
            PORT_RANGE="${2:?missing value for --port-range}"
            shift 2
            ;;
        -h|--help)
            cat <<'EOF'
Usage: bash scripts/start-app.sh [--host 127.0.0.1] [--port 8768] [--port-range 20]

Environment defaults:
  PPT_AGENT_HOST
  PPT_AGENT_PORT
  PPT_AGENT_PORT_RANGE

The script starts at --port/PPT_AGENT_PORT and picks the first free port within
the range.
EOF
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

START_PORT="$PORT"
PORT="$(python3 - "$HOST" "$START_PORT" "$PORT_RANGE" <<'PY'
import socket
import sys

host = sys.argv[1]
start = int(sys.argv[2])
count = int(sys.argv[3])
for port in range(start, start + count + 1):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        continue
    finally:
        sock.close()
    print(port)
    raise SystemExit(0)
print("")
raise SystemExit(1)
PY
)"

if [[ -z "$PORT" ]]; then
    echo "ERROR: no free port found for $HOST starting at $START_PORT" >&2
    exit 1
fi

cd "$ROOT"
echo "ppt-agent app will use http://$HOST:$PORT"
python3 -m ppt_agent_app.server --host "$HOST" --port "$PORT"
