#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPONENTS=(
  "zsh"
  "nvim"
  "tmux"
  "alacritty"
  "i3"
  "zram"
)

log() {
  printf '[install] %s\n' "$*"
}

usage() {
  cat <<'EOF'
Usage:
  ./install.sh
  ./install.sh zsh nvim tmux

With no arguments, installs the full environment.
Available components: zsh, nvim, tmux, alacritty, i3, zram
EOF
}

run_component() {
  local component script
  component="$1"
  script="$SCRIPT_DIR/scripts/setup-${component}.sh"

  [[ -f "$script" ]] || {
    printf '[install] ERROR: missing installer for %s\n' "$component" >&2
    exit 1
  }

  log "Running ${component} setup"
  bash "$script"
}

main() {
  local requested=("$@")

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  if [[ "${#requested[@]}" -eq 0 ]]; then
    requested=("${COMPONENTS[@]}")
  fi

  for component in "${requested[@]}"; do
    case "$component" in
      zsh|nvim|tmux|alacritty|i3|zram)
        run_component "$component"
        ;;
      *)
        printf '[install] ERROR: unknown component: %s\n' "$component" >&2
        usage
        exit 1
        ;;
    esac
  done

  log "All requested components installed."
}

main "$@"
