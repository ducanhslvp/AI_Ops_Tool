#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LOG_DIR="$PROJECT_ROOT/.run"
mkdir -p "$LOG_DIR"
nohup "$PROJECT_ROOT/scripts/run_backend.sh" >"$LOG_DIR/backend.log" 2>&1 &
echo $! >"$LOG_DIR/backend.pid"
nohup "$PROJECT_ROOT/scripts/run_frontend.sh" >"$LOG_DIR/frontend.log" 2>&1 &
echo $! >"$LOG_DIR/frontend.pid"
sleep 3
case "$(uname -s)" in
  Darwin) open http://127.0.0.1:5173 ;;
  Linux) command -v xdg-open >/dev/null 2>&1 && xdg-open http://127.0.0.1:5173 >/dev/null 2>&1 || true ;;
esac
echo "AIOps Platform started. API: http://127.0.0.1:8000  UI: http://127.0.0.1:5173"
