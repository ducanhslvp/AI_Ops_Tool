#!/usr/bin/env sh
set -eu
: "${AIOPS_TOKEN:?Set AIOPS_TOKEN to an access token}"
BASE_URL=${AIOPS_API_URL:-http://localhost:8000/api/v1}
MESSAGE=${1:-Check disk health and explain the evidence}
SERVER=${AIOPS_SERVER_ID:-}
BODY=$(printf '{"message":"%s","server_id":%s}' "$MESSAGE" "$(if [ -n "$SERVER" ]; then printf '"%s"' "$SERVER"; else printf null; fi)")
curl --no-buffer --fail --silent --show-error -X POST \
  -H "Authorization: Bearer $AIOPS_TOKEN" -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" -d "$BODY" "$BASE_URL/ai/chat/stream"
