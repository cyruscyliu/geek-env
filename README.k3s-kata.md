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

## Headlamp Web UI

Headlamp is installed as the cluster web UI for browsing pods, logs, workloads,
services, and storage from a browser.

Resources:

- namespace: `kube-system`
- deployment: `headlamp`
- service: `headlamp`
- admin service account: `headlamp-admin`

### Access Directly

Use this only when you want to reach Headlamp directly and log in with a
Kubernetes token. This path bypasses Traefik, so any Traefik basic-auth
middleware will not apply.

`kubectl port-forward` is a foreground process, not a daemon. For a one-off
session, run:

```bash
kubectl -n kube-system port-forward --address 0.0.0.0 svc/headlamp 8081:80
```

To leave it running after closing the shell, use:

```bash
nohup kubectl -n kube-system port-forward --address 0.0.0.0 svc/headlamp 8081:80 >/tmp/headlamp-port-forward.log 2>&1 &
```

Open:

```text
http://<server-ip>:8081
```

Generate a login token:

```bash
kubectl -n kube-system create token headlamp-admin
```

Paste that token into the Headlamp login screen.

### Access Via Traefik Basic Auth

If Traefik is your ingress controller, you can put HTTP basic auth in front of
Headlamp without changing the Headlamp deployment itself. This is a separate
access path from the direct `svc/headlamp` port-forward above.

1. Generate a secret manifest with an htpasswd-style user entry:

```bash
bash scripts/render-headlamp-basic-auth-secret.sh admin 'replace-me' > /tmp/headlamp-basic-auth-secret.yaml
```

2. The example ingress in
   [`config/headlamp/headlamp-traefik-basic-auth.yaml`](config/headlamp/headlamp-traefik-basic-auth.yaml)
   has no host match, so it can be reached by server IP through Traefik.

3. Apply the secret and the Traefik middleware/ingress:

```bash
kubectl apply -f /tmp/headlamp-basic-auth-secret.yaml
kubectl apply -f config/headlamp/headlamp-traefik-basic-auth.yaml
```

4. Send traffic through Traefik, not directly to `svc/headlamp`. For a local
   session, stop any existing `svc/headlamp` port-forward and then port-forward
   Traefik on `8081:80`:

```bash
kubectl -n kube-system port-forward --address 0.0.0.0 svc/traefik 8081:80
```

To leave it running after closing the shell, use:

```bash
nohup kubectl -n kube-system port-forward --address 0.0.0.0 svc/traefik 8081:80 >/tmp/headlamp-traefik-port-forward.log 2>&1 &
```

Open:

```text
http://<server-ip>:8081
```

This adds:

- a `Secret` named `headlamp-basic-auth` in `kube-system`
- a Traefik `Middleware` named `headlamp-basic-auth`
- an `Ingress` named `headlamp` that routes to `svc/headlamp`

Notes:

- this protects the Headlamp URL at the ingress layer only
- port-forwarding `svc/headlamp` directly bypasses Traefik and will not trigger
  basic auth
- use either the direct `svc/headlamp` path or the Traefik path on `8081`, not
  both at the same time
- because the example ingress has no host match, requests by server IP can
  reach Headlamp through Traefik
- Kubernetes authorization still comes from the credentials used inside
  Headlamp, such as a token pasted into the login screen
- if you already expose Headlamp with a different `Ingress` or `IngressRoute`,
  attach the middleware there instead of applying the example ingress as-is

### Remove

```bash
kubectl delete clusterrolebinding headlamp-admin
kubectl -n kube-system delete serviceaccount headlamp-admin
kubectl delete -f https://raw.githubusercontent.com/kubernetes-sigs/headlamp/main/kubernetes-headlamp.yaml
```

## `scripts/agentctl.py`

Generate AI-native vault project config and manifests, and re-apply saved
projects.

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
- repo-local auth files under `secrets/agentctl/` are copied into the guest
  automatically when present
- `Codex` auto-installs `bubblewrap`
- `paseo` is auto-installed, starts during bootstrap, and persists pairing
  state under the mounted workspace

### Auth sources

Codex:

- `secrets/agentctl/codex/auth.json`
- optional `OPENAI_API_KEY` fallback
- optional `secrets/agentctl/codex/config.toml`

Claude Code:

- `secrets/agentctl/claude/settings.json`
- optional `ANTHROPIC_API_KEY` fallback

### Generated artifacts

```text
agents/
  <project>.agent.yaml
  <project>.yaml
```

### Apply A Saved Project

```bash
python3 scripts/agentctl.py <project>
```

This reloads `agents/<project>.agent.yaml`, re-renders `agents/<project>.yaml`,
applies it with `kubectl`, and waits for readiness when the pod template
changes.

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
