#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON="$ROOT/backend/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
cd "$ROOT/backend"
"$PYTHON" -m pytest -q -p no:cacheprovider tests/test_ai_adapter.py
