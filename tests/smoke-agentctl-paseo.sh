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

if [[ ! -f "$HOME/.codex/auth.json" && -z "${OPENAI_API_KEY:-}" ]]; then
  log "Skipping: neither ~/.codex/auth.json nor OPENAI_API_KEY is available for Codex"
  exit 0
fi

log "Generating canonical config and rendered manifest for $PROJECT"
python3 - <<PY
import json
import os
from pathlib import Path

from scripts.agentctl import AgentConfig, SecretEnvVar, agent_label_for_cmd, resolve_agent_args, write_project_files

project = "${PROJECT}"
work_dir = Path("${WORK_DIR}")
auth_path = Path.home() / ".codex" / "auth.json"
auth_name = ""
auth_key = ""
auth_mount_path = ""
auth_content = ""
secret_env_vars = []

if auth_path.exists():
    data = json.loads(auth_path.read_text())
    if data.get("auth_mode") == "chatgpt":
        auth_name = f"{project}-codex-auth"
        auth_key = "auth.json"
        auth_mount_path = "/home/agent/.codex/auth.json"
        auth_content = auth_path.read_text()

api_key = os.environ.get("OPENAI_API_KEY", "")
if api_key:
    secret_env_vars.append(SecretEnvVar("OPENAI_API_KEY", api_key))

cfg = AgentConfig(
    project_name=project,
    host_path=str(work_dir),
    mount_path="/workspace",
    runtime_class="kata-qemu",
    base_image="debian:trixie-slim",
    cpu="1",
    memory="2Gi",
    storage="10Gi",
    agent=agent_label_for_cmd("codex"),
    agent_cmd="codex",
    permissive_mode="true",
    agent_args=resolve_agent_args("codex", "true"),
    persist_state=False,
    all_packages="sudo ca-certificates curl wget git jq python3 python3-pip ripgrep fd-find bat nodejs npm bubblewrap",
    bootstrap_profile="full",
    secret_env_vars=secret_env_vars,
    agent_secret_name=auth_name,
    agent_secret_key=auth_key,
    agent_secret_mount_path=auth_mount_path,
    agent_secret_content=auth_content,
)
work_dir.mkdir(parents=True, exist_ok=True)
write_project_files(cfg)
PY

test -f "$REPO_ROOT/agents/$PROJECT.agent.yaml"
test -f "$REPO_ROOT/agents/$PROJECT.yaml"

log "Applying rendered manifest"
kubectl apply -f "$REPO_ROOT/agents/$PROJECT.yaml"

log "Waiting for deployment readiness"
kubectl -n "$PROJECT" rollout status "deployment/$PROJECT" --timeout=900s

POD="$(kubectl -n "$PROJECT" get pod -l "app=$PROJECT" -o jsonpath='{.items[0].metadata.name}')"
test -n "$POD"

log "Checking agent tooling"
kubectl -n "$PROJECT" exec "$POD" -- sh -lc 'command -v paseo >/dev/null && command -v codex >/dev/null'

log "Checking Paseo daemon status"
kubectl -n "$PROJECT" exec "$POD" -- su - agent -c 'cd /workspace && PASEO_HOME=/home/agent/.paseo paseo daemon status'

log "Launching a detached Codex task through Paseo"
AGENT_ID="$(
  kubectl -n "$PROJECT" exec "$POD" -- su - agent -c \
    "cd /workspace && PASEO_HOME=/home/agent/.paseo paseo run --provider codex --detach -q 'Reply with exactly SMOKE_OK and then stop.'" \
    | tr -d '\r' | tail -n1
)"
test -n "$AGENT_ID"

log "Waiting for Paseo-managed agent $AGENT_ID"
kubectl -n "$PROJECT" exec "$POD" -- su - agent -c \
  "cd /workspace && PASEO_HOME=/home/agent/.paseo paseo wait '$AGENT_ID' --timeout 300"

log "Checking Paseo agent listing"
kubectl -n "$PROJECT" exec "$POD" -- su - agent -c \
  "cd /workspace && PASEO_HOME=/home/agent/.paseo paseo ls -a -q | grep -Fx '$AGENT_ID'"

log "Checking Paseo agent logs"
kubectl -n "$PROJECT" exec "$POD" -- su - agent -c \
  "cd /workspace && PASEO_HOME=/home/agent/.paseo paseo logs '$AGENT_ID' --tail 200" \
  | tee "$WORK_DIR/paseo-agent.log"

grep -q "SMOKE_OK" "$WORK_DIR/paseo-agent.log"

log "Deleting namespace"
kubectl delete namespace "$PROJECT" --wait=false

log "agentctl Paseo smoke test passed"
