# geek-env

Bootstrap or refresh a Debian workstation from one cloned repo.

## What it installs

- `zsh` with Meslo Nerd Font, `powerlevel10k`, and shell completion
- `neovim` with Telescope, Treesitter, Mason/LSP, project root detection, breadcrumbs, and Codex
- `tmux` with TPM and a practical default config
- `alacritty` configured to use the Nerd Font and match the rest of the theme
- `i3wm` with a usable keyboard-driven config and `i3status`
- ZRAM-backed swap using `zstd`

## Fresh Debian flow

```bash
git clone <your-repo-url> ~/geek-env
cd ~/geek-env
./install.sh
```

This is the primary flow on Debian. The installer runs each setup
script in order and reapplies the repo configs into your home
directory.

## Partial installs

You can also install a subset:

```bash
./install.sh zsh nvim tmux
```

Available components:

- `zsh`
- `nvim`
- `tmux`
- `alacritty`
- `i3`
- `zram`

## Notes

- Most setup steps use `sudo` for packages and system config.
- Existing user configs are backed up before replacement.
- Re-running `./install.sh` works as an update pass.
- Git-based tools are pulled forward and repo configs are re-applied.
- The managed Neovim config is symlinked into `~/.config/nvim`, so repo edits show up there immediately.
- Neovim Codex integration assumes `codex` is already on your `PATH`.
- Use `nvim .` for the bundled editor setup. Plain `vim .` will not load the Neovim Codex integration.
- On startup, Neovim opens a VS Code style layout managed by `neo-tree` and `edgy.nvim`: explorer on the left, editor in the middle, shell below, and Codex on the right.
- Codex file opens are routed back into the main Neovim session using Neovim remote editing.
- The UI uses a VS Code themed colorscheme, top buffer tabs, and plugin-managed breadcrumbs.
- Tree-sitter is loaded eagerly at startup, and the config falls back to direct parser setup if `nvim-treesitter.configs` is unavailable.
- The managed `zsh` config exports `EDITOR=nvim`, `VISUAL=nvim`, and aliases `vim` to `nvim`.
- Keymaps: `<leader>e` toggles the file tree, `<leader>aa` toggles the Codex panel, `<leader>an` opens a new Codex panel, `<leader>at` toggles the shell panel, and `<leader>aT` opens a new shell panel.
- Diagnostics and symbols: `<leader>xx` toggles the diagnostics panel, `<leader>xX` toggles diagnostics for the current buffer, `<leader>cs` toggles the symbols panel, and `<leader>cl` toggles the LSP locations panel.
- Debian's stock `neovim` package can be too old for this config. `scripts/setup-nvim.sh` requires Neovim `0.11.0` or newer and installs a newer local `nvim` under `~/.local/bin` when needed.
- The Neovim setup installs the Node.js runtime but does not require `npm`.
- Debian is the main target, even if some scripts have other branches.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
