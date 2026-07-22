#!/bin/sh
set -eu

mkdir -p /app/data
chown aiops:aiops /app/data

gosu aiops alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  gosu aiops python /app/scripts/seed_backend.py
fi

exec gosu aiops "$@"
