#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT/ShadcnTemplateFE"
[ -d node_modules ] || { echo 'Run scripts/setup_linux.sh first.' >&2; exit 1; }
exec npm run dev -- --host 127.0.0.1 --port 5173
