# geek-env

Bootstrap or refresh a Debian workstation from one cloned repo.

## What it installs

- `zsh` with Meslo Nerd Font, `powerlevel10k`, and shell completion
- `neovim` with Telescope, Treesitter, LSP, completion, and Codex
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
- Neovim Codex integration assumes `codex` is already on your `PATH`.
- Debian is the main target, even if some scripts have other branches.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
