#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_CONFIG_DIR="$REPO_ROOT/config/nvim"
TARGET_CONFIG_DIR="$HOME/.config/nvim"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/nvim"
LAZY_DIR="$DATA_DIR/lazy/lazy.nvim"
LOCAL_BIN_DIR="$HOME/.local/bin"
LOCAL_OPT_DIR="$HOME/.local/opt"
LOCAL_NVIM_ROOT="$LOCAL_OPT_DIR/nvim-linux-x86_64"
LOCAL_NVIM_BIN="$LOCAL_BIN_DIR/nvim"
NVIM_MIN_VERSION="0.10.0"
NVIM_TARBALL_URL="https://github.com/neovim/neovim/releases/download/stable/nvim-linux-x86_64.tar.gz"

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

version_ge() {
  [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | tail -n 1)" == "$1" ]]
}

current_nvim_version() {
  local nvim_bin

  if [[ -x "$LOCAL_NVIM_BIN" ]]; then
    nvim_bin="$LOCAL_NVIM_BIN"
  else
    nvim_bin="$(command -v nvim 2>/dev/null || true)"
  fi

  [[ -n "$nvim_bin" ]] || return 1
  "$nvim_bin" --version | awk 'NR==1 { sub(/^v/, "", $2); print $2 }'
}

current_nvim_bin() {
  if [[ -x "$LOCAL_NVIM_BIN" ]]; then
    printf '%s\n' "$LOCAL_NVIM_BIN"
    return
  fi

  command -v nvim 2>/dev/null || true
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
      sudo apt-get install -y git curl unzip tar gcc ripgrep fd-find python3-venv nodejs xclip
      ;;
    dnf)
      sudo dnf install -y neovim git curl unzip gcc ripgrep fd-find python3-virtualenv nodejs xclip
      ;;
    brew)
      brew install neovim git curl unzip ripgrep fd node
      ;;
  esac
}

install_local_nvim() {
  local tmp_dir

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' RETURN

  mkdir -p "$LOCAL_BIN_DIR" "$LOCAL_OPT_DIR"
  log "Installing Neovim into $LOCAL_NVIM_ROOT"
  curl -L "$NVIM_TARBALL_URL" -o "$tmp_dir/nvim.tar.gz"
  tar -xzf "$tmp_dir/nvim.tar.gz" -C "$tmp_dir"
  rm -rf "$LOCAL_NVIM_ROOT"
  cp -R "$tmp_dir"/nvim-linux-x86_64 "$LOCAL_NVIM_ROOT"
  ln -sfn "$LOCAL_NVIM_ROOT/bin/nvim" "$LOCAL_NVIM_BIN"
}

ensure_supported_nvim() {
  local manager
  local version

  manager="$(detect_pkg_manager)"
  version="$(current_nvim_version || true)"

  if [[ -n "$version" ]] && version_ge "$version" "$NVIM_MIN_VERSION"; then
    return
  fi

  case "$manager" in
    apt)
      install_local_nvim
      ;;
    *)
      fail "Neovim $NVIM_MIN_VERSION or newer is required. Install a newer Neovim and re-run this script."
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
  local nvim_bin

  nvim_bin="$(current_nvim_bin)"
  [[ -n "$nvim_bin" ]] || fail "Neovim is not installed."

  log "Installing Neovim plugins"
  "$nvim_bin" --headless "+Lazy! sync" +qa
}

main() {
  [[ -d "$SOURCE_CONFIG_DIR" ]] || fail "Missing repo config at $SOURCE_CONFIG_DIR"

  install_packages
  ensure_supported_nvim
  backup_existing_config
  install_config
  bootstrap_lazy
  install_plugins

  log "Setup complete."
  if [[ -x "$LOCAL_NVIM_BIN" ]]; then
    log "Using local Neovim at $LOCAL_NVIM_BIN"
  fi
  log "Open Neovim and run :Mason to install language servers you want beyond the defaults."
}

main "$@"
