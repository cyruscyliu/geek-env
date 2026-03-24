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
- supported agents prompt once for permissive mode and default to `yes`
- Codex auto-installs `bubblewrap`
- permissive Codex launches with `--dangerously-bypass-approvals-and-sandbox`
- permissive Claude launches with `--dangerously-skip-permissions`
- permissive mode can be disabled during generation for stricter containers

### Auth sources

Claude:

- `~/.claude/.credentials.json`
- `~/.config/claude/credentials.json`
- existing Claude credentials are reused automatically during container creation

Codex:

- `~/.codex/auth.json`
- optional `OPENAI_API_KEY` fallback
- existing `~/.codex/auth.json` is reused automatically during container creation

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
- `rebuild`
- `restart`
- `status`
- `delete`

### Attach behavior

- waits for the container to start
- streams logs during provisioning
- waits for `agent` and expected tools
- attaches in tmux as `agent`
- starts in the configured work directory
- does not auto-run the coding agent on attach
- installs the selected agent behind a wrapper named `codex` or `claude` so the normal command includes the saved args

## Container Bootstrap

The generated vault reuses these repo scripts inside the container:

- `scripts/setup-zsh.sh`
- `scripts/setup-nvim.sh`
- `scripts/setup-tmux.sh`

It does not run `scripts/setup-alacritty.sh` inside the container.
The generated `agent` account is switched to `zsh` after provisioning.

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

This reapplies `agents/<project>.yaml` as saved. It only rolls a new pod if the
saved manifest changes the Deployment pod template.

### Rebuild a container from current generator logic

```bash
bash scripts/new-agent.sh <project>
```

Choose `rebuild`.

This regenerates the container bootstrap section in `agents/<project>.yaml`
using the current `scripts/new-agent.sh` logic, then reapplies the manifest.

## `scripts/refresh-k3s-network.sh`

Refresh k3s after switching between networks such as office, home, or VPN.

### Usage

```bash
sudo bash scripts/refresh-k3s-network.sh
```

### What it does

- prints the current host resolver state
- restarts `k3s`
- waits for the node to become `Ready`
- waits for `coredns` and `metrics-server` rollouts
- verifies `v1beta1.metrics.k8s.io` is available
- runs `kubectl top nodes` as a final sanity check
