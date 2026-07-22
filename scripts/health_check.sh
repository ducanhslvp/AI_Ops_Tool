#!/usr/bin/env sh
set -eu
: "${AIOPS_TOKEN:?Set AIOPS_TOKEN to an access token}"
BASE_URL=${AIOPS_API_URL:-http://localhost:8000/api/v1}
curl --fail --silent --show-error -H "Authorization: Bearer $AIOPS_TOKEN" \
  "$BASE_URL/ai/providers/health"
