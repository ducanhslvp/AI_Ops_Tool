#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for name in backend frontend; do
  file="$ROOT/.run/$name.pid"
  if [[ -f "$file" ]]; then kill "$(cat "$file")" 2>/dev/null || true; rm -f "$file"; fi
done
