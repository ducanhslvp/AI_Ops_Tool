#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKEND_ROOT="$PROJECT_ROOT/backend"
FRONTEND_ROOT="$PROJECT_ROOT/ShadcnTemplateFE"

for command in python3 node npm; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing required command: $command" >&2; exit 1; }
done

[ -x "$BACKEND_ROOT/.venv/bin/python" ] || python3 -m venv "$BACKEND_ROOT/.venv"
"$BACKEND_ROOT/.venv/bin/python" -m pip install --upgrade pip
(cd "$BACKEND_ROOT" && .venv/bin/python -m pip install -e '.[dev]')

if [ ! -f "$BACKEND_ROOT/.env" ]; then
  cp "$BACKEND_ROOT/.env.example" "$BACKEND_ROOT/.env"
  "$BACKEND_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/generate_local_env.py" "$BACKEND_ROOT/.env"
fi

(cd "$BACKEND_ROOT" && .venv/bin/python -m alembic upgrade head)
"$BACKEND_ROOT/.venv/bin/python" "$PROJECT_ROOT/scripts/seed_backend.py"
(cd "$FRONTEND_ROOT" && npm ci)

echo "Setup complete. API: http://127.0.0.1:8000  UI: http://127.0.0.1:5173"
"$PROJECT_ROOT/scripts/run_all.sh"
