# Agent Vault Usage

This document is the command-level reference for the Agent Vault fleet
orchestration scripts.

## `scripts/setup-k3s-kata.sh`

Prepare a Debian host for Kata-backed agent vaults and multi-node scheduling.

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
- runs [`scripts/run-kata-smoke-test.sh`](scripts/run-kata-smoke-test.sh)

### Verify

```bash
k3s kubectl get nodes
k3s kubectl get runtimeclass
```

## `scripts/setup-k3s-kata-worker.sh`

Join an additional x64 Debian host to an existing k3s cluster as a Kata-capable
worker node.

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

Generate and manage an AI-native vault.

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
`Ti`. If you enter a bare number in the wizard, `scripts/agentctl.py`
normalizes it to `Gi` before saving the canonical config and rendered manifest.

### Agent defaults

- `Codex` and `Claude Code` are both installed in generated guests
- local auth files are copied into the guest automatically when present
- `Codex` auto-installs `bubblewrap`
- `paseo` is auto-installed, starts during bootstrap, and persists pairing
  state under the mounted workspace

### Auth sources

Codex:

- `~/.codex/auth.json`
- optional `OPENAI_API_KEY` fallback
- existing `~/.codex/auth.json` is reused automatically during container creation

Claude Code:

- `~/.config/claude-code/auth.json`
- `~/.claude.json`
- optional `ANTHROPIC_API_KEY` fallback

### Generated artifacts

```text
agents/
  <project>.agent.yaml
  <project>.yaml
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
- waits for the project user, `paseo`, and the expected agent CLI
- prints the current `paseo` pairing payload before attach when available
- attaches in a shell as the project user
- starts in the configured work directory
- mounts the host `~/.codex` into the project user's home so Codex state is shared across projects
- does not auto-run the coding agent on attach
- installs Codex behind a `codex` wrapper so the normal command includes the saved args
- installs Claude Code behind a `claude` wrapper so the normal command includes the saved args

## Troubleshooting

### Live validation

Use the dedicated integration checks when you need to exercise real `kubectl`
and Kata-backed pod lifecycle behavior:

```bash
python3 -m unittest tests/test_agentctl_k3s_integration.py
./tests/smoke-agentctl.sh
./tests/smoke-agentctl-paseo.sh
```

They skip cleanly when `kubectl` or the `kata-qemu` RuntimeClass is not
available.

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

This reapplies the rendered `agents/<project>.yaml` from the saved
`agents/<project>.agent.yaml` config. It only rolls a new pod if the rendered
manifest changes the Deployment pod template. The manage flow reports whether
it detected a rollout or is reusing the current pod before attaching, and shows
the pod it is watching plus provisioning logs once the new container starts.
Before applying, it also checks the requested CPU, memory, and ephemeral
storage against remaining requested headroom on ready schedulable nodes and
fails early if nothing in the cluster can fit the pod.

### Rebuild a container from current generator logic

```bash
python3 scripts/agentctl.py <project>
```

Choose `rebuild`.

This regenerates `agents/<project>.yaml` from `agents/<project>.agent.yaml`
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
