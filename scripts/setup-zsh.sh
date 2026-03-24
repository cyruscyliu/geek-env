#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
ZSH_CUSTOM_DIR="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
OH_MY_ZSH_DIR="${ZSH:-$HOME/.oh-my-zsh}"
AUTOSUGGESTIONS_DIR="$ZSH_CUSTOM_DIR/plugins/zsh-autosuggestions"
SYNTAX_HIGHLIGHTING_DIR="$ZSH_CUSTOM_DIR/plugins/zsh-syntax-highlighting"
SKIP_DEFAULT_SHELL_CHANGE="${SKIP_DEFAULT_SHELL_CHANGE:-0}"

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

dir_is_empty() {
  local dir
  dir="$1"

  [[ -d "$dir" ]] || return 0
  [[ -z "$(find "$dir" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]
}

detect_pkg_manager() {
  if command_exists apt-get; then
    echo "apt"
  elif command_exists dnf; then
    echo "dnf"
  elif command_exists brew; then
    echo "brew"
  else
    fail "Unsupported system. Install zsh, git, and curl manually."
  fi
}

install_packages() {
  local manager
  manager="$(detect_pkg_manager)"

  case "$manager" in
    apt)
      sudo apt-get update || log "apt-get update had errors (non-fatal), continuing"
      sudo apt-get install -y zsh git curl
      ;;
    dnf)
      sudo dnf install -y zsh git curl
      ;;
    brew)
      brew install zsh git curl
      ;;
  esac
}

clone_or_update_repo() {
  local repo_url target_dir
  repo_url="$1"
  target_dir="$2"

  if [[ -d "$target_dir/.git" ]]; then
    log "Updating $(basename "$target_dir")"
    git -C "$target_dir" pull --ff-only
  elif [[ -d "$target_dir" ]] && ! dir_is_empty "$target_dir"; then
    fail "$(basename "$target_dir") exists at $target_dir but is not a git checkout; move it aside and rerun."
  else
    log "Cloning $(basename "$target_dir")"
    git clone --depth=1 "$repo_url" "$target_dir"
  fi
}

install_oh_my_zsh() {
  local framework_file temp_dir
  framework_file="$OH_MY_ZSH_DIR/oh-my-zsh.sh"

  if [[ -d "$OH_MY_ZSH_DIR/.git" ]]; then
    log "Updating oh-my-zsh"
    git -C "$OH_MY_ZSH_DIR" pull --ff-only
  elif [[ -f "$framework_file" ]]; then
    log "Keeping existing oh-my-zsh directory at $OH_MY_ZSH_DIR"
  elif [[ -d "$OH_MY_ZSH_DIR" ]] && ! dir_is_empty "$OH_MY_ZSH_DIR"; then
    log "Repairing partial oh-my-zsh directory at $OH_MY_ZSH_DIR"
    temp_dir="$(mktemp -d)"
    git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$temp_dir"
    rm -rf "$temp_dir/custom"
    cp -a "$temp_dir/." "$OH_MY_ZSH_DIR/"
    rm -rf "$temp_dir"
  elif [[ -d "$OH_MY_ZSH_DIR" ]]; then
    log "Cloning oh-my-zsh into existing empty directory"
    git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$OH_MY_ZSH_DIR"
  else
    log "Cloning oh-my-zsh"
    git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$OH_MY_ZSH_DIR"
  fi
}

ensure_oh_my_zsh_layout() {
  mkdir -p "$ZSH_CUSTOM_DIR/plugins" "$HOME/.zsh"
}

write_zshenv() {
  local zshenv
  zshenv="$HOME/.zshenv"

  if [[ -f "$zshenv" && ! -f "${zshenv}.pre-geek-env" ]]; then
    cp "$zshenv" "${zshenv}.pre-geek-env"
    log "Backed up existing ~/.zshenv to ~/.zshenv.pre-geek-env"
  fi

  cat >"$zshenv" <<'EOF'
skip_global_compinit=1
EOF
}

write_zshrc() {
  local zshrc
  zshrc="$HOME/.zshrc"

  if [[ -f "$zshrc" && ! -f "${zshrc}.pre-geek-env" ]]; then
    cp "$zshrc" "${zshrc}.pre-geek-env"
    log "Backed up existing ~/.zshrc to ~/.zshrc.pre-geek-env"
  fi

  cat >"$zshrc" <<EOF
export ZSH="$OH_MY_ZSH_DIR"
export ZSH_CUSTOM="${ZSH_CUSTOM_DIR}"
export PATH="\$HOME/.local/bin:\$PATH"
export EDITOR="nvim"
export VISUAL="nvim"

plugins=(git python sudo zsh-autosuggestions zsh-syntax-highlighting)

ZSH_THEME=""
[[ -r "\$ZSH/oh-my-zsh.sh" ]] && source "\$ZSH/oh-my-zsh.sh"

if [[ -o interactive ]] && [[ -t 0 ]] && [[ -t 1 ]]; then
  bindkey '^F' autosuggest-accept
fi

alias vim='nvim'

if [[ -o interactive ]] && [[ -t 0 ]] && [[ -t 1 ]]; then
  PROMPT='%n@%m:%~ %# '
  RPROMPT=''
fi
EOF
}

set_default_shell() {
  local zsh_path current_shell
  zsh_path="$(command -v zsh)"
  current_shell="${SHELL:-}"

  if [[ "$SKIP_DEFAULT_SHELL_CHANGE" == "1" ]]; then
    log "Skipping login shell change"
    return
  fi

  if [[ "${GEEK_ENV_TEST_MODE:-0}" == "1" ]]; then
    log "Test mode enabled; skipping login shell change"
    return
  fi

  if [[ "$current_shell" == "$zsh_path" ]]; then
    log "Default shell is already $zsh_path"
    return
  fi

  if command_exists chsh; then
    log "Changing default shell to $zsh_path"
    chsh -s "$zsh_path"
  else
    log "chsh not found; set your login shell to $zsh_path manually"
  fi
}

main() {
  install_packages
  install_oh_my_zsh
  ensure_oh_my_zsh_layout

  clone_or_update_repo https://github.com/zsh-users/zsh-autosuggestions.git "$AUTOSUGGESTIONS_DIR"
  clone_or_update_repo https://github.com/zsh-users/zsh-syntax-highlighting.git "$SYNTAX_HIGHLIGHTING_DIR"

  write_zshrc
  write_zshenv
  set_default_shell

  log "Setup complete."
}

main "$@"
