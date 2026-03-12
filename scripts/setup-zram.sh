#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

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
    fail "Unsupported system. Configure ZRAM manually."
  fi
}

install_packages() {
  local manager
  manager="$(detect_pkg_manager)"

  case "$manager" in
    apt)
      sudo apt-get update
      sudo apt-get install -y zram-tools
      ;;
    dnf)
      sudo dnf install -y zram-generator-defaults
      ;;
  esac
}

configure_apt() {
  sudo tee /etc/default/zramswap >/dev/null <<'EOF'
ALGO=zstd
PERCENT=100
PRIORITY=100
EOF

  sudo systemctl enable --now zramswap.service
}

configure_dnf() {
  sudo mkdir -p /etc/systemd/zram-generator.conf.d
  sudo tee /etc/systemd/zram-generator.conf.d/geek-env.conf >/dev/null <<'EOF'
[zram0]
zram-size = ram
compression-algorithm = zstd
swap-priority = 100
fs-type = swap
EOF

  sudo systemctl daemon-reload
  sudo systemctl restart systemd-zram-setup@zram0.service
}

main() {
  install_packages

  case "$(detect_pkg_manager)" in
    apt)
      configure_apt
      ;;
    dnf)
      configure_dnf
      ;;
  esac

  log "ZRAM swap enabled with zstd compression."
  swapon --show
}

main "$@"
