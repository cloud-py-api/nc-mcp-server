#!/bin/bash
# Seed synthetic data for pagination integration tests.
# Creates 55 files and 55 link shares to test limit/offset behavior.
# Usage: seed_pagination_data.sh <NC_URL> <USER> <PASSWORD>
set -euo pipefail

NC_URL="${1:?Usage: $0 <NC_URL> <USER> <PASSWORD>}"
USER="${2:?}"
PASS="${3:?}"
AUTH="$USER:$PASS"
DAV_BASE="$NC_URL/remote.php/dav/files/$USER"
DIR="mcp-pagination-data"
COUNT=55

echo "=== Seeding pagination test data ($COUNT items) ==="

echo "Creating directory: $DIR"
curl -sf -u "$AUTH" -X MKCOL "$DAV_BASE/$DIR/" -o /dev/null 2>/dev/null || true

echo "Creating $COUNT files..."
for i in $(seq 1 $COUNT); do
  NUM=$(printf '%03d' "$i")
  curl -sf -u "$AUTH" -X PUT \
    -H "Content-Type: text/plain" \
    --data "Pagination test file $NUM" \
    "$DAV_BASE/$DIR/pagtest-$NUM.txt" -o /dev/null &
  if (( i % 10 == 0 )); then wait; fi
done
wait
echo "Created $COUNT files"

echo "=== Seed complete ==="
