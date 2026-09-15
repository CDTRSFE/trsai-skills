#!/bin/bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/state"
STATE_FILE="$STATE_DIR/notified-issues.json"
QUERY_SCRIPT="$SCRIPT_DIR/jira_query.sh"

mkdir -p "$STATE_DIR"

if [[ ! -f "$STATE_FILE" ]]; then
  echo '{"seen":[]}' > "$STATE_FILE"
fi

RESULT="$(bash "$QUERY_SCRIPT" list)"

if ! jq -e '.ok == true' >/dev/null 2>&1 <<< "$RESULT"; then
  jq -cn --argjson result "$RESULT" '{ok:false,error:($result.error // "Jira query failed"),raw:$result}'
  exit 0
fi

TMP_NEW="$(mktemp)"
TMP_STATE="$(mktemp)"

jq -c --slurpfile state "$STATE_FILE" '
  .issues
  | map(select(.key as $key | ($state[0].seen // []) | index($key) | not))
' <<< "$RESULT" > "$TMP_NEW"

jq -n --slurpfile state "$STATE_FILE" --slurpfile result <(printf '%s' "$RESULT") '
  {
    seen: ((($state[0].seen // []) + (($result[0].issues // []) | map(.key))) | unique)
  }
' > "$TMP_STATE"

mv "$TMP_STATE" "$STATE_FILE"

jq -cn --argjson result "$RESULT" --slurpfile new "$TMP_NEW" '
  {
    ok:true,
    action:"notify_check",
    total_count:($result.count // 0),
    new_count:($new[0] | length),
    new_issues:$new[0]
  }
'

rm -f "$TMP_NEW"
