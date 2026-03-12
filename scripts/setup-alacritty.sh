#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_CONFIG_DIR="$REPO_ROOT/config/alacritty"
TARGET_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/alacritty"

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
    fail "Unsupported system. Install Alacritty manually."
  fi
}

install_packages() {
  case "$(detect_pkg_manager)" in
    apt)
      sudo apt-get update
      sudo apt-get install -y alacritty
      ;;
    dnf)
      sudo dnf install -y alacritty
      ;;
    brew)
      brew install --cask alacritty
      ;;
  esac
}

install_config() {
  [[ -d "$SOURCE_CONFIG_DIR" ]] || fail "Missing Alacritty config at $SOURCE_CONFIG_DIR"

  if [[ -d "$TARGET_CONFIG_DIR" && ! -d "${TARGET_CONFIG_DIR}.pre-geek-env" ]]; then
    cp -R "$TARGET_CONFIG_DIR" "${TARGET_CONFIG_DIR}.pre-geek-env"
    log "Backed up existing Alacritty config"
  fi

  rm -rf "$TARGET_CONFIG_DIR"
  cp -R "$SOURCE_CONFIG_DIR" "$TARGET_CONFIG_DIR"
  log "Installed Alacritty config into $TARGET_CONFIG_DIR"
}

main() {
  install_packages
  install_config
  log "Setup complete. Restart Alacritty to load the new config."
}

main "$@"
