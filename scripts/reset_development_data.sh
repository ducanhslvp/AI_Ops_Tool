#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export APP_ENV=development TEST_MODE=true SSH_TRANSPORT=local_simulation
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/reset_development_data.py"
