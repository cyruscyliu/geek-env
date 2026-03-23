# Agent Vault

Run coding agents in VM-backed sandboxes, switch on permissive mode, and let
them ship without constant approval babysitting.

![Platform](https://img.shields.io/badge/platform-k3s-blue)
![Isolation](https://img.shields.io/badge/isolation-Kata%20Containers-6f42c1)
![Agent](https://img.shields.io/badge/agent-Codex%20%7C%20Claude%20Code-0a7ea4)
![Shell](https://img.shields.io/badge/shell-tmux%20%7C%20zsh%20%7C%20Neovim-2ea44f)
![License](https://img.shields.io/badge/license-MIT-black)

## Description

Agent Vault turns this repo into a single-node control plane for isolated coding
agents. It provisions k3s plus Kata Containers on Debian, then launches each
agent in its own Kubernetes namespace with a mounted workspace, tmux session,
and repo-managed shell/editor environment.

## Quick Start

```bash
grep -c vmx /proc/cpuinfo
sudo bash scripts/setup-k3s-kata.sh
bash scripts/new-agent.sh
```

Recommended first vault:

- runtime: `kata-qemu`
- image: `debian:trixie-slim`
- agent: `OpenAI Codex`
- deploy: `yes`

To re-enter or manage it later:

```bash
bash scripts/new-agent.sh <project>
```

For tool-specific usage details, see:

- [`README.k3s-kata.md`](README.k3s-kata.md)
- [`README.tmux.md`](README.tmux.md)
- [`README.alacritty.md`](README.alacritty.md)
- [`README.vim.md`](README.vim.md)

## Contribute

- keep Bash scripts idempotent and explicit
- use `set -euo pipefail`
- update docs when behavior changes
- validate with:

```bash
bash -n scripts/new-agent.sh scripts/setup-k3s-kata.sh
./tests/smoke-test.sh
```

If you change command flow or generated manifests, update the relevant usage
docs under the README files in the repo root.

## License

MIT. See [`LICENSE`](LICENSE).
