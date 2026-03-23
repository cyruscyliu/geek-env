# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

geek-env bootstraps a Debian workstation from a single git clone. `install.sh` orchestrates component installers in `scripts/setup-<component>.sh`. Managed application configs live under `config/`. Debian is the primary target.

## Commands

```bash
./install.sh                              # Install or refresh full environment
./install.sh nvim zsh                     # Install only selected components
bash -n install.sh scripts/setup-*.sh     # Syntax-check all scripts (run before committing)
nvim --headless "+Lazy! sync" +qa         # Refresh Neovim plugins after config edits
./tests/smoke-test.sh                     # Post-install validation suite
./tests/test-toolkit.sh                   # Docker-based integration test (full install x2, checks idempotency)
```

Run all commands from the repo root. Setup scripts use `sudo` and create `*.pre-geek-env.<timestamp>` backups before overwriting user config.

## Architecture

- **install.sh** — top-level orchestrator; dispatches to `scripts/setup-{zsh,nvim,tmux,alacritty,i3,zram}.sh`
- **scripts/** — each installer is standalone and idempotent; detects package manager (apt/dnf/brew)
- **config/nvim/** — Lua-based Neovim config: `lua/config/` (options, keymaps, lazy.nvim bootstrap) and `lua/plugins/` (lazy.nvim plugin specs split by concern: coding, editor, git, lsp, ui)
- **config/{i3,alacritty,tmux}/** — app configs symlinked or copied into user home directories
- **tests/** — smoke-test.sh validates installed state; test-toolkit.sh runs full install in a disposable Debian Docker container

Neovim config is **symlinked** into `~/.config/nvim`, so repo edits take effect immediately. Tmux and i3 configs are **copied**.

## Coding Conventions

- Bash: `set -euo pipefail`, aligned blocks, one statement per line, helpers like `log()`, `fail()`, `install_config()`
- Neovim Lua: plugin specs in `config/nvim/lua/plugins/*.lua`; prefer existing plugins over ad hoc modules
- Commits: short imperative subjects, one change per commit; update `README.md` Notes section when behavior or dependencies change

## Testing

No formal unit tests. Validate with:
1. `bash -n` syntax check on all shell scripts
2. Targeted dry run of the affected installer (`./install.sh nvim`)
3. Test both fresh install and re-run on existing setup
4. For Neovim changes, verify headless startup: `nvim --headless "+Lazy! sync" +qa`
5. Document any checks you could not run due to sandbox/network limits
