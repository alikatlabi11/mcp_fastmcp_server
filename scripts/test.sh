# Mark executable with: chmod +x scripts/test.sh

#!/usr/bin/env bash
set -euo pipefail

# shellcheck disable=SC1091
source .venv/bin/activate

# Lint (optional; comment out if not needed)
ruff check .
black --check .

# Run tests
pytest
# pytest -v --cov=server --cov=cli --cov-report=term-missing tests/