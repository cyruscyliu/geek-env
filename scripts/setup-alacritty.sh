#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_CONFIG_DIR="$REPO_ROOT/config/alacritty"
TARGET_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/alacritty"
CONFIG_FILE="alacritty.toml"

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
      sudo apt-get update || log "apt-get update had errors (non-fatal), continuing"
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

compute_font_size() {
  local height
  height="$(detect_display_height || true)"

  case "$height" in
    ''|*[!0-9]*)
      printf '10.0\n'
      ;;
    *)
      if (( height >= 2160 )); then
        printf '13.0\n'
      elif (( height >= 1800 )); then
        printf '11.5\n'
      elif (( height >= 1440 )); then
        printf '11.0\n'
      elif (( height >= 1080 )); then
        printf '10.0\n'
      else
        printf '9.5\n'
      fi
      ;;
  esac
}

detect_display_height() {
  local resolution

  [[ -n "${DISPLAY:-}" ]] || return 1
  command_exists xrandr || return 1

  resolution="$(xrandr --current 2>/dev/null | awk '/\*/ { print $1; exit }')"
  [[ -n "$resolution" ]] || return 1

  printf '%s\n' "${resolution##*x}"
}

install_config() {
  local font_size source_file target_file

  [[ -d "$SOURCE_CONFIG_DIR" ]] || fail "Missing Alacritty config at $SOURCE_CONFIG_DIR"
  source_file="$SOURCE_CONFIG_DIR/$CONFIG_FILE"
  target_file="$TARGET_CONFIG_DIR/$CONFIG_FILE"
  [[ -f "$source_file" ]] || fail "Missing Alacritty config file at $source_file"

  if [[ -d "$TARGET_CONFIG_DIR" && ! -d "${TARGET_CONFIG_DIR}.pre-geek-env" ]]; then
    cp -R "$TARGET_CONFIG_DIR" "${TARGET_CONFIG_DIR}.pre-geek-env"
    log "Backed up existing Alacritty config"
  fi

  rm -rf "$TARGET_CONFIG_DIR"
  mkdir -p "$TARGET_CONFIG_DIR"
  font_size="$(compute_font_size)"
  sed "s/^size = .*/size = ${font_size}/" "$source_file" >"$target_file"
  log "Installed Alacritty config into $TARGET_CONFIG_DIR with font size $font_size"
}

main() {
  install_packages
  install_config
  log "Setup complete. Restart Alacritty to load the new config."
}

main "$@"
