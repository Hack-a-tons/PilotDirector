#!/usr/bin/env bash
#
# Usage:
#   cat domains.txt | ./checkdomains.sh
#
#   Options:
#     -h, --help   Show this help message
#

show_help() {
  grep '^#' "$0" | cut -c 3-
}

# Parse options
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  show_help
  exit 0
elif [[ "$1" != "" ]]; then
  echo "Unknown option: $1" >&2
  echo "Use -h for help." >&2
  exit 1
fi

# Check dependencies
if ! command -v whois >/dev/null 2>&1; then
  echo "Error: whois command not found. Install with 'brew install whois'." >&2
  exit 2
fi

check_domain() {
  local domain="$1"
  local output
  output=$(whois "$domain" 2>/dev/null)

  # Normalize to lowercase
  local lower
  lower=$(echo "$output" | tr '[:upper:]' '[:lower:]')

  if echo "$lower" | grep -qE "no match|not found|available"; then
    echo "$domain"
  else
    # uncertain → print debug info to stderr
    echo "?? Cannot determine availability for $domain" >&2
    echo "$output" >&2
  fi
}

# Read domains from stdin
while IFS= read -r domain; do
  [[ -z "$domain" ]] && continue
  check_domain "$domain"
done
