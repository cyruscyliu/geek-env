#!/usr/bin/env bash
# new-agent.sh
# Interactive generator and manager for k3s + Kata Containers agent deployments
# Usage:
#   bash new-agent.sh                  # create a new agent
#   bash new-agent.sh <project>        # manage an existing agent

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/../agents"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BOLD="\e[1m"
CYAN="\e[36m"
GREEN="\e[32m"
YELLOW="\e[33m"
DIM="\e[2m"
RESET="\e[0m"

header() { echo -e "\n${BOLD}${CYAN}▸ $*${RESET}"; }
hint()   { echo -e "${DIM}  $*${RESET}"; }
ok()     { echo -e "${GREEN}✔${RESET} $*"; }
warn()   { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail()   { stop_log_stream; echo -e "${YELLOW}✖${RESET}  $*" >&2; exit 1; }

prompt() {
    # prompt <var> <question> <default>
    local var="$1" question="$2" default="${3:-}" input
    if [[ -n "$default" ]]; then
        echo -ne "${BOLD}${question}${RESET} ${DIM}[${default}]${RESET}: "
    else
        echo -ne "${BOLD}${question}${RESET}: "
    fi
    read -r input
    input="${input:-$default}"
    printf -v "$var" '%s' "$input"
}

prompt_path() {
    # prompt_path <var> <question> <default>
    # Uses Readline so interactive users get tab completion for filesystem paths.
    local var="$1" question="$2" default="${3:-}" input
    if [[ -n "$default" ]]; then
        echo -ne "${BOLD}${question}${RESET} ${DIM}[${default}]${RESET}: "
        read -e -i "$default" -r input
    else
        echo -ne "${BOLD}${question}${RESET}: "
        read -e -r input
    fi
    input="${input:-$default}"
    printf -v "$var" '%s' "$input"
}

choose() {
    # choose <var> <question> [--default N] <option1> <option2> ...
    local var="$1" question="$2"
    shift 2
    local default_idx=0
    if [[ "${1:-}" == "--default" ]]; then
        default_idx="$2"
        shift 2
    fi
    local options=("$@")
    echo -e "${BOLD}${question}${RESET}"
    for i in "${!options[@]}"; do
        if [[ "$default_idx" -gt 0 && "$((i+1))" == "$default_idx" ]]; then
            echo -e "  ${GREEN}*${RESET} ${DIM}$((i+1))${RESET}) ${options[$i]}"
        else
            echo -e "    ${DIM}$((i+1))${RESET}) ${options[$i]}"
        fi
    done
    while true; do
        if [[ "$default_idx" -gt 0 ]]; then
            echo -ne "Choice [1-${#options[@]}] ${DIM}[${default_idx}]${RESET}: "
        else
            echo -ne "Choice [1-${#options[@]}]: "
        fi
        read -r pick
        if [[ -z "$pick" && "$default_idx" -gt 0 ]]; then
            printf -v "$var" '%s' "${options[$((default_idx-1))]}"
            break
        fi
        if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#options[@]} )); then
            printf -v "$var" '%s' "${options[$((pick-1))]}"
            break
        fi
        warn "Enter a number between 1 and ${#options[@]}"
    done
}

multichoose() {
    # multichoose <var> <question> [--defaults "1 2 3"] <option1> <option2> ...
    # Sets var to a space-separated list of selected items.
    # Pre-selected items are marked with * and used if user presses Enter.
    local var="$1" question="$2"
    shift 2
    local default_indices=()
    if [[ "${1:-}" == "--defaults" ]]; then
        read -ra default_indices <<< "$2"
        shift 2
    fi
    local options=("$@") selected=() defaults_selected=() picks pick i d marker
    for d in "${default_indices[@]:-}"; do
        (( d >= 1 && d <= ${#options[@]} )) && defaults_selected+=("${options[$((d-1))]}")
    done
    echo -e "${BOLD}${question}${RESET}"
    hint "Enter numbers to select (e.g: 1 3 4), 0 for none. Press Enter to keep defaults (*)."
    for i in "${!options[@]}"; do
        marker="  "
        for d in "${default_indices[@]:-}"; do
            [[ "$((i+1))" == "$d" ]] && marker="${GREEN}*${RESET} " && break
        done
        echo -e "  ${marker}${DIM}$((i+1))${RESET}) ${options[$i]}"
    done
    echo -ne "Choices: "
    read -r picks
    if [[ -z "$picks" ]]; then
        selected=("${defaults_selected[@]:-}")
    else
        for pick in $picks; do
            [[ "$pick" == "0" ]] && break
            if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#options[@]} )); then
                selected+=("${options[$((pick-1))]}")
            fi
        done
    fi
    printf -v "$var" '%s' "${selected[*]:-}"
}

confirm() {
    # confirm <question> → returns 0 (yes) or 1 (no), default no
    echo -ne "${BOLD}$1${RESET} ${DIM}[y/N]${RESET}: "
    read -r ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

confirm_yes() {
    # confirm_yes <question> → returns 0 (yes) or 1 (no), default yes
    echo -ne "${BOLD}$1${RESET} ${DIM}[Y/n]${RESET}: "
    read -r ans
    [[ ! "$ans" =~ ^[Nn]$ ]]
}

add_secret() {
    # add_secret <KEY_NAME> <value>
    local name="$1" value="$2"
    SECRETS+=("${name}=${value}")
    SECRET_ENV_BLOCKS+="
        - name: ${name}
          valueFrom:
            secretKeyRef:
              name: ${PROJECT_NAME}-secrets
              key: ${name}"
}

agent_package_for_cmd() {
    case "$1" in
        claude) printf '%s\n' "@anthropic-ai/claude-code" ;;
        codex)  printf '%s\n' "@openai/codex" ;;
        *)      printf '%s\n' "" ;;
    esac
}

resolve_agent_args() {
    local agent_cmd="$1"
    local permissive_mode="$2"

    case "$agent_cmd:$permissive_mode" in
        "claude:true")
            printf '%s\n' "--dangerously-skip-permissions"
            ;;
        "codex:true")
            printf '%s\n' "--dangerously-bypass-approvals-and-sandbox"
            ;;
        *)
            printf '%s\n' ""
            ;;
    esac
}

baseline_packages() {
    printf '%s\n' "sudo ca-certificates curl wget git jq tmux python3 python3-pip ripgrep fd-find bat"
}

agent_bin_dir() {
    printf '%s\n' "/opt/agent-cli/bin"
}

build_agent_wrapper_line() {
    local agent_cmd="$1"
    local agent_args="$2"
    local agent_bin

    if [[ -z "$agent_cmd" ]]; then
        printf '%s' ""
        return
    fi

    agent_bin="$(agent_bin_dir)/${agent_cmd}"

    printf "printf '%%s\\\\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'exec %s%s \"\$@\"' > /usr/local/bin/%s && chmod 755 /usr/local/bin/%s && \\\\\n          " \
        "$agent_bin" \
        "${agent_args:+ ${agent_args}}" \
        "$agent_cmd" \
        "$agent_cmd"
}

build_agent_install_line() {
    local agent_pkg="$1"

    if [[ -z "$agent_pkg" ]]; then
        printf '%s' ""
        return
    fi

    printf "mkdir -p /opt/agent-cli && npm install -g --prefix /opt/agent-cli %s && \\\\\n          " "$agent_pkg"
}

build_user_setup_line() {
cat <<'EOF'
su - agent -c "REPO_ROOT=/opt/geek-env SKIP_DEFAULT_SHELL_CHANGE=1 /opt/geek-env/scripts/setup-zsh.sh" && \
          usermod -s "$(command -v zsh)" agent && \
          su - agent -c "REPO_ROOT=/opt/geek-env /opt/geek-env/scripts/setup-nvim.sh" && \
          su - agent -c "REPO_ROOT=/opt/geek-env SKIP_PACKAGE_INSTALL=1 /opt/geek-env/scripts/setup-tmux.sh" && \
EOF
}

build_container_bootstrap_lines() {
cat <<EOF
          if ! id agent >/dev/null 2>&1; then useradd -m -s /bin/bash agent; fi && \\
          mkdir -p /home/agent /home/agent/.claude /home/agent/.codex && \\
          chown agent:agent /home/agent /home/agent/.claude /home/agent/.codex && \\
          apt-get update && apt-get install -y \\
            ${ALL_PACKAGES} && \\
          mkdir -p /etc/sudoers.d && \\
          echo "agent ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/agent && \\
          chmod 440 /etc/sudoers.d/agent && \\
          ${USER_SETUP_LINE}${RUSTUP_INSTALL_LINE}${AGENT_INSTALL_LINE}${AGENT_WRAPPER_LINE}touch /tmp/.ready && sleep infinity
EOF
}

extract_manifest_packages() {
    local manifest="$1"
    awk '
        index($0, "apt-get update && apt-get install -y") {
            getline
            line=$0
            sub(/^[[:space:]]+/, "", line)
            sub(/[[:space:]]+&&[[:space:]]+\\$/, "", line)
            print line
            exit
        }
    ' "$manifest"
}

refresh_project_manifest() {
    local manifest="${OUTPUT_DIR}/${PROJECT_NAME}.yaml"
    local tmp
    local block_file

    [[ -f "$manifest" ]] || fail "Manifest not found: ${manifest}"

    ALL_PACKAGES="${PROJECT_ALL_PACKAGES:-}"
    if [[ -z "$ALL_PACKAGES" ]]; then
        ALL_PACKAGES="$(extract_manifest_packages "$manifest")"
    fi
    if [[ -z "$ALL_PACKAGES" || "$ALL_PACKAGES" != *"sudo"* ]]; then
        warn "Falling back to derived package set for ${PROJECT_NAME}"
        ALL_PACKAGES="$(baseline_packages)"
        if [[ -n "${PROJECT_AGENT_CMD:-}" ]]; then
            ALL_PACKAGES="${ALL_PACKAGES} nodejs npm"
        fi
        if [[ "${PROJECT_AGENT_CMD:-}" == "codex" ]]; then
            ALL_PACKAGES="${ALL_PACKAGES} bubblewrap"
        fi
        ALL_PACKAGES="$(echo "$ALL_PACKAGES" | tr ' ' '\n' | sort -u | tr '\n' ' ' | xargs)"
    fi

    AGENT_PKG="$(agent_package_for_cmd "${PROJECT_AGENT_CMD:-}")"
    USER_SETUP_LINE="$(build_user_setup_line)"
    RUSTUP_INSTALL_LINE=""
    AGENT_INSTALL_LINE=""
    AGENT_WRAPPER_LINE=""

    if grep -q "sh.rustup.rs" "$manifest"; then
        RUSTUP_INSTALL_LINE="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | su agent -c 'sh -s -- -y' && \\"$'\n'"          "
    fi

    if [[ -n "$AGENT_PKG" ]]; then
        AGENT_INSTALL_LINE="$(build_agent_install_line "${AGENT_PKG}")"
    fi

    if [[ -n "${PROJECT_AGENT_CMD:-}" ]]; then
        AGENT_WRAPPER_LINE="$(build_agent_wrapper_line "${PROJECT_AGENT_CMD}" "${PROJECT_AGENT_ARGS}")"
    fi

    tmp="$(mktemp)"
    block_file="$(mktemp)"
    build_container_bootstrap_lines > "$block_file"
    awk -v block_file="$block_file" '
        BEGIN { in_args = 0 }
        {
            if (!in_args && $0 == "        - |") {
                print $0
                while ((getline line < block_file) > 0) {
                    print line
                }
                close(block_file)
                in_args = 1
                next
            }
            if (in_args) {
                if ($0 == "        readinessProbe:") {
                    print $0
                    in_args = 0
                }
                next
            }
            print $0
        }
    ' "$manifest" > "$tmp"
    rm -f "$block_file"
    mv "$tmp" "$manifest"
    ok "Refreshed ${manifest} with current generator bootstrap"
}

get_project_pod() {
    kubectl -n "$PROJECT_NAME" get pods \
        --selector="app=${PROJECT_NAME}" \
        --sort-by=.metadata.creationTimestamp \
        -o custom-columns=NAME:.metadata.name,DELETING:.metadata.deletionTimestamp \
        --no-headers 2>/dev/null | awk '$2 == "<none>" || $2 == "" { print "pod/" $1 }' | tail -1
}

print_deploy_diagnostics() {
    local pod="$1"

    echo ""
    warn "Deployment diagnostics for ${PROJECT_NAME}:"
    kubectl -n "$PROJECT_NAME" get deployment "$PROJECT_NAME" -o wide || true
    kubectl -n "$PROJECT_NAME" get pods -o wide || true

    if [[ -n "$pod" ]]; then
        echo ""
        warn "Describing ${pod}:"
        kubectl -n "$PROJECT_NAME" describe "$pod" || true

        echo ""
        warn "Recent logs from ${pod}:"
        kubectl -n "$PROJECT_NAME" logs "$pod" --tail=100 || true
    fi
}

LOG_STREAM_PID=""

start_log_stream() {
    local pod="$1"
    local interval_seconds=2
    local timeout_seconds="${LOG_STREAM_START_TIMEOUT_SECONDS:-120}"
    local elapsed=0
    local running_started="" waiting_reason=""

    stop_log_stream

    while (( elapsed < timeout_seconds )); do
        running_started="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.running.startedAt}' 2>/dev/null || true)"
        if [[ -n "$running_started" ]]; then
            echo ""
            hint "Streaming logs from ${pod} while waiting..."
            kubectl -n "$PROJECT_NAME" logs -f "$pod" --tail=20 --ignore-errors=true >/dev/null 2>&1 &
            LOG_STREAM_PID=$!
            return 0
        fi

        waiting_reason="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)"
        if [[ -n "$waiting_reason" && "$waiting_reason" != "ContainerCreating" ]]; then
            break
        fi

        sleep "$interval_seconds"
        elapsed=$(( elapsed + interval_seconds ))
    done
}

stop_log_stream() {
    if [[ -n "${LOG_STREAM_PID:-}" ]]; then
        kill "$LOG_STREAM_PID" >/dev/null 2>&1 || true
        wait "$LOG_STREAM_PID" 2>/dev/null || true
        LOG_STREAM_PID=""
    fi
}

wait_for_pod_running() {
    local timeout_seconds="${1:-300}"
    local interval_seconds=2
    local elapsed=0
    local pod="" phase="" running_started="" waiting_reason="" terminated_reason="" last_status=""

    while (( elapsed < timeout_seconds )); do
        pod="$(get_project_pod)"
        if [[ -n "$pod" ]]; then
            phase="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
            running_started="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.running.startedAt}' 2>/dev/null || true)"
            waiting_reason="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)"
            terminated_reason="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || true)"

            if [[ -n "$running_started" ]]; then
                ok "Container is running."
                return 0
            fi

            if [[ -n "$terminated_reason" ]] && [[ "$terminated_reason" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown} (${terminated_reason})"
                last_status="$terminated_reason"
            elif [[ -n "$waiting_reason" ]] && [[ "$waiting_reason" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown} (${waiting_reason})"
                last_status="$waiting_reason"
            elif [[ -z "$last_status" || "$phase" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown}"
                last_status="$phase"
            fi
        fi

        sleep "$interval_seconds"
        elapsed=$(( elapsed + interval_seconds ))
    done

    print_deploy_diagnostics "${pod:-}"
    fail "Timed out after ${timeout_seconds}s waiting for ${PROJECT_NAME} to start running"
}

wait_for_deployment_ready() {
    local timeout_seconds="${1:-900}"
    local interval_seconds=5
    local elapsed=0
    local pod="" phase="" ready="" waiting_reason="" terminated_reason="" last_status=""

    while (( elapsed < timeout_seconds )); do
        pod="$(get_project_pod)"
        if [[ -n "$pod" ]]; then
            phase="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
            ready="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || true)"
            waiting_reason="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.waiting.reason}' 2>/dev/null || true)"
            terminated_reason="$(kubectl -n "$PROJECT_NAME" get "$pod" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || true)"

            if [[ "$ready" == "true" ]]; then
                ok "Pod is ready."
                return 0
            fi

            if [[ -n "$terminated_reason" ]] && [[ "$terminated_reason" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown} (${terminated_reason})"
                last_status="$terminated_reason"
            elif [[ -n "$waiting_reason" ]] && [[ "$waiting_reason" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown} (${waiting_reason})"
                last_status="$waiting_reason"
            elif [[ -z "$last_status" || "$phase" != "$last_status" ]]; then
                hint "Status: ${phase:-Unknown}"
                last_status="$phase"
            fi

            if [[ "$waiting_reason" == "CrashLoopBackOff" || "$waiting_reason" == "ImagePullBackOff" || "$waiting_reason" == "ErrImagePull" ]]; then
                print_deploy_diagnostics "$pod"
                fail "Deployment failed while waiting for ${PROJECT_NAME} to become ready"
            fi
        fi

        sleep "$interval_seconds"
        elapsed=$(( elapsed + interval_seconds ))
    done

    print_deploy_diagnostics "${pod:-}"
    fail "Timed out after ${timeout_seconds}s waiting for ${PROJECT_NAME} to become ready"
}

wait_for_agent_user() {
    local pod="$1"
    local timeout_seconds="${2:-180}"
    local interval_seconds=2
    local elapsed=0

    while (( elapsed < timeout_seconds )); do
        if kubectl -n "$PROJECT_NAME" exec "$pod" -- sh -lc 'id agent >/dev/null 2>&1' >/dev/null 2>&1; then
            return 0
        fi

        sleep "$interval_seconds"
        elapsed=$(( elapsed + interval_seconds ))
    done

    print_deploy_diagnostics "$pod"
    fail "The agent user did not become available in ${pod} after ${timeout_seconds}s"
}

wait_for_project_tools() {
    local pod="$1"
    local timeout_seconds="${2:-600}"
    local interval_seconds=2
    local elapsed=0
    local checks='command -v tmux >/dev/null 2>&1'

    if [[ -n "${PROJECT_AGENT_CMD:-}" ]]; then
        checks="${checks} && command -v ${PROJECT_AGENT_CMD} >/dev/null 2>&1"
    fi

    while (( elapsed < timeout_seconds )); do
        if kubectl -n "$PROJECT_NAME" exec "$pod" -- sh -lc "$checks" >/dev/null 2>&1; then
            return 0
        fi

        sleep "$interval_seconds"
        elapsed=$(( elapsed + interval_seconds ))
    done

    print_deploy_diagnostics "$pod"
    if [[ -n "${PROJECT_AGENT_CMD:-}" ]]; then
        fail "tmux and ${PROJECT_AGENT_CMD} did not become available in ${pod} after ${timeout_seconds}s"
    fi
    fail "tmux did not become available in ${pod} after ${timeout_seconds}s"
}

attach_to_project_pod() {
    local pod="$1"
    local work_dir="${PROJECT_MOUNT_PATH:-${MOUNT_PATH:-/home/agent/work}}"
    local tmux_cmd="${PROJECT_TMUX_CMD:-tmux new-session -A -s main}"

    ok "Attaching to ${pod}..."
    start_log_stream "$pod"
    wait_for_agent_user "$pod" "${AGENT_USER_TIMEOUT_SECONDS:-180}"
    if [[ -n "${PROJECT_AGENT_CMD:-}" ]]; then
        wait_for_project_tools "$pod" "${AGENT_TOOL_TIMEOUT_SECONDS:-600}"
    fi
    stop_log_stream

    if kubectl -n "$PROJECT_NAME" exec "$pod" -- sh -lc 'command -v tmux >/dev/null 2>&1' >/dev/null 2>&1; then
        kubectl -n "$PROJECT_NAME" exec -it "$pod" -- su - agent -c "cd '$work_dir' 2>/dev/null || cd ~; ${tmux_cmd}"
        return
    fi

    warn "tmux is not ready yet. Opening an agent shell in ${work_dir}."
    kubectl -n "$PROJECT_NAME" exec -it "$pod" -- su - agent -c "cd '$work_dir' 2>/dev/null || cd ~; exec \"\${SHELL:-/bin/sh}\""
}

apply_project_manifest() {
    local manifest="${OUTPUT_DIR}/${PROJECT_NAME}.yaml"

    [[ -f "$manifest" ]] || fail "Manifest not found: ${manifest}"

    ok "Applying ${manifest}..."
    kubectl apply -f "$manifest"
}

# ────────────────────────────────────────────────
# Manage mode  (bash new-agent.sh <project>)
# ────────────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
    PROJECT_NAME="$1"
    PROJECT_ENV_FILE="${OUTPUT_DIR}/${PROJECT_NAME}.env"
    PROJECT_MOUNT_PATH="/home/agent/work"
    PROJECT_AGENT_CMD=""
    PROJECT_AGENT_ARGS=""
    PROJECT_PERMISSIVE_MODE=""
    PROJECT_ALL_PACKAGES=""

    if [[ -f "$PROJECT_ENV_FILE" ]]; then
        PROJECT_MOUNT_PATH="$(awk -F= '/^MOUNT_PATH=/{print substr($0, index($0, "=") + 1)}' "$PROJECT_ENV_FILE" | tail -1)"
        PROJECT_MOUNT_PATH="${PROJECT_MOUNT_PATH:-/home/agent/work}"
        PROJECT_AGENT_CMD="$(awk -F= '/^AGENT_CMD=/{print substr($0, index($0, "=") + 1)}' "$PROJECT_ENV_FILE" | tail -1)"
        PROJECT_PERMISSIVE_MODE="$(awk -F= '/^PERMISSIVE_MODE=/{print substr($0, index($0, "=") + 1)}' "$PROJECT_ENV_FILE" | tail -1)"
        PROJECT_AGENT_ARGS="$(awk -F= '/^AGENT_ARGS=/{print substr($0, index($0, "=") + 1)}' "$PROJECT_ENV_FILE" | tail -1)"
        PROJECT_ALL_PACKAGES="$(awk -F= '/^ALL_PACKAGES=/{print substr($0, index($0, "=") + 1)}' "$PROJECT_ENV_FILE" | tail -1)"

        if [[ -n "$PROJECT_AGENT_CMD" && -n "$PROJECT_PERMISSIVE_MODE" ]]; then
            PROJECT_AGENT_ARGS="$(resolve_agent_args "$PROJECT_AGENT_CMD" "$PROJECT_PERMISSIVE_MODE")"
        fi
    fi

    if ! kubectl -n "$PROJECT_NAME" get deployment "$PROJECT_NAME" &>/dev/null 2>&1; then
        echo -e "${YELLOW}⚠${RESET}  No deployment found for '${PROJECT_NAME}'"
        exit 1
    fi

    get_pod() {
        get_project_pod
    }

clear
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
printf "  ║ %-37s ║\n" "Manage Agent: ${PROJECT_NAME}"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${RESET}"

    choose ACTION "Action" \
        "exec    — attach tmux session" \
        "update  — apply saved manifest; restarts only if pod spec changed" \
        "rebuild — regenerate bootstrap and roll a new pod" \
        "restart — rolling restart with current manifest" \
        "status  — show deployment, pod, and logs" \
        "delete  — delete deployment + namespace"

    case "$ACTION" in
        exec*)
            POD="$(get_pod)"
            [[ -z "$POD" ]] && echo "No pod running." && exit 1
            attach_to_project_pod "$POD"
            ;;
        update*)
            apply_project_manifest
            ok "Waiting for updated pod to start..."
            wait_for_pod_running "${POD_START_TIMEOUT_SECONDS:-300}"
            POD="$(get_pod)"
            attach_to_project_pod "$POD"
            ;;
        rebuild*)
            refresh_project_manifest
            apply_project_manifest
            ok "Waiting for rebuilt pod to start..."
            wait_for_pod_running "${POD_START_TIMEOUT_SECONDS:-300}"
            POD="$(get_pod)"
            attach_to_project_pod "$POD"
            ;;
        restart*)
            ok "Restarting deployment/${PROJECT_NAME}..."
            kubectl -n "$PROJECT_NAME" rollout restart deployment/"$PROJECT_NAME"
            ok "Waiting for restarted pod to start..."
            wait_for_pod_running "${POD_START_TIMEOUT_SECONDS:-300}"
            POD="$(get_pod)"
            attach_to_project_pod "$POD"
            ;;
        status*)
            POD="$(get_pod)"
            print_deploy_diagnostics "${POD:-}"
            ;;
        delete*)
            warn "This will delete the namespace '${PROJECT_NAME}' and all its resources."
            confirm "Are you sure?" || exit 0
            kubectl delete namespace "$PROJECT_NAME"
            ok "Deleted namespace ${PROJECT_NAME}"
            ;;
    esac
    exit 0
fi

# ────────────────────────────────────────────────
# Intro
# ────────────────────────────────────────────────
STEPS=8
STEP=0
step() { STEP=$(( STEP + 1 )); header "[${STEP}/${STEPS}] $*"; }

clear
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   k3s + Kata Agent Config Generator   ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${RESET}"
echo -e "  Deploys a Kata-isolated coding agent on k3s.\n"

# ────────────────────────────────────────────────
# 1. Project identity
# ────────────────────────────────────────────────
step "Project"

prompt PROJECT_NAME "Project name (used as namespace + deployment name)" ""
while [[ -z "$PROJECT_NAME" || ! "$PROJECT_NAME" =~ ^[a-z0-9-]+$ ]]; do
    warn "Name must be lowercase letters, numbers, hyphens only"
    prompt PROJECT_NAME "Project name" ""
done

DEFAULT_HOST_PATH="/home/${SUDO_USER:-$USER}/Projects/${PROJECT_NAME}"
prompt_path HOST_PATH "Host path to mount" "$DEFAULT_HOST_PATH"
if [[ ! -d "$HOST_PATH" ]]; then
    warn "Directory does not exist: $HOST_PATH"
    if confirm "Create it?"; then
        mkdir -p "$HOST_PATH"
        ok "Created $HOST_PATH"
    fi
fi

prompt_path MOUNT_PATH "Mount path inside container" "/home/agent/work"

# ────────────────────────────────────────────────
# 2. Runtime
# ────────────────────────────────────────────────
step "Runtime"

choose RUNTIME_CLASS "Kata runtime flavour" --default 1 \
    "kata-qemu (full VMX isolation)" \
    "kata-clh (Cloud Hypervisor, faster start)" \
    "kata-qemu-tdx (TDX confidential computing)"

case "$RUNTIME_CLASS" in
    kata-qemu-tdx*) RUNTIME_CLASS="kata-qemu-tdx" ;;
    kata-clh*)      RUNTIME_CLASS="kata-clh" ;;
    kata-qemu*)     RUNTIME_CLASS="kata-qemu" ;;
esac

# ────────────────────────────────────────────────
# 3. Base image
# ────────────────────────────────────────────────
step "Base image"

choose BASE_IMAGE "Base container image" --default 1 \
    "debian:trixie-slim" \
    "ubuntu:24.04" \
    "python:3.12-slim" \
    "node:22-slim" \
    "custom"

if [[ "$BASE_IMAGE" == "custom" ]]; then
    prompt BASE_IMAGE "Enter custom image (e.g. myrepo/myimage:tag)" ""
fi

# ────────────────────────────────────────────────
# 4. Toolchains
# ────────────────────────────────────────────────
step "Toolchain packages"
hint "Always installed: python3 python3-pip git curl wget jq ripgrep fd-find bat"

multichoose TOOLCHAINS "Additional toolchains" \
    "nodejs npm" \
    "golang" \
    "rustup" \
    "build-essential"

prompt EXTRA_PACKAGES "Any additional apt packages (space-separated, or leave blank)" ""

# ────────────────────────────────────────────────
# 5. Resources
# ────────────────────────────────────────────────
step "Resource limits"
hint "These are hard limits for the Kata VM. OOM = VM dies, not your host."

choose CPU_PRESET "CPU limit" --default 2 \
    "1 (light scripting)" \
    "2" \
    "4 (compilation / ML)" \
    "8 (heavy parallel builds)" \
    "custom"

case "$CPU_PRESET" in
    1*) CPU=1 ;;
    2*) CPU=2 ;;
    4*) CPU=4 ;;
    8*) CPU=8 ;;
    custom) prompt CPU "CPU limit" "2" ;;
esac

choose MEM_PRESET "Memory limit" --default 3 \
    "1Gi (minimal)" \
    "2Gi" \
    "4Gi" \
    "8Gi (ML / large builds)" \
    "16Gi" \
    "custom"

case "$MEM_PRESET" in
    1Gi*)   MEMORY="1Gi" ;;
    2Gi*)   MEMORY="2Gi" ;;
    4Gi*)   MEMORY="4Gi" ;;
    8Gi*)   MEMORY="8Gi" ;;
    16Gi*)  MEMORY="16Gi" ;;
    custom) prompt MEMORY "Memory limit (e.g. 6Gi)" "4Gi" ;;
esac

choose STORAGE_PRESET "Ephemeral storage limit" --default 2 \
    "10Gi" \
    "20Gi" \
    "50Gi" \
    "100Gi" \
    "custom"

case "$STORAGE_PRESET" in
    10Gi*)  STORAGE="10Gi" ;;
    20Gi*)  STORAGE="20Gi" ;;
    50Gi*)  STORAGE="50Gi" ;;
    100Gi*) STORAGE="100Gi" ;;
    custom) prompt STORAGE "Storage limit (e.g. 30Gi)" "20Gi" ;;
esac

# ────────────────────────────────────────────────
# 6. AI Agent
# ────────────────────────────────────────────────
step "AI Agent"

AGENT_PKG=""
AGENT_CMD=""
AGENT_ARGS=""
PERMISSIVE_MODE=""
AGENT_KEY_NAME=""
AGENT_SECRET_NAME=""
AGENT_SECRET_SOURCE_FILE=""
AGENT_SECRET_KEY=""
AGENT_SECRET_MOUNT_PATH=""
AGENT_SECRET_CONTENT=""

choose AGENT "AI coding agent to install in the container" --default 2 \
    "Claude Code (Anthropic)" \
    "OpenAI Codex" \
    "None"

case "$AGENT" in
    "Claude Code"*)
        AGENT_PKG="@anthropic-ai/claude-code"
        AGENT_CMD="claude"
        ;;
    "OpenAI Codex"*)
        AGENT_PKG="@openai/codex"
        AGENT_CMD="codex"
        AGENT_KEY_NAME="OPENAI_API_KEY"
        ;;
esac

if [[ -n "$AGENT_CMD" ]]; then
    if confirm_yes "Enable permissive mode for the agent container?"; then
        PERMISSIVE_MODE="true"
    else
        PERMISSIVE_MODE="false"
    fi

    AGENT_ARGS="$(resolve_agent_args "$AGENT_CMD" "$PERMISSIVE_MODE")"
fi

if [[ -n "$AGENT_CMD" ]]; then
    case "$AGENT_CMD" in
        claude)
            # Claude Code uses OAuth — inject the whole credentials file as a mounted secret
            for f in \
                "$HOME/.claude/.credentials.json" \
                "$HOME/.config/claude/credentials.json"
            do
                if [[ -f "$f" ]]; then
                    AGENT_SECRET_CONTENT="$(cat "$f")"
                    AGENT_SECRET_SOURCE_FILE="$f"
                    AGENT_SECRET_NAME="${PROJECT_NAME}-claude-credentials"
                    AGENT_SECRET_KEY="credentials.json"
                    AGENT_SECRET_MOUNT_PATH="/home/agent/.claude/.credentials.json"
                    break
                fi
            done

            if [[ -z "$AGENT_SECRET_CONTENT" ]]; then
                hint "No existing Claude credentials file found on this host."
                hint "Running ${AGENT_CMD} auth login so the container can reuse host auth."

                if command -v "$AGENT_CMD" &>/dev/null; then
                    "$AGENT_CMD" auth login 2>/dev/null || true
                else
                    warn "${AGENT_CMD} not found on host — install it first (npm install -g ${AGENT_PKG})"
                    warn "Skipping host auth; you can add the key manually below."
                fi

                for f in \
                    "$HOME/.claude/.credentials.json" \
                    "$HOME/.config/claude/credentials.json"
                do
                    if [[ -f "$f" ]]; then
                        AGENT_SECRET_CONTENT="$(cat "$f")"
                        AGENT_SECRET_SOURCE_FILE="$f"
                        AGENT_SECRET_NAME="${PROJECT_NAME}-claude-credentials"
                        AGENT_SECRET_KEY="credentials.json"
                        AGENT_SECRET_MOUNT_PATH="/home/agent/.claude/.credentials.json"
                        break
                    fi
                done
            else
                ok "Reusing existing Claude auth from ${AGENT_SECRET_SOURCE_FILE}"
            fi

            if [[ -n "$AGENT_SECRET_CONTENT" ]]; then
                ok "Read Claude OAuth credentials from ${AGENT_SECRET_SOURCE_FILE}"
            else
                warn "Could not find Claude credentials file — auth may not have completed"
            fi
            ;;
        codex)
            # Codex may use ChatGPT OAuth (~/.codex/auth.json) or a plain API key
            DERIVED_KEY=""
            CODEX_AUTH_MODE=""

            if [[ ! -f "$HOME/.codex/auth.json" ]]; then
                hint "No existing Codex auth file found on this host."
                hint "Running codex auth login so the container can reuse host auth."

                if command -v "$AGENT_CMD" &>/dev/null; then
                    "$AGENT_CMD" auth login 2>/dev/null || true
                else
                    warn "${AGENT_CMD} not found on host — install it first (npm install -g ${AGENT_PKG})"
                    warn "Skipping host auth; you can add the key manually below."
                fi
            else
                ok "Reusing existing Codex auth from $HOME/.codex/auth.json"
            fi

            if [[ -f "$HOME/.codex/auth.json" ]]; then
                CODEX_AUTH_MODE="$(jq -r '.auth_mode // empty' "$HOME/.codex/auth.json" 2>/dev/null || true)"
                DERIVED_KEY="$(jq -r '.OPENAI_API_KEY // empty' "$HOME/.codex/auth.json" 2>/dev/null || true)"

                if [[ "$CODEX_AUTH_MODE" == "chatgpt" ]]; then
                    AGENT_SECRET_CONTENT="$(cat "$HOME/.codex/auth.json")"
                    AGENT_SECRET_SOURCE_FILE="$HOME/.codex/auth.json"
                    AGENT_SECRET_NAME="${PROJECT_NAME}-codex-auth"
                    AGENT_SECRET_KEY="auth.json"
                    AGENT_SECRET_MOUNT_PATH="/home/agent/.codex/auth.json"
                    ok "Read Codex OAuth credentials from ${AGENT_SECRET_SOURCE_FILE}"
                fi
            fi

            if [[ -n "$DERIVED_KEY" ]]; then
                ok "Derived ${AGENT_KEY_NAME} from host auth"
                add_secret "$AGENT_KEY_NAME" "$DERIVED_KEY"
            elif [[ -z "$AGENT_SECRET_CONTENT" ]]; then
                warn "Could not auto-read credential from host"
                prompt DERIVED_KEY "${AGENT_KEY_NAME} (paste manually, or leave blank to skip)" ""
                [[ -n "$DERIVED_KEY" ]] && add_secret "$AGENT_KEY_NAME" "$DERIVED_KEY"
            fi
            ;;
    esac
fi

# ────────────────────────────────────────────────
# 7. Environment variables
# ────────────────────────────────────────────────
step "Environment variables"

hint "Plain env vars (stored in the Deployment, not encrypted)."
PLAIN_ENV_BLOCKS=""
while confirm "Add a plain env var?"; do
    prompt ENV_VAR_NAME  "Variable name (e.g. GOPATH)" ""
    prompt ENV_VAR_VALUE "Value" ""
    PLAIN_ENV_BLOCKS+="
        - name: ${ENV_VAR_NAME}
          value: \"${ENV_VAR_VALUE}\""
done

hint "Secret env vars (stored as a Kubernetes Secret, injected as env vars)."
SECRETS=()
SECRET_ENV_BLOCKS=""

while confirm "Add a secret env var?"; do
    prompt SECRET_NAME "Variable name" ""
    prompt SECRET_VALUE "Value" ""
    SECRETS+=("${SECRET_NAME}=${SECRET_VALUE}")
    SECRET_ENV_BLOCKS+="
        - name: ${SECRET_NAME}
          valueFrom:
            secretKeyRef:
              name: ${PROJECT_NAME}-secrets
              key: ${SECRET_NAME}"
done

# ────────────────────────────────────────────────
# 8. NodePort service
# ────────────────────────────────────────────────
step "Network"

EXPOSE_SERVICE="false"
if confirm "Expose a port via NodePort service?"; then
    prompt CONTAINER_PORT "Container port" "8080"
    prompt NODE_PORT "NodePort (30000-32767)" "30800"
    EXPOSE_SERVICE="true"
fi

# ────────────────────────────────────────────────
# Assemble package list and init steps
# ────────────────────────────────────────────────
# Agent CLIs require npm; ensure nodejs is present
if [[ -n "$AGENT_PKG" && "$TOOLCHAINS" != *"nodejs"* ]]; then
    TOOLCHAINS="${TOOLCHAINS:+$TOOLCHAINS }nodejs npm"
fi

# Codex relies on bubblewrap inside the container sandbox
if [[ "$AGENT_CMD" == "codex" ]] && [[ "$EXTRA_PACKAGES" != *"bubblewrap"* ]]; then
    EXTRA_PACKAGES="${EXTRA_PACKAGES:+$EXTRA_PACKAGES }bubblewrap"
fi

# Rustup is not an apt package — install via curl; strip from apt list
INSTALL_RUSTUP=false
if [[ "$TOOLCHAINS" == *"rustup"* ]]; then
    INSTALL_RUSTUP=true
    TOOLCHAINS="${TOOLCHAINS//rustup/}"
fi

# baseline is always installed; tmux for exec workflow
BASELINE="$(baseline_packages)"
ALL_PACKAGES="${BASELINE} ${TOOLCHAINS:-} ${EXTRA_PACKAGES:-}"
ALL_PACKAGES=$(echo "$ALL_PACKAGES" | tr ' ' '\n' | sort -u | tr '\n' ' ' | xargs)

RUSTUP_INSTALL_LINE=""
if [[ "$INSTALL_RUSTUP" == "true" ]]; then
    RUSTUP_INSTALL_LINE="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | su agent -c 'sh -s -- -y' && \\"$'\n'"          "
fi

AGENT_INSTALL_LINE=""
if [[ -n "$AGENT_PKG" ]]; then
    AGENT_INSTALL_LINE="$(build_agent_install_line "${AGENT_PKG}")"
fi

AGENT_WRAPPER_LINE=""
if [[ -n "$AGENT_CMD" ]]; then
    AGENT_WRAPPER_LINE="$(build_agent_wrapper_line "${AGENT_CMD}" "${AGENT_ARGS}")"
fi

USER_SETUP_LINE="$(build_user_setup_line)"

# ────────────────────────────────────────────────
# Generate YAML
# ────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
YAML_FILE="${OUTPUT_DIR}/${PROJECT_NAME}.yaml"
ENV_FILE="${OUTPUT_DIR}/${PROJECT_NAME}.env"

cat > "$YAML_FILE" <<YAML
# Agent deployment: ${PROJECT_NAME}
# Generated by new-agent.sh on $(date '+%Y-%m-%d %H:%M:%S')

apiVersion: v1
kind: Namespace
metadata:
  name: ${PROJECT_NAME}
---
YAML

if [[ ${#SECRETS[@]} -gt 0 ]]; then
cat >> "$YAML_FILE" <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: ${PROJECT_NAME}-secrets
  namespace: ${PROJECT_NAME}
type: Opaque
stringData:
$(for s in "${SECRETS[@]}"; do
    key="${s%%=*}"
    val="${s#*=}"
    echo "  ${key}: \"${val}\""
done)
---
YAML
fi

# Agent OAuth credentials — stored as a separate secret and mounted as a file
if [[ -n "$AGENT_SECRET_CONTENT" ]]; then
cat >> "$YAML_FILE" <<YAML
apiVersion: v1
kind: Secret
metadata:
  name: ${AGENT_SECRET_NAME}
  namespace: ${PROJECT_NAME}
type: Opaque
stringData:
  ${AGENT_SECRET_KEY}: |
$(echo "$AGENT_SECRET_CONTENT" | sed 's/^/    /')
---
YAML
fi

cat >> "$YAML_FILE" <<YAML
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${PROJECT_NAME}
  namespace: ${PROJECT_NAME}
spec:
  progressDeadlineSeconds: 900
  replicas: 1
  selector:
    matchLabels:
      app: ${PROJECT_NAME}
  template:
    metadata:
      labels:
        app: ${PROJECT_NAME}
    spec:
      runtimeClassName: ${RUNTIME_CLASS}
      containers:
      - name: agent
        image: ${BASE_IMAGE}
        command: ["/bin/sh", "-c"]
        args:
        - |
$(build_container_bootstrap_lines)
        readinessProbe:
          exec:
            command: ["test", "-f", "/tmp/.ready"]
          initialDelaySeconds: 5
          periodSeconds: 5
          failureThreshold: 60
        resources:
          limits:
            memory: "${MEMORY}"
            cpu: "${CPU}"
            ephemeral-storage: "${STORAGE}"
        volumeMounts:
        - name: project
          mountPath: ${MOUNT_PATH}
        - name: geek-env
          mountPath: /opt/geek-env
          readOnly: true
$(if [[ -n "$AGENT_SECRET_CONTENT" ]]; then
echo "        - name: agent-auth"
echo "          mountPath: ${AGENT_SECRET_MOUNT_PATH}"
echo "          subPath: ${AGENT_SECRET_KEY}"
echo "          readOnly: true"
fi)
YAML

ALL_ENV_BLOCKS="${PLAIN_ENV_BLOCKS}${SECRET_ENV_BLOCKS}"
if [[ -n "$ALL_ENV_BLOCKS" ]]; then
cat >> "$YAML_FILE" <<YAML
        env:${ALL_ENV_BLOCKS}
YAML
fi

cat >> "$YAML_FILE" <<YAML
      volumes:
      - name: project
        hostPath:
          path: ${HOST_PATH}
          type: Directory
      - name: geek-env
        hostPath:
          path: ${REPO_ROOT}
          type: Directory
$(if [[ -n "$AGENT_SECRET_CONTENT" ]]; then
echo "      - name: agent-auth"
echo "        secret:"
echo "          secretName: ${AGENT_SECRET_NAME}"
fi)
YAML

if [[ "$EXPOSE_SERVICE" == "true" ]]; then
cat >> "$YAML_FILE" <<YAML
---
apiVersion: v1
kind: Service
metadata:
  name: ${PROJECT_NAME}
  namespace: ${PROJECT_NAME}
spec:
  type: NodePort
  selector:
    app: ${PROJECT_NAME}
  ports:
  - port: ${CONTAINER_PORT}
    targetPort: ${CONTAINER_PORT}
    nodePort: ${NODE_PORT}
YAML
fi

# ────────────────────────────────────────────────
# Generate .env
# ────────────────────────────────────────────────
cat > "$ENV_FILE" <<ENV
# ${PROJECT_NAME}.env — project config
PROJECT=${PROJECT_NAME}
HOST_PATH=${HOST_PATH}
MOUNT_PATH=${MOUNT_PATH}
RUNTIME_CLASS=${RUNTIME_CLASS}
BASE_IMAGE=${BASE_IMAGE}
CPU=${CPU}
MEMORY=${MEMORY}
STORAGE=${STORAGE}
AGENT=${AGENT}
AGENT_CMD=${AGENT_CMD}
PERMISSIVE_MODE=${PERMISSIVE_MODE}
AGENT_ARGS=${AGENT_ARGS}
ALL_PACKAGES=${ALL_PACKAGES}
ENV

ok "Generated ${YAML_FILE}"

echo ""
echo -e "${BOLD}  Summary${RESET}"
echo -e "  ${DIM}───────────────────────────────────────${RESET}"
echo -e "  Project   ${BOLD}${PROJECT_NAME}${RESET}"
echo -e "  Runtime   ${BOLD}${RUNTIME_CLASS}${RESET}"
echo -e "  Image     ${BOLD}${BASE_IMAGE}${RESET}"
echo -e "  Resources ${BOLD}${CPU} CPU · ${MEMORY} RAM · ${STORAGE} storage${RESET}"
echo -e "  Mount     ${BOLD}${HOST_PATH}${RESET} → ${MOUNT_PATH}"
[[ -n "$AGENT_CMD" ]] && echo -e "  Agent     ${BOLD}${AGENT_CMD} ${AGENT_ARGS}${RESET}"
[[ -n "$AGENT_CMD" ]] && echo -e "  Permissive ${BOLD}${PERMISSIVE_MODE:-false}${RESET}"
[[ -n "$AGENT_CMD" ]] && echo -e "  Command   ${BOLD}${AGENT_CMD}${RESET}"
echo -e "  ${DIM}───────────────────────────────────────${RESET}"
echo ""
confirm_yes "Deploy now?" || exit 0

# ────────────────────────────────────────────────
# Apply, wait, and exec
# ────────────────────────────────────────────────
if ! command -v kubectl &>/dev/null; then
    warn "kubectl not found — skipping deploy. Apply manually:"
    echo -e "  kubectl apply -f ${YAML_FILE}"
    exit 0
fi

if kubectl -n "$PROJECT_NAME" get deployment "$PROJECT_NAME" &>/dev/null 2>&1; then
    warn "Deployment '$PROJECT_NAME' already exists and will be restarted."
    confirm "Continue?" || exit 0
fi

ok "Applying manifests..."
kubectl apply -f "$YAML_FILE"

PROJECT_MOUNT_PATH="$MOUNT_PATH"
PROJECT_AGENT_CMD="$AGENT_CMD"
PROJECT_TMUX_CMD="tmux new-session -A -s main"

ok "Waiting for pod to start..."
wait_for_pod_running "${POD_START_TIMEOUT_SECONDS:-300}"

POD="$(get_project_pod)"

attach_to_project_pod "$POD"
