#!/usr/bin/env bash
# Run an all-users job in batches until every user is done.
#
#   run-batched-job.sh <api base url> <job path>
#   CRON_SECRET must be set.
#
# Each request starts no new user after BUDGET seconds and returns the uid it
# stopped after as next_cursor. Every request therefore ends well inside a
# host's time limit (Vercel Hobby stops a request after 300 s), and the next
# request picks up where the last one left off.
set -euo pipefail

API="$1"
JOB_PATH="$2"
BUDGET="${BUDGET:-200}"      # seconds of new work per request
MAX_TIME="${MAX_TIME:-330}"  # curl gives up a little after the host would
MAX_BATCHES="${MAX_BATCHES:-200}"
MAX_ATTEMPTS=3               # per batch, for timeouts and 5xx

: "${CRON_SECRET:?CRON_SECRET must be set}"

cursor=""
for batch in $(seq 1 "$MAX_BATCHES"); do
  body=$(jq -nc --arg c "$cursor" --argjson b "$BUDGET" \
    '{dry_run: false, time_budget_seconds: $b} + (if $c == "" then {} else {cursor: $c} end)')

  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    # A timed out curl prints "000"; "|| true" keeps it a retry under -e.
    response=$(curl -s -S -w "\n%{http_code}" --max-time "$MAX_TIME" -X POST \
      -H "Content-Type: application/json" \
      -H "X-Cron-Secret: $CRON_SECRET" \
      -d "$body" "$API$JOB_PATH") || response=$'\n000'
    code=$(echo "$response" | tail -n1)
    reply=$(echo "$response" | sed '$d')
    echo "Batch $batch attempt $attempt (after ${cursor:-start}): HTTP $code"
    echo "  $reply"
    [ "$code" = "200" ] && break
    # 4xx (bad secret, overlapping run) will not get better by retrying.
    case "$code" in 4*) echo "ERROR: $JOB_PATH refused the request"; exit 1 ;; esac
    if [ "$attempt" = "$MAX_ATTEMPTS" ]; then
      echo "ERROR: $JOB_PATH failed $MAX_ATTEMPTS times after cursor '${cursor:-start}'"
      exit 1
    fi
    sleep 10
  done

  cursor=$(echo "$reply" | jq -r '.next_cursor // empty')
  if [ -z "$cursor" ]; then
    echo "$JOB_PATH finished in $batch batch(es)."
    exit 0
  fi
done

echo "ERROR: $JOB_PATH still had users left after $MAX_BATCHES batches."
exit 1
