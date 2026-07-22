#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"; FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export APP_ENV=development TEST_MODE=true SSH_TRANSPORT=local_simulation
mkdir -p "$ROOT/.run"
(cd "$ROOT/backend" && .venv/bin/alembic upgrade head)
"$ROOT/backend/.venv/bin/python" "$ROOT/scripts/seed_backend.py"
(cd "$ROOT/backend" && nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" >api-dev.log 2>&1 & echo $! >"$ROOT/.run/backend.pid")
(cd "$ROOT/ShadcnTemplateFE" && VITE_API_BASE_URL="http://127.0.0.1:$BACKEND_PORT/api/v1" nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" >vite-dev.log 2>&1 & echo $! >"$ROOT/.run/frontend.pid")
echo "Development environment started: http://127.0.0.1:$FRONTEND_PORT"
