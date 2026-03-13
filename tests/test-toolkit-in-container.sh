#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_HOME="${HOME:-/home/geek}"
FIRST_LOG="/tmp/geek-env-install-first.log"
SECOND_LOG="/tmp/geek-env-install-second.log"
SMOKE_LOG="/tmp/geek-env-smoke.log"

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

assert_file() {
  local path
  path="$1"
  [[ -f "$path" ]] || fail "Expected file: $path"
}

assert_dir() {
  local path
  path="$1"
  [[ -d "$path" ]] || fail "Expected directory: $path"
}

assert_log_contains() {
  local path pattern
  path="$1"
  pattern="$2"
  grep -Fq "$pattern" "$path" || fail "Expected log line '$pattern' in $path"
}

main() {
  mkdir -p "$TEST_HOME"
  rm -f "$FIRST_LOG" "$SECOND_LOG" "$SMOKE_LOG"

  export HOME="$TEST_HOME"
  export XDG_CONFIG_HOME="$HOME/.config"
  export XDG_DATA_HOME="$HOME/.local/share"
  export GEEK_ENV_TEST_MODE="${GEEK_ENV_TEST_MODE:-1}"
  export GEEK_ENV_SYSTEM_ROOT="${GEEK_ENV_SYSTEM_ROOT:-/tmp/geek-env-system}"

  log "Running first full install"
  bash "$REPO_ROOT/install.sh" | tee "$FIRST_LOG"

  log "Running second full install"
  bash "$REPO_ROOT/install.sh" | tee "$SECOND_LOG"

  log "Running smoke test suite"
  bash "$REPO_ROOT/tests/smoke-test.sh" | tee "$SMOKE_LOG"

  log "Asserting installed toolkit state"
  assert_file "$HOME/.zshrc"
  assert_dir "$HOME/.oh-my-zsh/custom/themes/powerlevel10k"
  assert_dir "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions"
  assert_dir "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting"
  assert_dir "$HOME/.zsh/zsh-autocomplete"
  assert_file "$GEEK_ENV_SYSTEM_ROOT/etc/default/zramswap"

  log "Checking idempotency signals"
  assert_log_contains "$SECOND_LOG" "Meslo Nerd Font already installed; skipping download"
  assert_log_contains "$SECOND_LOG" "Test mode enabled; skipping login shell change"
  assert_log_contains "$SECOND_LOG" "Skipping zramswap service activation"
  assert_log_contains "$SECOND_LOG" "[install] All requested components installed."
  assert_log_contains "$SMOKE_LOG" "Smoke test passed"

  log "Toolkit integration test passed"
}

main "$@"
