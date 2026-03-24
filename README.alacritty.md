# Alacritty

GPU-accelerated terminal emulator configured with Catppuccin Mocha theme, DejaVu Sans Mono, and tmux integration.

## Install

```bash
./install.sh alacritty
```

The setup script auto-detects your display resolution and sets an appropriate font size. The config is copied (not symlinked) to `~/.config/alacritty/alacritty.toml`.

## Keyboard Shortcuts

### Alacritty

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+N` | New window |
| `Ctrl+Shift+C` | Copy |
| `Ctrl+Shift+V` | Paste |
| `Ctrl+=` | Increase font size |
| `Ctrl+-` | Decrease font size |
| `Ctrl+0` | Reset font size |

### Tmux Integration

These shortcuts send tmux prefix (`Ctrl+Space`) sequences and only work inside a tmux session.

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+D` | Split pane vertically |
| `Ctrl+D` | Split pane horizontally |
| `Ctrl+Shift+H` | Move to left pane |
| `Ctrl+Shift+J` | Move to pane below |
| `Ctrl+Shift+K` | Move to pane above |
| `Ctrl+Shift+L` | Move to right pane |
| `Ctrl+Shift+T` | New tmux window (tab) |
| `Ctrl+Shift+Left` | Previous tmux window |
| `Ctrl+Shift+Right` | Next tmux window |
| `Ctrl+Shift+S` | Open tmux session list |

Tmux also binds the underlying `p` and `n` window switches in copy mode, so the same Alacritty window shortcuts continue to work there.

## Font Size by Resolution

The setup script picks a font size based on display height:

| Resolution | Font Size |
|---|---|
| 4K (2160p+) | 13.0 |
| QHD+ (1800p) | 11.5 |
| QHD (1440p) | 11.0 |
| FHD (1080p-1200p) | 10.0 |
| Below 1080p | 9.5 |
| Unknown / headless | 10.0 |

## Features

- **Catppuccin Mocha** color scheme
- **DejaVu Sans Mono** as the default terminal font
- **1px line spacing** (`font.offset.y = 1`) for readability
- **Auto-copy on select** (`save_to_clipboard = true`)
- **50k line scrollback** with multiplier 3
- **Mouse hides while typing**
- **Hollow cursor** when window loses focus
- **Live config reload** — edits to `alacritty.toml` apply immediately
