# Mark executable with: chmod +x scripts/setup.sh

#!/usr/bin/env bash
set -euo pipefail

# Create and populate virtualenv
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip wheel setuptools

# Install runtime deps (for deterministic CI you can switch to a pinned requirements lock)
pip install -r requirements.txt

# Install dev extras defined in pyproject (pytest, ruff, black, mypy, etc.)
pip install -e ".[dev]"

echo "✅ Environment ready. Use '. .venv/bin/activate' to activate."
