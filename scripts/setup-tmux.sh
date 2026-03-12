#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_TMUX_CONF="$REPO_ROOT/config/tmux/.tmux.conf"
TARGET_TMUX_CONF="$HOME/.tmux.conf"
TPM_DIR="$HOME/.tmux/plugins/tpm"

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

detect_pkg_manager() {
  if command_exists apt-get; then
    echo "apt"
  elif command_exists dnf; then
    echo "dnf"
  elif command_exists brew; then
    echo "brew"
  else
    fail "Unsupported system. Install tmux manually."
  fi
}

install_packages() {
  case "$(detect_pkg_manager)" in
    apt)
      sudo apt-get update
      sudo apt-get install -y tmux git
      ;;
    dnf)
      sudo dnf install -y tmux git
      ;;
    brew)
      brew install tmux git
      ;;
  esac
}

install_config() {
  [[ -f "$SOURCE_TMUX_CONF" ]] || fail "Missing tmux config at $SOURCE_TMUX_CONF"

  if [[ -f "$TARGET_TMUX_CONF" && ! -f "${TARGET_TMUX_CONF}.pre-geek-env" ]]; then
    cp "$TARGET_TMUX_CONF" "${TARGET_TMUX_CONF}.pre-geek-env"
    log "Backed up existing ~/.tmux.conf"
  fi

  cp "$SOURCE_TMUX_CONF" "$TARGET_TMUX_CONF"
  log "Installed tmux config into $TARGET_TMUX_CONF"
}

install_tpm() {
  mkdir -p "$(dirname "$TPM_DIR")"

  if [[ -d "$TPM_DIR/.git" ]]; then
    log "Updating tmux plugin manager"
    git -C "$TPM_DIR" pull --ff-only
  else
    log "Cloning tmux plugin manager"
    git clone --depth=1 https://github.com/tmux-plugins/tpm "$TPM_DIR"
  fi
}

install_plugins() {
  "$TPM_DIR/bin/install_plugins"
  "$TPM_DIR/bin/update_plugins" all
}

main() {
  install_packages
  install_config
  install_tpm
  install_plugins
  log "Setup complete. Start tmux with: tmux"
}

main "$@"
