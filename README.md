# geek-env

Bootstrap or refresh a Debian workstation from one cloned repo.

## What it installs

- `zsh` with Meslo Nerd Font, `powerlevel10k`, and shell completion
- `neovim` with blink.cmp, Telescope, Treesitter, Mason/LSP, gitsigns, conform, flash, and breadcrumbs
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

## Docker test

Use the Docker harness for a repeatable full-toolkit integration run:

```bash
./tests/test-toolkit.sh
```

This builds a disposable Debian container, runs `./install.sh` twice as a
normal user with passwordless `sudo`, and verifies the installed state for
`zsh`, `nvim`, `tmux`, `alacritty`, `i3`, and container-safe `zram`
configuration output.

## Smoke test

Use the smoke suite after an install or update pass:

```bash
./tests/smoke-test.sh
```

It checks that the configured toolkit starts cleanly enough to catch obvious
breakage: interactive `zsh`, headless `nvim`, `tmux`, `i3` config validation,
Alacritty config parsing, and installed `zram` configuration.

## Notes

- Most setup steps use `sudo` for packages and system config.
- Existing user configs are backed up before replacement.
- Re-running `./install.sh` works as an update pass.
- Git-based tools are pulled forward and repo configs are re-applied.
- The `zsh` installer skips the Meslo Nerd Font download when it is already installed.
- The managed Neovim config is symlinked into `~/.config/nvim`, so repo edits show up there immediately.
- On startup, Neovim opens a VS Code style layout managed by `neo-tree` and `edgy.nvim`: explorer on the left and editor in the middle.
- The UI uses a VS Code themed colorscheme, top buffer tabs, and plugin-managed breadcrumbs.
- Tree-sitter is loaded eagerly at startup, and the config falls back to direct parser setup if `nvim-treesitter.configs` is unavailable.
- The managed `zsh` config exports `EDITOR=nvim`, `VISUAL=nvim`, and aliases `vim` to `nvim`.
- SSH sessions use a plain ASCII `zsh` prompt instead of the Nerd Font `powerlevel10k` prompt to avoid broken glyphs on remote hosts.
- The Alacritty installer computes the font size from the detected display height when `xrandr` is available, falling back to `10.0` for unknown or headless environments.
- Keymaps: `<leader>e` toggles the file tree, `<S-h>`/`<S-l>` cycle buffers, `s` triggers flash jump, `<leader>cf` formats the buffer.
- Git: `]h`/`[h` navigate hunks, `<leader>hs` stages a hunk, `<leader>hp` previews, `<leader>hb` shows blame.
- Text objects: `af`/`if` select functions, `ac`/`ic` select classes, `aa`/`ia` select arguments; `]f`/`[f` jump between functions.
- Diagnostics and symbols: `<leader>xx` toggles the diagnostics panel, `<leader>xX` toggles diagnostics for the current buffer, `<leader>cs` toggles the symbols panel, and `<leader>cl` toggles the LSP locations panel.
- Formatting: conform.nvim formats on save using `shfmt` (shell), `stylua` (Lua), `black` (Python), and `prettier` (JS/TS/JSON/YAML/Markdown). Formatters are installed on demand via Mason.
- Debian's stock `neovim` package can be too old for this config. `scripts/setup-nvim.sh` requires Neovim `0.11.0` or newer and installs a newer local `nvim` under `~/.local/bin` when needed.
- The Neovim setup installs the Node.js runtime but does not require `npm`.
- Debian is the main target, even if some scripts have other branches.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
