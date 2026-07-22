#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/test_ai_flow.py" "${1:-disk_full}" --base-url "${BASE_URL:-http://127.0.0.1:8000/api/v1}"
