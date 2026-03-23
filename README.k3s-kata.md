# k3s + Kata Containers — Isolated Coding Agents

Run AI coding agents (Claude Code, OpenAI Codex) inside hardware-isolated VMs
on a single Debian node. Each agent gets its own Kubernetes namespace, a
`kata-qemu` (or Cloud Hypervisor / TDX) sandbox, a host directory mounted into
the VM, and a persistent tmux session.

## Prerequisites

| Requirement | Notes |
|---|---|
| Debian (bookworm or trixie) | Primary target; Ubuntu should also work |
| Hardware virtualisation | `vmx` or `svm` flag in `/proc/cpuinfo` (BIOS setting) |
| `sudo` / root access | Both scripts require elevated privileges |
| Internet access | k3s and Kata Containers are downloaded on first run |
| `kubectl` on `$PATH` | Installed automatically with k3s as `k3s kubectl`; symlink if needed |

Check VMX support:

```bash
grep -c vmx /proc/cpuinfo   # must be > 0
```

## 1. Setup: `setup-k3s-kata.sh`

Idempotent. Safe to re-run — only applies changes when something is missing or
out of date.

```bash
sudo bash scripts/setup-k3s-kata.sh
```

### What it does

| Step | Function | Notes |
|---|---|---|
| Preflight | Checks root + VMX | Exits immediately if either is missing |
| Dependencies | `apt-get install curl zstd` | Quiet install |
| k3s | Installs via `https://get.k3s.io` | Skipped if already installed |
| kubeconfig | Writes `/etc/rancher/k3s/config.yaml` | Sets `write-kubeconfig-mode: "0644"` so normal users can read it |
| Kata Containers 3.28.0 | Downloads tarball from GitHub, extracts to `/opt/kata` | Skipped if `/opt/kata/bin/kata-runtime` already exists |
| containerd shim | `ln -sf /opt/kata/bin/containerd-shim-kata-v2 /usr/local/bin/` | Always refreshed |
| Runtime check | `kata-runtime check` | Warnings are non-fatal |
| containerd template | Written to `/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl` | Written only when content differs |
| k3s restart | `systemctl restart k3s` then waits up to 90 s for `Ready` | Skipped when nothing changed |
| RuntimeClasses | Deletes stale entries, then applies all three | Handler field is immutable — delete-then-apply is required |
| Smoke test | Runs `busybox` pod with `runtimeClassName: kata-qemu` | Verifies end-to-end isolation |

### Runtime classes installed

| Name | Hypervisor | Config |
|---|---|---|
| `kata-qemu` | QEMU (KVM) | `configuration-qemu.toml` |
| `kata-clh` | Cloud Hypervisor | `configuration-clh.toml` |
| `kata-qemu-tdx` | QEMU + Intel TDX | `configuration-qemu-tdx.toml` |

### Verify

```bash
k3s kubectl get nodes
k3s kubectl get runtimeclass
```

Expected output:

```
NAME     STATUS   ROLES                  AGE
debian   Ready    control-plane,master   2m

NAME            HANDLER         AGE
kata-clh        kata-clh        60s
kata-qemu       kata-qemu       60s
kata-qemu-tdx   kata-qemu-tdx   60s
```

---

## 2. Agent wizard: `new-agent.sh`

Interactive generator and manager for agent deployments.

### Create a new agent

```bash
bash scripts/new-agent.sh
```

The wizard walks through **8 steps**:

#### [1/8] Project

- **Project name** — becomes the k8s namespace and deployment name (lowercase, hyphens, numbers only).
- **Host path** — directory on the Debian host to mount into the container. Created for you if it does not exist.
- **Container mount path** — where the host directory appears inside the VM (default `/home/agent/work`).

#### [2/8] Runtime

Choose the Kata hypervisor:

| Option | Use case |
|---|---|
| `kata-qemu` *(default)* | Best compatibility, full VMX isolation |
| `kata-clh` | Cloud Hypervisor — faster VM start |
| `kata-qemu-tdx` | Intel TDX confidential computing |

#### [3/8] Base image

| Option | Notes |
|---|---|
| `debian:trixie-slim` *(default)* | Smallest, matches host OS |
| `ubuntu:24.04` | Wider package availability |
| `python:3.12-slim` | Python pre-installed |
| `node:22-slim` | Node pre-installed |
| `custom` | Enter any registry image |

#### [4/8] Toolchain packages

Always installed (baseline):

```
sudo  ca-certificates  curl  wget  git  jq  tmux
python3  python3-pip  ripgrep  fd-find  bat
```

Optional additional toolchains (select by number, Enter keeps defaults):

| Option | Notes |
|---|---|
| `nodejs npm` | Required when using Claude Code or Codex (auto-added) |
| `golang` | Go toolchain via apt |
| `rustup` | Rust — installed via `curl \| sh`, not apt |
| `build-essential` | gcc, make, etc. |

You can also enter extra apt packages at the free-form prompt.
When `OpenAI Codex` is selected, `bubblewrap` is also auto-installed.
The container bootstrap also reuses this repo's `setup-zsh.sh`,
`setup-nvim.sh`, and `setup-tmux.sh` scripts from a read-only mount of the
host `geek-env` checkout. `setup-alacritty.sh` is not run in the container.

#### [5/8] Resource limits

Resource limits are enforced by the Kata VM kernel — a limit breach kills the
VM, not the host. Defaults: **2 CPU · 4 Gi RAM · 20 Gi storage**.

#### [6/8] AI Agent

Choose the coding agent to install:

| Option | Package | Auth |
|---|---|---|
| Claude Code | `@anthropic-ai/claude-code` | OAuth — browser flow |
| OpenAI Codex *(default)* | `@openai/codex` | ChatGPT OAuth or API key |
| None | — | — |

**Claude Code auth flow:**

1. The wizard calls `claude auth login` on the host.
2. A browser window opens for Anthropic OAuth.
3. After sign-in, credentials are saved to `~/.claude/.credentials.json`.
4. The wizard reads that file and stores it as a Kubernetes Secret
   (`<project>-claude-credentials`), mounted read-only at
   `/home/agent/.claude/.credentials.json` inside the VM.
5. The agent pod starts Claude with `--dangerously-skip-permissions` (if
   confirmed) so it can act without interactive prompts.

**OpenAI Codex auth flow:**

1. The wizard calls `codex auth login` on the host.
2. If Codex is using ChatGPT OAuth, the wizard reads `~/.codex/auth.json`.
3. That file is stored as a Kubernetes Secret and mounted at
   `/home/agent/.codex/auth.json` inside the VM.
4. If Codex is using an API key instead, the wizard reads `OPENAI_API_KEY` from
   the host auth file and injects it as a secret env var.
5. If neither can be read automatically you are prompted to paste
   `OPENAI_API_KEY` manually.
6. The generated tmux launch runs Codex with
   `--dangerously-bypass-approvals-and-sandbox`.

If the agent CLI is not installed on the host, the wizard warns you and lets
you add the key manually. Install it with:

```bash
npm install -g @anthropic-ai/claude-code   # Claude Code
npm install -g @openai/codex               # OpenAI Codex
```

#### [7/8] Environment variables

Add plain env vars (stored in the Deployment manifest) or secret env vars
(stored in a Kubernetes Secret and injected at runtime). Both are optional.

#### [8/8] Network

Optionally expose a container port via a `NodePort` service (ports 30000–32767).

### Deploy flow

After the wizard completes:

1. A summary is printed.
2. `Deploy now? [Y/n]` — default **yes**.
3. `kubectl apply -f agents/<project>.yaml`
4. The wizard waits for the pod to reach `Running`, then attaches immediately
   as the `agent` user in the configured work directory.
5. If `tmux` is ready, it opens the project tmux session and starts the chosen
   AI agent there. If provisioning is still in progress, it opens an `agent`
   shell instead of blocking on readiness.
6. If the pod stalls or crashes before it reaches `Running`, the wizard prints
   deployment status, pod details, and recent container logs before exiting.

### Generated files

```
agents/
  <project>.yaml    # Namespace + Secret(s) + Deployment + optional Service
  <project>.env     # Plain-text config summary (not applied to k8s)
```

---

## 3. Manage mode

Pass a project name to manage an existing agent:

```bash
bash scripts/new-agent.sh <project>
```

| Action | Effect |
|---|---|
| `exec` | `kubectl exec` into the running pod and attach the tmux session |
| `update` | Re-applies `agents/<project>.yaml`, waits for the new pod to start, then attaches |
| `restart` | Rolling restart, waits for the new pod to start, then attaches |
| `status` | Prints deployment state, pod list, `describe`, and recent logs |
| `delete` | Deletes the entire namespace (asks for confirmation) |

---

## Troubleshooting

### CrashLoopBackOff

The wizard prints diagnostics automatically on timeout or on common failure
states such as `CrashLoopBackOff`, `ImagePullBackOff`, or `ErrImagePull`.

You can still inspect the pod manually:

```bash
k3s kubectl -n <project> logs deployment/<project>
k3s kubectl -n <project> describe pod <pod-name>
```

Common causes:

| Symptom | Fix |
|---|---|
| `grep: /etc/sudoers: No such file or directory` | Old manifests used `/etc/sudoers`. New manifests use `/etc/sudoers.d/agent`. Re-generate with the wizard. |
| `chown: invalid user: 'agent:agent'` | The `useradd` line ran after `chown` in the wrong order. Re-generate with the wizard. |
| `apt-get: command not found` | Base image does not use apt. Pick a Debian/Ubuntu image. |
| Package not found | Some package names differ between Debian and Ubuntu. Check `EXTRA_PACKAGES`. |

### Readiness probe failing

The container is ready only after `/tmp/.ready` is created, which happens after
all packages are installed. Installation time depends on image and network
speed. The probe allows up to 5 min (60 × 5 s). If it times out:

```bash
k3s kubectl -n <project> describe pod
k3s kubectl -n <project> logs deployment/<project> --follow
```

### `kubectl wait` race condition

`kubectl wait --for=condition=Ready pod --selector=...` fails with
"no matching resources found" when the pod does not exist yet. The wizard uses
`kubectl rollout status` instead, which waits for the Deployment controller.

### RuntimeClass handler immutable

If you see:

```
The RuntimeClass 'kata-qemu' is invalid: handler: Invalid value: 'kata-qemu': field is immutable
```

`setup-k3s-kata.sh` handles this by deleting existing RuntimeClasses before
re-applying. If you hit this manually, run:

```bash
k3s kubectl delete runtimeclass kata-qemu kata-clh kata-qemu-tdx --ignore-not-found=true
k3s kubectl apply -f <your manifest>
```

### Node not Ready after install

```bash
journalctl -u k3s -n 100 --no-pager
k3s kubectl get nodes
k3s kubectl get events -A
```

### Claude auth not persisted after restart

The credentials secret is read once at wizard time and stored in k8s. If you
re-authenticate on the host after deploying, re-run the wizard (or delete and
recreate the secret manually):

```bash
kubectl -n <project> delete secret <project>-claude-credentials
kubectl -n <project> create secret generic <project>-claude-credentials \
  --from-file=credentials.json="$HOME/.claude/.credentials.json"
kubectl -n <project> rollout restart deployment/<project>
```

---

## Quick reference

```bash
# Initial setup (once)
sudo bash scripts/setup-k3s-kata.sh

# Create a new agent
bash scripts/new-agent.sh

# Attach to a running agent
bash scripts/new-agent.sh <project>   # choose exec

# Restart an agent
bash scripts/new-agent.sh <project>   # choose restart

# Delete an agent
bash scripts/new-agent.sh <project>   # choose delete

# Check cluster state
k3s kubectl get nodes
k3s kubectl get runtimeclass
k3s kubectl get pods -A
```
