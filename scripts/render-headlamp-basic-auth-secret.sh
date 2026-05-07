#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <username> <password>" >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required" >&2
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi

username="$1"
password="$2"
tmpfile="$(mktemp)"
trap 'rm -f "$tmpfile"' EXIT

printf '%s:%s\n' "$username" "$(openssl passwd -apr1 "$password")" > "$tmpfile"

kubectl -n kube-system create secret generic headlamp-basic-auth \
  --from-file=users="$tmpfile" \
  --dry-run=client \
  -o yaml
