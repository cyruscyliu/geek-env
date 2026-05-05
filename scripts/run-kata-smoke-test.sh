#!/usr/bin/env bash
# run-kata-smoke-test.sh
# Validate that the kata-qemu RuntimeClass can start and complete a simple pod

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
POD_NAME="${KATA_SMOKE_POD_NAME:-kata-smoke-test}"
RUNTIME_CLASS="${KATA_SMOKE_RUNTIME_CLASS:-kata-qemu}"
IMAGE="${KATA_SMOKE_IMAGE:-busybox}"
EXPECTED_OUTPUT="${KATA_SMOKE_EXPECTED_OUTPUT:-kata works}"

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

main() {
  [[ $EUID -eq 0 ]] || fail "Run this script with sudo or as root"

  log "Running smoke test with RuntimeClass ${RUNTIME_CLASS}..."
  k3s kubectl delete pod "$POD_NAME" --ignore-not-found=true

  k3s kubectl run "$POD_NAME" \
    --image="$IMAGE" \
    --restart=Never \
    --overrides="{\"spec\":{\"runtimeClassName\":\"${RUNTIME_CLASS}\"}}" \
    -- echo "$EXPECTED_OUTPUT"

  log "Waiting for smoke test pod..."
  k3s kubectl wait --for=condition=Ready "pod/${POD_NAME}" --timeout=60s 2>/dev/null || true
  k3s kubectl wait --for=jsonpath='{.status.phase}'=Succeeded "pod/${POD_NAME}" --timeout=60s

  local result
  result="$(k3s kubectl logs "$POD_NAME")"
  k3s kubectl delete pod "$POD_NAME" --ignore-not-found=true

  [[ "$result" == "$EXPECTED_OUTPUT" ]] \
    || fail "Smoke test failed. Got: \"$result\""
  log "Smoke test passed: \"$result\""
}

main "$@"
