# Agent Vault Usage

This document is the command-level reference for the Agent Vault scripts.

## `scripts/setup-k3s-kata.sh`

Prepare a Debian host for Kata-backed agent vaults.

### Usage

```bash
sudo bash scripts/setup-k3s-kata.sh
```

### What it does

- installs k3s if needed
- installs Kata Containers
- writes the containerd template for Kata runtimes
- restarts k3s when required
- creates RuntimeClasses:
  - `kata-qemu`
  - `kata-clh`
  - `kata-qemu-tdx`
- runs a smoke test pod

### Verify

```bash
k3s kubectl get nodes
k3s kubectl get runtimeclass
```

## `scripts/new-agent.sh`

Generate and manage an agent vault.

### Create

```bash
bash scripts/new-agent.sh
```

The wizard collects:

- project name
- host path and mount path
- Kata runtime
- base image
- toolchain packages
- CPU, memory, and storage limits
- agent choice
- env vars and secrets
- optional NodePort exposure

### Agent defaults

- `OpenAI Codex` is the default agent
- Codex auto-installs `bubblewrap`
- Codex launches with `--dangerously-bypass-approvals-and-sandbox`
- Claude can be launched with `--dangerously-skip-permissions`

### Auth sources

Claude:

- `~/.claude/.credentials.json`
- `~/.config/claude/credentials.json`

Codex:

- `~/.codex/auth.json`
- optional `OPENAI_API_KEY` fallback

### Generated artifacts

```text
agents/
  <project>.yaml
  <project>.env
```

### Manage

```bash
bash scripts/new-agent.sh <project>
```

Actions:

- `exec`
- `update`
- `restart`
- `status`
- `delete`

### Attach behavior

- waits for the container to start
- streams logs during provisioning
- waits for `agent` and expected tools
- attaches in tmux as `agent`
- starts in the configured work directory

## Container Bootstrap

The generated vault reuses these repo scripts inside the container:

- `scripts/setup-zsh.sh`
- `scripts/setup-nvim.sh`
- `scripts/setup-tmux.sh`

It does not run `scripts/setup-alacritty.sh` inside the container.

## Troubleshooting

### Show status

```bash
bash scripts/new-agent.sh <project>
```

Choose `status`.

### Stop a vault

```bash
bash scripts/new-agent.sh <project>
```

Choose `delete`.

### Re-apply a saved manifest

```bash
bash scripts/new-agent.sh <project>
```

Choose `update`.
