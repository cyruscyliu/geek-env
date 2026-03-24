#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

assert_file() {
  local path
  path="$1"
  [[ -f "$path" ]] || fail "Missing file: $path"
}

assert_dir() {
  local path
  path="$1"
  [[ -d "$path" ]] || fail "Missing directory: $path"
}

assert_symlink_target() {
  local path target
  path="$1"
  target="$2"

  [[ -L "$path" ]] || fail "Missing symlink: $path"
  [[ "$(readlink "$path")" == "$target" ]] || fail "Expected $path -> $target"
}

run_check() {
  local description
  description="$1"
  shift

  log "$description"
  "$@"
}

check_zsh() {
  assert_file "$HOME/.zshrc"
  assert_file "$HOME/.zshenv"
  assert_dir "$HOME/.oh-my-zsh"
  zsh -ic 'exit 0'

  if command_exists python3; then
    python3 - <<'PY'
import os
import pty
import select
import subprocess
import sys
import time

try:
    master_fd, slave_fd = pty.openpty()
except OSError as exc:
    print(f"Skipping python3 REPL prompt check: {exc}", file=sys.stderr)
    sys.exit(0)

proc = subprocess.Popen(
    ["zsh", "-ic", "python3 -q"],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    close_fds=True,
)
os.close(slave_fd)

output = bytearray()
deadline = time.time() + 15
found_prompt = False

try:
    while time.time() < deadline:
        readable, _, _ = select.select([master_fd], [], [], 0.2)
        if not readable:
            continue

        chunk = os.read(master_fd, 4096)
        if not chunk:
            break

        output.extend(chunk)
        if b">>> " in output:
            found_prompt = True
            break
finally:
    if proc.poll() is None:
        try:
            os.write(master_fd, b"exit()\n")
        except OSError:
            pass

        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)

    os.close(master_fd)

if not found_prompt:
    sys.stderr.write(output.decode("utf-8", "replace"))
    raise SystemExit("python3 interactive prompt was not visible under zsh")
PY
  fi
}

check_nvim() {
  local nvim_bin

  assert_symlink_target "$HOME/.config/nvim" "$REPO_ROOT/config/nvim"
  assert_dir "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/lazy/lazy.nvim"

  if [[ -x "$HOME/.local/bin/nvim" ]]; then
    nvim_bin="$HOME/.local/bin/nvim"
  else
    nvim_bin="$(command -v nvim)"
  fi

  timeout 180 "$nvim_bin" --headless '+qall'
}

check_tmux() {
  assert_file "$HOME/.tmux.conf"
  assert_dir "$HOME/.tmux/plugins/tpm"
  tmux -f "$HOME/.tmux.conf" -L geek-env-smoke start-server
  tmux -L geek-env-smoke kill-server
}

check_alacritty() {
  assert_file "${XDG_CONFIG_HOME:-$HOME/.config}/alacritty/alacritty.toml"

  if command_exists python3; then
    python3 - <<'PY'
import pathlib
import tomllib

path = pathlib.Path.home() / ".config" / "alacritty" / "alacritty.toml"
with path.open("rb") as handle:
    tomllib.load(handle)
PY
  fi

  command_exists alacritty || fail "alacritty binary not found"

  if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
    timeout 30 alacritty --config-file "${XDG_CONFIG_HOME:-$HOME/.config}/alacritty/alacritty.toml" -e true
  else
    log "Skipping Alacritty launch smoke test because no graphical display is available"
  fi
}

check_i3() {
  assert_file "${XDG_CONFIG_HOME:-$HOME/.config}/i3/config"
  assert_file "${XDG_CONFIG_HOME:-$HOME/.config}/i3status/config"
  i3 -C -c "${XDG_CONFIG_HOME:-$HOME/.config}/i3/config"
}

check_zram() {
  local zram_apt zram_dnf

  zram_apt="${GEEK_ENV_SYSTEM_ROOT:-}/etc/default/zramswap"
  zram_dnf="${GEEK_ENV_SYSTEM_ROOT:-}/etc/systemd/zram-generator.conf.d/geek-env.conf"

  if [[ -n "${GEEK_ENV_SYSTEM_ROOT:-}" ]]; then
    [[ -f "$zram_apt" || -f "$zram_dnf" ]] || fail "Missing container-safe zram config"
    return
  fi

  [[ -f /etc/default/zramswap || -f /etc/systemd/zram-generator.conf.d/geek-env.conf ]] || fail "Missing zram config"
}

main() {
  export PATH="$HOME/.local/bin:$PATH"

  run_check "Smoke testing zsh" check_zsh
  run_check "Smoke testing nvim" check_nvim
  run_check "Smoke testing tmux" check_tmux
  run_check "Smoke testing alacritty" check_alacritty
  run_check "Smoke testing i3" check_i3
  run_check "Smoke testing zram" check_zram
  log "Smoke test passed"
}

main "$@"
