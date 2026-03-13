#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${GEEK_ENV_TEST_IMAGE:-geek-env-toolkit-test}"

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

main() {
  log "Building Docker test image"
  docker build -t "$IMAGE_NAME" -f "$REPO_ROOT/tests/toolkit.Dockerfile" "$REPO_ROOT"

  log "Running toolkit integration test in Docker"
  docker run --rm \
    -e DEBIAN_FRONTEND=noninteractive \
    -e HOME=/home/geek \
    -e GEEK_ENV_TEST_MODE=1 \
    -e GEEK_ENV_SYSTEM_ROOT=/tmp/geek-env-system \
    -v "$REPO_ROOT":/workspace \
    -w /workspace \
    "$IMAGE_NAME" \
    bash /workspace/tests/test-toolkit-in-container.sh
}

main "$@"
