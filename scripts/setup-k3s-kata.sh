#!/usr/bin/env bash
# setup-k3s-kata.sh
# Idempotent setup of k3s + Kata Containers on Debian (VMX required)

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
KATA_VERSION="3.28.0"
KATA_TARBALL="kata-static-${KATA_VERSION}-amd64.tar.zst"
KATA_URL="https://github.com/kata-containers/kata-containers/releases/download/${KATA_VERSION}/${KATA_TARBALL}"
KATA_RUNTIME="/opt/kata/bin/kata-runtime"
KATA_SHIM="/opt/kata/bin/containerd-shim-kata-v2"
KATA_SHIM_LINK="/usr/local/bin/containerd-shim-kata-v2"
K3S_CONFIG="/etc/rancher/k3s/config.yaml"
CONTAINERD_TMPL="/var/lib/rancher/k3s/agent/etc/containerd/config.toml.tmpl"
RESTART_NEEDED=false

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$SCRIPT_NAME" "$*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

preflight() {
  [[ $EUID -eq 0 ]] || fail "Run this script with sudo or as root"
  grep -qE "vmx|svm" /proc/cpuinfo \
    || fail "VMX/SVM not found in /proc/cpuinfo. Enable hardware virtualisation in BIOS."
  log "Preflight passed (root, VMX available)"
}

install_dependencies() {
  log "Installing dependencies..."
  apt-get update -qq
  apt-get install -y -qq curl zstd
}

install_k3s() {
  if command_exists k3s; then
    log "k3s already installed ($(k3s --version | head -1))"
  else
    log "Installing k3s..."
    curl -sfL https://get.k3s.io | sh -
  fi

  log "Configuring k3s kubeconfig permissions..."
  mkdir -p /etc/rancher/k3s
  cat >"$K3S_CONFIG" <<'EOF'
write-kubeconfig-mode: "0644"
EOF
}

install_kata() {
  if [[ -x "$KATA_RUNTIME" ]]; then
    log "Kata Containers already installed ($($KATA_RUNTIME --version 2>&1 | head -1))"
  else
    log "Downloading Kata Containers ${KATA_VERSION}..."
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL "$KATA_URL" -o "$tmp/$KATA_TARBALL"
    log "Extracting Kata Containers..."
    tar --use-compress-program=unzstd -xf "$tmp/$KATA_TARBALL" -C /
    rm -rf "$tmp"
    log "Kata Containers extracted to /opt/kata"
    RESTART_NEEDED=true
  fi

  log "Symlinking containerd shim..."
  ln -sf "$KATA_SHIM" "$KATA_SHIM_LINK"

  log "Verifying Kata runtime..."
  "$KATA_RUNTIME" check \
    && log "Kata runtime check passed" \
    || log "WARN: kata-runtime check had warnings (see above)"
}

configure_containerd() {
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<'EOF'
version = 2

[plugins."io.containerd.grpc.v1.cri".cni]
  bin_dir = "/var/lib/rancher/k3s/data/current/bin"
  conf_dir = "/var/lib/rancher/k3s/agent/etc/cni/net.d"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.runc]
  runtime_type = "io.containerd.runc.v2"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-qemu]
  runtime_type = "io.containerd.kata.v2"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-qemu.options]
    ConfigPath = "/opt/kata/share/defaults/kata-containers/configuration-qemu.toml"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-clh]
  runtime_type = "io.containerd.kata.v2"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-clh.options]
    ConfigPath = "/opt/kata/share/defaults/kata-containers/configuration-clh.toml"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-qemu-tdx]
  runtime_type = "io.containerd.kata.v2"
  [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-qemu-tdx.options]
    ConfigPath = "/opt/kata/share/defaults/kata-containers/configuration-qemu-tdx.toml"
EOF

  if cmp -s "$tmp" "$CONTAINERD_TMPL" 2>/dev/null; then
    log "containerd template already up to date"
    rm -f "$tmp"
  else
    mkdir -p "$(dirname "$CONTAINERD_TMPL")"
    mv "$tmp" "$CONTAINERD_TMPL"
    log "containerd template written"
    RESTART_NEEDED=true
  fi
}

restart_and_wait() {
  if [[ "$RESTART_NEEDED" != true ]]; then
    log "No changes detected; skipping k3s restart"
    return
  fi

  log "Restarting k3s..."
  systemctl restart k3s

  log "Waiting for node to be Ready..."
  local i status
  for i in $(seq 1 30); do
    status="$(k3s kubectl get nodes --no-headers 2>/dev/null | awk '{print $2}' || true)"
    if [[ "$status" == "Ready" ]]; then
      log "Node is Ready"
      return
    fi
    sleep 3
    [[ $i -lt 30 ]] || fail "Node did not become Ready after 90s. Check: journalctl -u k3s -n 50"
  done
}

apply_runtimeclass() {
  log "Applying Kata RuntimeClasses..."
  # handler is immutable; delete stale entries before applying
  k3s kubectl delete runtimeclass kata-qemu kata-clh kata-qemu-tdx --ignore-not-found=true
  k3s kubectl apply -f - <<'EOF'
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-qemu
handler: kata-qemu
---
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-clh
handler: kata-clh
---
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata-qemu-tdx
handler: kata-qemu-tdx
EOF
  log "RuntimeClasses applied (kata-qemu, kata-clh, kata-qemu-tdx)"
}

smoke_test() {
  log "Running smoke test..."
  k3s kubectl delete pod kata-smoke-test --ignore-not-found=true

  k3s kubectl run kata-smoke-test \
    --image=busybox \
    --restart=Never \
    --overrides='{"spec":{"runtimeClassName":"kata-qemu"}}' \
    -- echo "kata works"

  log "Waiting for smoke test pod..."
  k3s kubectl wait --for=condition=Ready pod/kata-smoke-test --timeout=60s 2>/dev/null || true
  k3s kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/kata-smoke-test --timeout=60s

  local result
  result="$(k3s kubectl logs kata-smoke-test)"
  k3s kubectl delete pod kata-smoke-test --ignore-not-found=true

  [[ "$result" == "kata works" ]] \
    || fail "Smoke test failed. Got: \"$result\""
  log "Smoke test passed: \"$result\""
}

main() {
  preflight
  install_dependencies
  install_k3s
  install_kata
  configure_containerd
  restart_and_wait
  apply_runtimeclass
  smoke_test
  log "Setup complete. Run: kubectl get nodes && kubectl get runtimeclass"
}

main "$@"
