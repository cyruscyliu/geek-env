# Agent Vault

Run coding agents in VM-backed sandboxes, switch on permissive mode, and let
them ship without constant approval babysitting.

![Platform](https://img.shields.io/badge/platform-k3s-blue)
![Isolation](https://img.shields.io/badge/isolation-Kata%20Containers-6f42c1)
![Agent](https://img.shields.io/badge/agent-Codex-0a7ea4)
![Shell](https://img.shields.io/badge/shell-tmux%20%7C%20zsh%20%7C%20Neovim-2ea44f)
![License](https://img.shields.io/badge/license-MIT-black)

## Description

Agent Vault turns this repo into a k3s control plane for isolated coding
agents. It provisions k3s plus Kata Containers on Debian, then launches each
agent in its own Kubernetes namespace with a mounted workspace, tmux session,
and repo-managed shell/editor environment. Supported agent containers default
to permissive mode during generation, with a prompt to disable it when needed.

## Quick Start

```bash
grep -c vmx /proc/cpuinfo
sudo bash scripts/setup-k3s-kata.sh
python3 scripts/agentctl.py
```

To re-enter or manage it later:

```bash
python3 scripts/agentctl.py <project>
```

For tool-specific usage details, see:

- [`README.k3s-kata.md`](README.k3s-kata.md)
- [`README.tmux.md`](README.tmux.md)
- [`README.alacritty.md`](README.alacritty.md)
- [`README.vim.md`](README.vim.md)

You can also add additional x64 Kata worker nodes with
[`scripts/setup-k3s-kata-worker.sh`](scripts/setup-k3s-kata-worker.sh).

## Notes

- `scripts/agentctl.py` stores each agent as a canonical
  `agents/<project>.agent.yaml` config and renders `agents/<project>.yaml`
  from it when applying or rebuilding.
- Memory and storage limits use Kubernetes-style binary units such as `Gi` or
  `Mi`. Bare values entered in the wizard are normalized to `Gi`.

## Contribute

- update docs when behavior changes
- validate with:

```bash
python3 -m py_compile scripts/agentctl.py
bash -n scripts/setup-k3s-kata.sh
python3 -m unittest tests/test_agentctl_user_story.py
python3 -m unittest tests/test_agentctl_k3s_integration.py
./tests/smoke-agentctl.sh
./tests/smoke-test.sh
```

If you change command flow or generated manifests, update the relevant usage
docs under the README files in the repo root.

## License

MIT. See [`LICENSE`](LICENSE).
