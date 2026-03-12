#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_CONFIG_DIR="$REPO_ROOT/config/nvim"
TARGET_CONFIG_DIR="$HOME/.config/nvim"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nvim"
LAZY_DIR="$DATA_DIR/lazy/lazy.nvim"

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
    fail "Unsupported system. Install Neovim and its dependencies manually."
  fi
}

install_packages() {
  local manager
  manager="$(detect_pkg_manager)"

  case "$manager" in
    apt)
      sudo apt-get update
      sudo apt-get install -y neovim git curl unzip gcc ripgrep fd-find python3-venv nodejs xclip
      ;;
    dnf)
      sudo dnf install -y neovim git curl unzip gcc ripgrep fd-find python3-virtualenv nodejs xclip
      ;;
    brew)
      brew install neovim git curl unzip ripgrep fd node
      ;;
  esac
}

backup_existing_config() {
  local backup_dir

  if [[ ! -d "$TARGET_CONFIG_DIR" ]]; then
    return
  fi

  backup_dir="${TARGET_CONFIG_DIR}.pre-geek-env.$(date +%Y%m%d%H%M%S)"
  cp -R "$TARGET_CONFIG_DIR" "$backup_dir"
  log "Backed up existing config to $backup_dir"
}

install_config() {
  mkdir -p "$(dirname "$TARGET_CONFIG_DIR")"
  rm -rf "$TARGET_CONFIG_DIR"
  cp -R "$SOURCE_CONFIG_DIR" "$TARGET_CONFIG_DIR"
  log "Installed Neovim config into $TARGET_CONFIG_DIR"
}

bootstrap_lazy() {
  if [[ -d "$LAZY_DIR/.git" ]]; then
    log "Updating lazy.nvim"
    git -C "$LAZY_DIR" pull --ff-only
    return
  fi

  mkdir -p "$(dirname "$LAZY_DIR")"
  log "Cloning lazy.nvim"
  git clone --filter=blob:none --branch=stable https://github.com/folke/lazy.nvim.git "$LAZY_DIR"
}

install_plugins() {
  log "Installing Neovim plugins"
  nvim --headless "+Lazy! sync" +qa
}

main() {
  [[ -d "$SOURCE_CONFIG_DIR" ]] || fail "Missing repo config at $SOURCE_CONFIG_DIR"

  install_packages
  backup_existing_config
  install_config
  bootstrap_lazy
  install_plugins

  log "Setup complete."
  log "Open Neovim and run :Mason to install language servers you want beyond the defaults."
}

main "$@"
