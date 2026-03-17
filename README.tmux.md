# Tmux

Terminal multiplexer configured with Catppuccin Mocha theme, vi copy mode, and session persistence.

## Install

```bash
./install.sh tmux
```

The config is copied to `~/.tmux.conf`. Plugins are managed by TPM and installed automatically.

## Prefix Key

The prefix is **Ctrl+Space** (instead of the default Ctrl+b).

All bindings below are prefixed unless noted otherwise.

## Keyboard Shortcuts

### Windows (Tabs)

| Shortcut | Action |
|---|---|
| `c` | New window (keeps current path) |
| `Space` | Toggle last window |
| `<` | Move window left |
| `>` | Move window right |
| `0-9` | Switch to window by number |

### Panes (Splits)

| Shortcut | Action |
|---|---|
| `\|` | Split vertically |
| `-` | Split horizontally |
| `h` / `j` / `k` / `l` | Navigate panes (vim-style, repeatable) |
| `H` / `J` / `K` / `L` | Resize panes by 5 cells (repeatable) |

These also have Alacritty shortcuts (no prefix needed, requires tmux running):

| Alacritty Shortcut | Action |
|---|---|
| `Ctrl+Shift+D` | Split vertically |
| `Ctrl+D` | Split horizontally |
| `Ctrl+Shift+H/J/K/L` | Navigate panes |
| `Ctrl+Shift+T` | New window |

### Copy Mode

Enter copy mode with `prefix + [` or by scrolling up with the mouse.

| Shortcut | Action |
|---|---|
| `v` | Begin selection |
| `Ctrl+v` | Toggle rectangle selection |
| `y` | Yank selection to clipboard |

Mouse selections are automatically copied to the clipboard via tmux-yank.

### Session Management

| Shortcut | Action |
|---|---|
| `d` | Detach from session |
| `s` | List sessions |
| `$` | Rename session |
| `r` | Reload config |

Closing the last pane in a session switches to another session instead of detaching (detach-on-destroy off).

## Plugins

| Plugin | Purpose |
|---|---|
| **tpm** | Plugin manager |
| **catppuccin/tmux** | Mocha theme with rounded window status |
| **tmux-sensible** | Sensible defaults (escape-time 0, focus-events on, etc.) |
| **tmux-yank** | System clipboard integration |
| **tmux-resurrect** | Save/restore sessions (`prefix + Ctrl+s` save, `prefix + Ctrl+r` restore) |
| **tmux-continuum** | Auto-saves sessions every 15 minutes, auto-restores on tmux start |

## Features

- **Catppuccin Mocha** theme matching Alacritty and Neovim
- **True color + undercurl** support for Neovim LSP diagnostics
- **Vi copy mode** with visual selection
- **Mouse support** for scrolling, pane selection, and resizing
- **100k line scrollback** history
- **Session persistence** across reboots via resurrect + continuum
- **Windows start at 1** (not 0) and auto-renumber on close
- **Status bar at top** with session name, date, and time
