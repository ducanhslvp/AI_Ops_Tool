#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKEND_ROOT="$PROJECT_ROOT/backend"
FRONTEND_ROOT="$PROJECT_ROOT/ShadcnTemplateFE"
PYTHON="$BACKEND_ROOT/.venv/bin/python"

(cd "$BACKEND_ROOT" && "$PYTHON" -m ruff check app tests alembic)
(cd "$BACKEND_ROOT" && "$PYTHON" -m pytest -q)
(cd "$FRONTEND_ROOT" && npm run lint)
(cd "$FRONTEND_ROOT" && npm run test)
(cd "$FRONTEND_ROOT" && npm run build)

echo "All backend and frontend checks passed."
