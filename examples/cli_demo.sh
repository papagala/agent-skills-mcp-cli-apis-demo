#!/usr/bin/env sh
# Path 2 from the article: CLI integration.
#
# An "agent" shells out to existing tools. Cheap and fast for local
# environments, but no shared semantics and no cloud reach.

set -eu

API_BASE_URL="${API_BASE_URL:-http://localhost:30080}"

created_id=$(
  curl --silent --show-error --fail \
    -X POST "${API_BASE_URL}/tasks" \
    -H "Content-Type: application/json" \
    -d '{"title":"Roll out feature flag","assignee":"frank","priority":"medium"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])'
)

curl --silent --show-error --fail \
  -X PATCH "${API_BASE_URL}/tasks/${created_id}" \
  -H "Content-Type: application/json" \
  -d '{"status":"done","note":"flag enabled at 10%"}'

echo
echo "Completed task ${created_id} via CLI."
