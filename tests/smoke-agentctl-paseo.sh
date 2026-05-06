#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="smoke-agentctl-paseo-$(date +%s)"
WORK_DIR="$(mktemp -d)"

log() {
  printf '[%s] %s\n' "$SCRIPT_NAME" "$*"
}

cleanup() {
  kubectl delete namespace "$PROJECT" --ignore-not-found=true --wait=false >/dev/null 2>&1 || true
  rm -f "$REPO_ROOT/agents/$PROJECT.agent.yaml" "$REPO_ROOT/agents/$PROJECT.yaml"
  rm -rf "$WORK_DIR"
}

trap cleanup EXIT

if ! command -v kubectl >/dev/null 2>&1; then
  log "Skipping: kubectl is not available"
  exit 0
fi

if ! kubectl get runtimeclass kata-qemu >/dev/null 2>&1; then
  log "Skipping: kata-qemu runtimeclass is not available"
  exit 0
fi

if [[ ! -f "$HOME/.codex/auth.json" ]]; then
  log "Skipping: ~/.codex/auth.json is not available for Codex"
  exit 0
fi

log "Generating install-isolation config and rendered manifest for $PROJECT"
python3 - <<PY
import json
from pathlib import Path

from scripts.agentctl import AgentAuthFile, AgentConfig, agent_label_for_cmd, write_project_files

project = "${PROJECT}"
work_dir = Path("${WORK_DIR}")
container_home = f"/home/{project}"
auth_path = Path.home() / ".codex" / "auth.json"
auth_files = []

if auth_path.exists():
    data = json.loads(auth_path.read_text())
    if data.get("auth_mode") == "chatgpt":
        auth_files.append(
            AgentAuthFile(
                key="codex-auth.json",
                mount_path=f"{container_home}/.codex/auth.json",
                content=auth_path.read_text(),
            )
        )

cfg = AgentConfig(
    project_name=project,
    runtime_class="kata-qemu",
    base_image="debian:trixie-slim",
    cpu="2",
    memory="4Gi",
    storage="10Gi",
    agent=agent_label_for_cmd("multi"),
    agent_cmd="multi",
    agent_args="",
    persist_state=False,
    all_packages="sudo ca-certificates curl wget git jq python3 python3-pip ripgrep fd-find bat nodejs npm bubblewrap",
    bootstrap_profile="full",
    auth_files=auth_files,
)
work_dir.mkdir(parents=True, exist_ok=True)
write_project_files(cfg)

custom_bootstrap = """          set -eux && \\
          if ! id {project} >/dev/null 2>&1; then useradd -m -s /bin/bash {project}; fi && \\
          mkdir -p /home/{project} /home/{project}/.codex /home/{project}/.claude /home/{project}/.paseo && \\
          chown -R {project}:{project} /home/{project} && \\
          apt-get update && apt-get install -y ca-certificates curl nodejs npm && \\
          echo 'installing @getpaseo/cli with verbose npm output' && \\
          mkdir -p /opt/agent-cli && npm install -ddd -g --prefix /opt/agent-cli @getpaseo/cli && \\
          ls -la /opt/agent-cli/bin && \\
          /opt/agent-cli/bin/paseo --version && \\
          touch /tmp/.ready && sleep infinity""".format(project=project)

manifest = cfg.yaml_path.read_text()
prefix, rest = manifest.split("        - |\\n", 1)
_, suffix = rest.split("\\n        readinessProbe:", 1)
cfg.yaml_path.write_text(prefix + "        - |\\n" + custom_bootstrap + "\\n        readinessProbe:" + suffix)
PY

test -f "$REPO_ROOT/agents/$PROJECT.agent.yaml"
test -f "$REPO_ROOT/agents/$PROJECT.yaml"

log "Applying rendered manifest"
kubectl apply -f "$REPO_ROOT/agents/$PROJECT.yaml"

log "Waiting for deployment readiness"
kubectl -n "$PROJECT" rollout status "deployment/$PROJECT" --timeout=900s

POD="$(kubectl -n "$PROJECT" get pod -l "app=$PROJECT" -o jsonpath='{.items[0].metadata.name}')"
test -n "$POD"

log "Checking isolated Paseo install"
kubectl -n "$PROJECT" exec "$POD" -- sh -lc 'test -x /opt/agent-cli/bin/paseo && /opt/agent-cli/bin/paseo --version'

log "Deleting namespace"
kubectl delete namespace "$PROJECT" --wait=false

log "agentctl Paseo install-isolation smoke test passed"
