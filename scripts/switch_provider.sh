#!/usr/bin/env sh
set -eu
: "${1:?Usage: switch_provider.sh PROVIDER}"
: "${AIOPS_TOKEN:?Set AIOPS_TOKEN to an administrator access token}"
BASE_URL=${AIOPS_API_URL:-http://localhost:8000/api/v1}
curl --fail --silent --show-error -X POST -H "Authorization: Bearer $AIOPS_TOKEN" \
  -H "Content-Type: application/json" -d "{\"provider\":\"$1\"}" \
  "$BASE_URL/ai/providers/switch"
