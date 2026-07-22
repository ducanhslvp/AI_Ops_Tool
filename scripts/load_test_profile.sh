#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/local_test_client.py" "${1:?profile required}" --hostname "${2:-erp-linux-01}" --base-url "${BASE_URL:-http://127.0.0.1:8000/api/v1}"
