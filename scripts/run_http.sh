#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source .venv/bin/activate

uvicorn server.http_app:app --host "${MCP_HTTP_HOST:-127.0.0.1}" --port "${MCP_HTTP_PORT:-8080}"

# ensure the script is executable with: chmod +x scripts/run_http.sh