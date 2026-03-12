#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_I3_DIR="$REPO_ROOT/config/i3"
TARGET_I3_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/i3"
TARGET_I3STATUS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/i3status"

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
  else
    fail "Unsupported system. Install i3 manually."
  fi
}

install_packages() {
  case "$(detect_pkg_manager)" in
    apt)
      sudo apt-get update
      sudo apt-get install -y i3 i3status i3lock dmenu feh picom flameshot playerctl xss-lock
      ;;
    dnf)
      sudo dnf install -y i3 i3status i3lock dmenu feh picom flameshot playerctl xss-lock
      ;;
  esac
}

install_config() {
  [[ -d "$SOURCE_I3_DIR" ]] || fail "Missing i3 config at $SOURCE_I3_DIR"

  if [[ -d "$TARGET_I3_DIR" && ! -d "${TARGET_I3_DIR}.pre-geek-env" ]]; then
    cp -R "$TARGET_I3_DIR" "${TARGET_I3_DIR}.pre-geek-env"
    log "Backed up existing i3 config"
  fi

  if [[ -d "$TARGET_I3STATUS_DIR" && ! -d "${TARGET_I3STATUS_DIR}.pre-geek-env" ]]; then
    cp -R "$TARGET_I3STATUS_DIR" "${TARGET_I3STATUS_DIR}.pre-geek-env"
    log "Backed up existing i3status config"
  fi

  rm -rf "$TARGET_I3_DIR"
  rm -rf "$TARGET_I3STATUS_DIR"
  mkdir -p "$(dirname "$TARGET_I3_DIR")" "$(dirname "$TARGET_I3STATUS_DIR")"
  cp -R "$SOURCE_I3_DIR/i3" "$TARGET_I3_DIR"
  cp -R "$SOURCE_I3_DIR/i3status" "$TARGET_I3STATUS_DIR"
  log "Installed i3 and i3status config"
}

main() {
  install_packages
  install_config
  log "Setup complete. Select i3 at login to use the new config."
}

main "$@"
