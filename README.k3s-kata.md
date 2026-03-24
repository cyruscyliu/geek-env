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

## `scripts/setup-k3s-kata-worker.sh`

Join an additional x64 Debian host to an existing k3s cluster as a Kata-capable
worker.

### Usage

On the current k3s server:

```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

On the new x64 worker:

```bash
export K3S_URL=https://<server-ip>:6443
export K3S_TOKEN=<node-token>
sudo -E bash scripts/setup-k3s-kata-worker.sh
```

Optional:

- set `K3S_NODE_NAME` to override the node name
- set `K3S_NODE_LABELS` to a comma-separated label list for the worker
- set `K3S_AGENT_EXTRA_ARGS` for extra `k3s agent` install flags

### What it does

- installs `k3s-agent` and joins the existing cluster
- installs Kata Containers for `amd64`
- writes the containerd template for Kata runtimes on the worker
- restarts `k3s-agent` when required

### Verify

From the server:

```bash
kubectl get nodes -o wide
kubectl describe node <worker-name>
```

## `scripts/agentctl.py`

Generate and manage an agent vault.

### Create

```bash
python3 scripts/agentctl.py
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

Memory and storage entries use Kubernetes binary units such as `Mi`, `Gi`, and
`Ti`. If you enter a bare number in the wizard or have an older saved
`agents/<project>.env`, `scripts/agentctl.py` normalizes it to `Gi` before
writing or reusing the manifest.

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
python3 scripts/agentctl.py <project>
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
- persists `/home/agent/.codex` and `/home/agent/.claude` under `<host-path>/.agent-state/`
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
python3 scripts/agentctl.py <project>
```

Choose `status`.

### Stop a vault

```bash
python3 scripts/agentctl.py <project>
```

Choose `delete`.

### Re-apply a saved manifest

```bash
python3 scripts/agentctl.py <project>
```

Choose `update`.

This reapplies `agents/<project>.yaml` as saved. It only rolls a new pod if the
saved manifest changes the Deployment pod template. The manage flow reports
whether it detected a rollout or is reusing the current pod before attaching,
and shows the pod it is watching plus provisioning logs once the new container
starts. Before applying, it also checks the requested CPU, memory, and
ephemeral storage against remaining requested headroom on ready schedulable
nodes and fails early if nothing in the cluster can fit the pod.

### Rebuild a container from current generator logic

```bash
python3 scripts/agentctl.py <project>
```

Choose `rebuild`.

This regenerates the container bootstrap section in `agents/<project>.yaml`
using the current `scripts/agentctl.py` logic, then reapplies the manifest.

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
