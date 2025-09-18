# Mark executable with: chmod +x scripts/run_server.sh

#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source .venv/Scripts/activate

# Optional: export a few envs used by app.config (if present)
# export SANDBOX_ROOT="./.sandbox"
# export REDIS_URL="redis://127.0.0.1:6379/0"
# export HTTP_ALLOWLIST="example.com,api.github.com"

# Run FastMCP stdio server
python -m server.main
