#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
ZSH_CUSTOM_DIR="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
OH_MY_ZSH_DIR="${ZSH:-$HOME/.oh-my-zsh}"
P10K_DIR="$ZSH_CUSTOM_DIR/themes/powerlevel10k"
AUTOSUGGESTIONS_DIR="$ZSH_CUSTOM_DIR/plugins/zsh-autosuggestions"
SYNTAX_HIGHLIGHTING_DIR="$ZSH_CUSTOM_DIR/plugins/zsh-syntax-highlighting"
AUTOCOMPLETE_DIR="$HOME/.zsh/zsh-autocomplete"
FONT_VERSION="v3.4.0"
FONT_ARCHIVE="Meslo.zip"
FONT_URL="https://github.com/ryanoasis/nerd-fonts/releases/download/${FONT_VERSION}/${FONT_ARCHIVE}"

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
    fail "Unsupported system. Install zsh, git, curl, unzip, and a Nerd Font manually."
  fi
}

install_packages() {
  local manager
  manager="$(detect_pkg_manager)"

  case "$manager" in
    apt)
      sudo apt-get update
      sudo apt-get install -y zsh git curl unzip fontconfig
      ;;
    dnf)
      sudo dnf install -y zsh git curl unzip fontconfig
      ;;
    brew)
      brew install zsh git curl unzip fontconfig
      ;;
  esac
}

install_font() {
  local fonts_dir archive_path

  if [[ "$(uname -s)" == "Darwin" ]]; then
    fonts_dir="$HOME/Library/Fonts"
  else
    fonts_dir="$HOME/.local/share/fonts"
  fi

  mkdir -p "$fonts_dir"
  archive_path="$(mktemp "/tmp/${FONT_ARCHIVE}.XXXXXX")"

  log "Installing Meslo Nerd Font into $fonts_dir"
  curl -fsSL "$FONT_URL" -o "$archive_path"
  unzip -o "$archive_path" -d "$fonts_dir" >/dev/null
  rm -f "$archive_path"

  if command_exists fc-cache; then
    fc-cache -f "$fonts_dir" >/dev/null 2>&1 || true
  fi
}

clone_or_update_repo() {
  local repo_url target_dir
  repo_url="$1"
  target_dir="$2"

  if [[ -d "$target_dir/.git" ]]; then
    log "Updating $(basename "$target_dir")"
    git -C "$target_dir" pull --ff-only
  else
    log "Cloning $(basename "$target_dir")"
    git clone --depth=1 "$repo_url" "$target_dir"
  fi
}

install_oh_my_zsh() {
  if [[ -d "$OH_MY_ZSH_DIR/.git" ]]; then
    log "Updating oh-my-zsh"
    git -C "$OH_MY_ZSH_DIR" pull --ff-only
  elif [[ -d "$OH_MY_ZSH_DIR" ]]; then
    log "Keeping existing oh-my-zsh directory at $OH_MY_ZSH_DIR"
  else
    log "Cloning oh-my-zsh"
    git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$OH_MY_ZSH_DIR"
  fi
}

ensure_oh_my_zsh_layout() {
  mkdir -p "$ZSH_CUSTOM_DIR/themes" "$ZSH_CUSTOM_DIR/plugins" "$HOME/.zsh"
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
export POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true
export PATH="$HOME/.local/bin:$PATH"
export EDITOR="nvim"
export VISUAL="nvim"

plugins=(git python sudo zsh-autosuggestions zsh-syntax-highlighting)

ZSH_THEME="powerlevel10k/powerlevel10k"
source "\$ZSH/oh-my-zsh.sh"
source "$AUTOCOMPLETE_DIR/zsh-autocomplete.plugin.zsh"

zstyle ':autocomplete:*' min-input 1
zstyle ':autocomplete:*' recent-dirs yes

bindkey '^F' autosuggest-accept

alias vim='nvim'

[[ -r ~/.p10k.zsh ]] && source ~/.p10k.zsh
EOF
}

write_p10k_config() {
  local p10k
  p10k="$HOME/.p10k.zsh"

  if [[ -f "$p10k" ]]; then
    log "Keeping existing ~/.p10k.zsh"
    return
  fi

  cat >"$p10k" <<'EOF'
# Minimal Powerlevel10k configuration.
typeset -g POWERLEVEL9K_MODE=nerdfont-complete
typeset -g POWERLEVEL9K_LEFT_PROMPT_ELEMENTS=(dir vcs prompt_char)
typeset -g POWERLEVEL9K_RIGHT_PROMPT_ELEMENTS=(status command_execution_time background_jobs time)
typeset -g POWERLEVEL9K_PROMPT_ADD_NEWLINE=true
typeset -g POWERLEVEL9K_MULTILINE_FIRST_PROMPT_PREFIX=""
typeset -g POWERLEVEL9K_MULTILINE_LAST_PROMPT_PREFIX=""
typeset -g POWERLEVEL9K_SHORTEN_STRATEGY=truncate_to_unique
typeset -g POWERLEVEL9K_TIME_FORMAT='%D{%H:%M}'
typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_VIINS_CONTENT_EXPANSION='> '
typeset -g POWERLEVEL9K_PROMPT_CHAR_ERROR_VIINS_CONTENT_EXPANSION='! '
typeset -g POWERLEVEL9K_PROMPT_CHAR_OK_VICMD_CONTENT_EXPANSION='< '
typeset -g POWERLEVEL9K_PROMPT_CHAR_ERROR_VICMD_CONTENT_EXPANSION='< '
EOF
}

set_default_shell() {
  local zsh_path current_shell
  zsh_path="$(command -v zsh)"
  current_shell="${SHELL:-}"

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
  install_font
  install_oh_my_zsh
  ensure_oh_my_zsh_layout

  clone_or_update_repo https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
  clone_or_update_repo https://github.com/zsh-users/zsh-autosuggestions.git "$AUTOSUGGESTIONS_DIR"
  clone_or_update_repo https://github.com/zsh-users/zsh-syntax-highlighting.git "$SYNTAX_HIGHLIGHTING_DIR"
  clone_or_update_repo https://github.com/marlonrichert/zsh-autocomplete.git "$AUTOCOMPLETE_DIR"

  write_zshrc
  write_zshenv
  write_p10k_config
  set_default_shell

  log "Setup complete."
  log "Restart your terminal and select a Nerd Font variant such as 'MesloLGS NF' if your terminal does not switch fonts automatically."
}

main "$@"
