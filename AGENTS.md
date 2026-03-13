# Repository Guidelines

## Project Structure & Module Organization
This repository bootstraps a Debian workstation from one checkout.
Top-level orchestration lives in
[install.sh](/home/debian/Projects/geek-env/install.sh), which dispatches
component installers in `scripts/` such as `setup-nvim.sh` and
`setup-zsh.sh`. Managed application configs live under `config/`:

- `config/nvim/`: Neovim config, organized as `lua/config/` for core
  settings and `lua/plugins/` for lazy.nvim plugin specs.
- `config/i3/`: `i3` and `i3status` configs.
- `config/alacritty/`: Alacritty TOML config.
- `config/tmux/`: tmux config copied into the user home directory.

## Build, Test, and Development Commands
- `./install.sh`: install or refresh the full environment.
- `./install.sh nvim zsh`: install only selected components.
- `bash -n install.sh scripts/setup-*.sh`: syntax-check installer scripts
  before committing.
- `nvim --headless "+Lazy! sync" +qa`: refresh Neovim plugins after
  editing `config/nvim/`.

Run commands from the repo root. Most setup scripts use `sudo` and
overwrite user config after creating `*.pre-geek-env*` backups.

## Coding Style & Naming Conventions
Use Bash with `set -euo pipefail`. Match the existing style with aligned
blocks and one statement per line. Keep helper functions short and
explicit (`log`, `fail`, `install_config`). Name setup scripts
`setup-<component>.sh`. In Neovim Lua, keep reusable plugin specs in
`config/nvim/lua/plugins/*.lua` and avoid ad hoc modules when a plugin
already covers the behavior.

## Testing Guidelines
There is no formal test suite. Validate changes with shell syntax checks
and a targeted dry run of the affected installer, for example
`./install.sh nvim`. Test installer changes with two user states:
a fresh install on a clean account and a repeat run on an existing
setup to confirm updates do not break re-application. For Neovim edits,
ensure startup succeeds and plugin specs load cleanly. Document any
checks you could not run because of sandbox, package, or network limits.

## Commit & Pull Request Guidelines
Recent commits use short, imperative subjects such as `Fix missing omz`
and `Refactor Neovim layout around plugins`. Keep commit titles
concise, capitalized, and focused on one change. Pull requests should
include:

- What component changed and why.
- Any user-visible behavior changes or new dependencies.
- Manual verification performed (`bash -n`, partial install run,
  Neovim startup).
- Screenshots only when changing UI-heavy configs such as `i3` or
  Neovim layout.

## Security & Configuration Tips
Do not commit machine-specific secrets, tokens, or hostnames. Keep repo
config generic and parameterize paths through `$HOME` or XDG
directories where possible.
