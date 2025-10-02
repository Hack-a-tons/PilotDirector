#!/usr/bin/env bash
#
# checkdomains.sh — check domain availability using Domainr API
#
# Usage:
#   cat domains.txt | ./checkdomains.sh
#
# Options:
#   -h, --help   Show this help message
#
# Requirements:
#   - curl
#   - jq
#   - .env file in same directory with either:
#       API_KEY="your_rapidapi_key"
#     or
#       CLIENT_ID="your_client_id"
#

show_help() {
  grep '^#' "$0" | cut -c 4-
}

# --- Load .env ---
if [[ -f ".env" ]]; then
  # shellcheck source=/dev/null
  source .env
fi

# --- Option parsing ---
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  show_help
  exit 0
elif [[ -n "$1" ]]; then
  echo "Unknown option: $1" >&2
  echo "Use -h for help." >&2
  exit 1
fi

# --- Dependency check ---
for cmd in curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: $cmd not found. Install with 'brew install $cmd'." >&2
    exit 2
  fi
done

check_domain() {
  local domain="$1"
  local url response summary

  if [[ -n "$API_KEY" ]]; then
    # RapidAPI endpoint
    url="https://domainr.p.rapidapi.com/v2/status?domain=$domain"
    response=$(curl -s \
      -H "x-rapidapi-host: domainr.p.rapidapi.com" \
      -H "x-rapidapi-key: $API_KEY" \
      "$url")
  elif [[ -n "$CLIENT_ID" ]]; then
    # Direct Domainr endpoint
    url="https://api.domainr.com/v2/status?domain=$domain&client_id=$CLIENT_ID"
    response=$(curl -s "$url")
  else
    echo "Error: API_KEY or CLIENT_ID must be set in .env" >&2
    exit 3
  fi

  if [[ -z "$response" ]]; then
    echo "Error: empty response for $domain" >&2
    return
  fi

  summary=$(echo "$response" | jq -r '.status[0].summary // empty')

  if [[ "$summary" == "inactive" || "$summary" == "undelegated" || "$summary" == "available" ]]; then
    echo "$domain"
  else
    echo "Taken: $domain ($summary)" >&2
  fi
}

# --- Main loop ---
while IFS= read -r domain; do
  [[ -z "$domain" ]] && continue
  check_domain "$domain"
done
