#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_CONFIG="$SKILL_DIR/jira_config.json"

print_error() {
  local message="$1"
  jq -cn --arg error "$message" '{ok:false,error:$error}'
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    print_error "Missing required command: $cmd"
    exit 1
  fi
}

CONFIG_PATH="$DEFAULT_CONFIG"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      if [[ $# -lt 2 ]]; then
        print_error "Missing value for --config"
        exit 1
      fi
      CONFIG_PATH="$2"
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

ACTION="${1:-}"
ARGUMENT="${2:-}"

require_cmd jq
require_cmd curl

if [[ -z "$ACTION" ]]; then
  print_error "Usage: jira_query.sh [--config path] <list|detail> [ISSUE-KEY]"
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  print_error "Config file not found: $CONFIG_PATH"
  exit 1
fi

if ! jq empty "$CONFIG_PATH" >/dev/null 2>&1; then
  print_error "Invalid JSON config: $CONFIG_PATH"
  exit 1
fi

SOURCE_COUNT="$(jq '.sources | length // 0' "$CONFIG_PATH")"
if [[ "$SOURCE_COUNT" -eq 0 ]]; then
  print_error "No Jira sources configured in $CONFIG_PATH"
  exit 1
fi

if [[ "$ACTION" == "detail" && -z "$ARGUMENT" ]]; then
  print_error "detail action requires an issue key"
  exit 1
fi

build_url() {
  local template="$1"
  local issue_key="$2"
  jq -rn --arg tmpl "$template" --arg key "$issue_key" '$tmpl | gsub("\\{issue_key\\}"; $key)'
}

fetch_json() {
  local url="$1"
  local username="$2"
  local password="$3"
  local insecure="$4"

  local curl_args=(
    -sS
    --connect-timeout 10
    --max-time 30
    -u "$username:$password"
    -H "Accept: application/json"
  )

  if [[ "$insecure" == "true" ]]; then
    curl_args+=(-k)
  fi

  curl "${curl_args[@]}" "$url"
}

append_source_error() {
  local errors_file="$1"
  local source_name="$2"
  local message="$3"

  jq \
    --arg source "$source_name" \
    --arg message "$message" \
    '. + [{source: $source, message: $message}]' \
    "$errors_file" > "${errors_file}.next"
  mv "${errors_file}.next" "$errors_file"
}

list_issues() {
  local issues_file errors_file
  issues_file="$(mktemp)"
  errors_file="$(mktemp)"
  echo '[]' > "$issues_file"
  echo '[]' > "$errors_file"

  local sources_json
  sources_json="$(jq -c '.sources[]' "$CONFIG_PATH")"

  while IFS= read -r source; do
    [[ -z "$source" ]] && continue

    local name base_url username password list_url insecure browse_tmpl response source_label
    name="$(jq -r '.name // empty' <<< "$source")"
    base_url="$(jq -r '.base_url // empty' <<< "$source")"
    username="$(jq -r '.username // empty' <<< "$source")"
    password="$(jq -r '.password // empty' <<< "$source")"
    list_url="$(jq -r '.list_url // empty' <<< "$source")"
    insecure="$(jq -r '.insecure // false' <<< "$source")"
    browse_tmpl="$(jq -r '.browse_url_template // "\(.base_url)/browse/{issue_key}"' <<< "$source")"
    source_label="$(jq -r '.name // .base_url // "unknown"' <<< "$source")"

    if [[ -z "$name" || -z "$base_url" || -z "$username" || -z "$password" || -z "$list_url" ]]; then
      append_source_error "$errors_file" "$source_label" "Source config is incomplete"
      continue
    fi

    if ! response="$(fetch_json "$list_url" "$username" "$password" "$insecure" 2>/dev/null)"; then
      append_source_error "$errors_file" "$name" "Request failed or timed out"
      continue
    fi

    if ! jq empty >/dev/null 2>&1 <<< "$response"; then
      append_source_error "$errors_file" "$name" "Response was not valid JSON"
      continue
    fi

    if ! jq -e '(.issues | type) == "array"' >/dev/null 2>&1 <<< "$response"; then
      local jira_errors
      jira_errors="$(jq -r '(.errorMessages // []) | join("; ")' <<< "$response")"
      if [[ -z "$jira_errors" ]]; then
        jira_errors="Response did not include issues"
      fi
      append_source_error "$errors_file" "$name" "$jira_errors"
      continue
    fi

    jq \
      --arg source_name "$name" \
      --arg browse_tmpl "$browse_tmpl" \
      '
      [.issues[]? | (.key // "") as $issue_key | {
        source: $source_name,
        key: $issue_key,
        summary: (.fields.summary // ""),
        status: (.fields.status.name // ""),
        due_date: (.fields.duedate // ""),
        fix_versions: [(.fields.fixVersions // [])[]?.name],
        url: ($browse_tmpl | gsub("\\{issue_key\\}"; $issue_key))
      }]
      ' <<< "$response" > "${issues_file}.next"

    jq -s '.[0] + .[1]' "$issues_file" "${issues_file}.next" > "${issues_file}.merged"
    mv "${issues_file}.merged" "$issues_file"
    rm -f "${issues_file}.next"
  done <<< "$sources_json"

  jq -cn --slurpfile issues "$issues_file" --slurpfile errors "$errors_file" '
    ($errors[0] | length) as $error_count |
    ({
      ok: ($error_count == 0),
      action: "list",
      count: ($issues[0] | length),
      issues: $issues[0]
    } + if $error_count > 0 then {
      partial: (($issues[0] | length) > 0),
      error: "Some Jira sources failed",
      errors: $errors[0]
    } else {} end)
  '
  rm -f "$issues_file" "$errors_file" "${issues_file}.next" "${errors_file}.next"
}

detail_issue() {
  local issue_key="$1"
  local sources_json
  sources_json="$(jq -c '.sources[]' "$CONFIG_PATH")"

  while IFS= read -r source; do
    [[ -z "$source" ]] && continue

    local name base_url username password detail_tmpl browse_tmpl insecure detail_url response
    name="$(jq -r '.name // empty' <<< "$source")"
    base_url="$(jq -r '.base_url // empty' <<< "$source")"
    username="$(jq -r '.username // empty' <<< "$source")"
    password="$(jq -r '.password // empty' <<< "$source")"
    detail_tmpl="$(jq -r '.detail_url_template // "\(.base_url)/rest/api/2/issue/{issue_key}"' <<< "$source")"
    browse_tmpl="$(jq -r '.browse_url_template // "\(.base_url)/browse/{issue_key}"' <<< "$source")"
    insecure="$(jq -r '.insecure // false' <<< "$source")"

    if [[ -z "$name" || -z "$base_url" || -z "$username" || -z "$password" || -z "$detail_tmpl" ]]; then
      continue
    fi

    detail_url="$(build_url "$detail_tmpl" "$issue_key")"
    response="$(fetch_json "$detail_url" "$username" "$password" "$insecure" 2>/dev/null)" || continue

    if ! jq -e '.key' >/dev/null 2>&1 <<< "$response"; then
      continue
    fi

    if [[ "$(jq -r '.key // empty' <<< "$response")" != "$issue_key" ]]; then
      continue
    fi

    jq -cn \
      --arg source_name "$name" \
      --arg browse_tmpl "$browse_tmpl" \
      --arg issue_key "$issue_key" \
      --argjson raw "$response" '
      {
        ok: true,
        action: "detail",
        issue: {
          source: $source_name,
          key: ($raw.key // $issue_key),
          summary: ($raw.fields.summary // ""),
          status: ($raw.fields.status.name // ""),
          due_date: ($raw.fields.duedate // ""),
          fix_versions: [($raw.fields.fixVersions // [])[]?.name],
          reporter: ($raw.fields.reporter.displayName // "未知"),
          created: ($raw.fields.created // ""),
          updated: ($raw.fields.updated // ""),
          description: (
            if ($raw.fields.description | type) == "string" then
              $raw.fields.description
            elif ($raw.fields.description | type) == "object" then
              ($raw.fields.description | tostring)
            else
              ""
            end
          ),
          url: ($browse_tmpl | gsub("\\{issue_key\\}"; $issue_key))
        }
      }
    '
    return 0
  done <<< "$sources_json"

  print_error "Issue not found: $issue_key"
  return 1
}

case "$ACTION" in
  list)
    list_issues
    ;;
  detail)
    detail_issue "$ARGUMENT"
    ;;
  *)
    print_error "Unknown action: $ACTION"
    exit 1
    ;;
esac
