#!/usr/bin/env python3
"""
Interactive generator and manager for k3s + Kata Containers agent deployments.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "agents"

BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

LOG_STREAM_PROCESS: subprocess.Popen[str] | None = None

PublicState = Literal["none", "saved", "starting", "ready", "failed"]
UserAction = Literal["config", "apply", "exec", "status", "delete"]
SystemEvent = Literal["pod_ready", "failure"]


class AgentError(RuntimeError):
    pass


class InvalidTransitionError(AgentError):
    pass


def transition_public_state(
    current: PublicState,
    action: UserAction | None = None,
    *,
    event: SystemEvent | None = None,
) -> PublicState:
    if (action is None) == (event is None):
        raise InvalidTransitionError("Provide exactly one of action or event")

    if action is not None:
        transitions: dict[tuple[PublicState, UserAction], PublicState] = {
            ("none", "config"): "saved",
            ("none", "status"): "none",
            ("saved", "config"): "saved",
            ("saved", "apply"): "starting",
            ("saved", "status"): "saved",
            ("saved", "delete"): "none",
            ("starting", "status"): "starting",
            ("starting", "delete"): "none",
            ("ready", "config"): "saved",
            ("ready", "apply"): "starting",
            ("ready", "exec"): "ready",
            ("ready", "status"): "ready",
            ("ready", "delete"): "none",
            ("failed", "config"): "saved",
            ("failed", "apply"): "starting",
            ("failed", "status"): "failed",
            ("failed", "delete"): "none",
        }
        try:
            return transitions[(current, action)]
        except KeyError as exc:
            raise InvalidTransitionError(f"Invalid user transition: {current} --{action}--> ?") from exc

    transitions = {
        ("starting", "pod_ready"): "ready",
        ("starting", "failure"): "failed",
    }
    try:
        return transitions[(current, event or "")]
    except KeyError as exc:
        raise InvalidTransitionError(f"Invalid system transition: {current} --{event}--> ?") from exc


def header(message: str) -> None:
    print(f"\n{BOLD}{CYAN}▸ {message}{RESET}")


def hint(message: str) -> None:
    print(f"{DIM}  {message}{RESET}")


def ok(message: str) -> None:
    print(f"{GREEN}✔{RESET} {message}")


def warn(message: str) -> None:
    print(f"{YELLOW}⚠{RESET}  {message}")


def fail(message: str) -> "NoReturn":
    stop_log_stream()
    raise AgentError(message)


def prompt(question: str, default: str = "") -> str:
    if default:
        raw = input(f"{BOLD}{question}{RESET} {DIM}[{default}]{RESET}: ")
        return raw.strip() or default
    return input(f"{BOLD}{question}{RESET}: ").strip()


def prompt_path(question: str, default: str = "") -> str:
    return prompt(question, default)


def choose(question: str, options: list[str], default_idx: int = 0) -> str:
    print(f"{BOLD}{question}{RESET}")
    for index, option in enumerate(options, start=1):
        if default_idx and index == default_idx:
            print(f"  {GREEN}*{RESET} {DIM}{index}{RESET}) {option}")
        else:
            print(f"    {DIM}{index}{RESET}) {option}")

    while True:
        if default_idx:
            raw = input(f"Choice [1-{len(options)}] {DIM}[{default_idx}]{RESET}: ").strip()
            if not raw:
                return options[default_idx - 1]
        else:
            raw = input(f"Choice [1-{len(options)}]: ").strip()
        if raw.isdigit():
            pick = int(raw)
            if 1 <= pick <= len(options):
                return options[pick - 1]
        warn(f"Enter a number between 1 and {len(options)}")


def multichoose(question: str, options: list[str], defaults: list[int] | None = None) -> list[str]:
    defaults = defaults or []
    print(f"{BOLD}{question}{RESET}")
    hint("Enter numbers to select (e.g: 1 3 4), 0 for none. Press Enter to keep defaults (*).")
    for index, option in enumerate(options, start=1):
        marker = f"{GREEN}*{RESET} " if index in defaults else "  "
        print(f"  {marker}{DIM}{index}{RESET}) {option}")
    raw = input("Choices: ").strip()
    if not raw:
        return [options[index - 1] for index in defaults]
    if raw == "0":
        return []
    selected: list[str] = []
    for token in raw.split():
        if token.isdigit():
            pick = int(token)
            if 1 <= pick <= len(options):
                selected.append(options[pick - 1])
    return selected


def confirm(question: str) -> bool:
    return input(f"{BOLD}{question}{RESET} {DIM}[y/N]{RESET}: ").strip().lower() == "y"


def confirm_yes(question: str) -> bool:
    return input(f"{BOLD}{question}{RESET} {DIM}[Y/n]{RESET}: ").strip().lower() not in {"n", "no"}


def run(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    text: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        capture_output=capture,
        check=check,
        text=text,
        input=input_text,
    )


def kubectl(
    args: list[str],
    *,
    capture: bool = True,
    check: bool = True,
    namespace: str | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["kubectl"]
    if namespace:
        cmd.extend(["-n", namespace])
    cmd.extend(args)
    return run(cmd, capture=capture, check=check, input_text=input_text)


def command_exists(name: str) -> bool:
    return subprocess.run(["sh", "-lc", f"command -v {shlex.quote(name)} >/dev/null 2>&1"]).returncode == 0


def normalize_binary_quantity(value: str, field: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        return f"{value}Gi"
    if re.fullmatch(r"\d+(?:\.\d+)?(?:Ki|Mi|Gi|Ti|Pi|Ei)", value):
        return value
    fail(f"{field} must include a Kubernetes binary unit such as Mi, Gi, or Ti")


def cpu_to_millicores(value: str) -> int:
    if re.fullmatch(r"\d+m", value):
        return int(value[:-1])
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return round(float(value) * 1000)
    fail("CPU limit must be an integer core count or millicores")


def quantity_to_bytes(value: str) -> int:
    if re.fullmatch(r"\d+", value):
        return int(value)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|Pi|Ei)", value)
    if not match:
        fail("Quantity must use a supported Kubernetes binary unit")
    amount = float(match.group(1))
    exponent = {"Ki": 1, "Mi": 2, "Gi": 3, "Ti": 4, "Pi": 5, "Ei": 6}[match.group(2)]
    return round(amount * (1024 ** exponent))


def format_cpu_millicores(value: int) -> str:
    return str(value // 1000) if value % 1000 == 0 else f"{value}m"


def format_binary_bytes(value: int) -> str:
    for unit, size in [
        ("Ei", 1024**6),
        ("Pi", 1024**5),
        ("Ti", 1024**4),
        ("Gi", 1024**3),
        ("Mi", 1024**2),
        ("Ki", 1024),
    ]:
        if value >= size and value % size == 0:
            return f"{value // size}{unit}"
    return f"{value}B"


def sort_unique_words(words: Iterable[str]) -> str:
    return " ".join(sorted({word for word in words if word}))


def baseline_packages() -> str:
    return "sudo ca-certificates curl wget git jq tmux python3 python3-pip ripgrep fd-find bat"


def agent_package_for_cmd(cmd: str) -> str:
    return {
        "claude": "@anthropic-ai/claude-code",
        "codex": "@openai/codex",
    }.get(cmd, "")


def resolve_agent_args(agent_cmd: str, permissive_mode: str) -> str:
    if agent_cmd == "claude" and permissive_mode == "true":
        return "--dangerously-skip-permissions"
    if agent_cmd == "codex" and permissive_mode == "true":
        return "--dangerously-bypass-approvals-and-sandbox"
    return ""


def build_agent_install_line(agent_pkg: str) -> str:
    if not agent_pkg:
        return ""
    return f"mkdir -p /opt/agent-cli && npm install -g --prefix /opt/agent-cli {agent_pkg} && \\\n          "


def build_agent_wrapper_line(agent_cmd: str, agent_args: str) -> str:
    if not agent_cmd:
        return ""
    args = f" {agent_args}" if agent_args else ""
    return (
        "printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail' "
        f"'exec /opt/agent-cli/bin/{agent_cmd}{args} \"$@\"' > /usr/local/bin/{agent_cmd} "
        f"&& chmod 755 /usr/local/bin/{agent_cmd} && \\\n          "
    )


def build_user_setup_line() -> str:
    return (
        'su - agent -c "REPO_ROOT=/opt/geek-env SKIP_DEFAULT_SHELL_CHANGE=1 /opt/geek-env/scripts/setup-zsh.sh" && \\\n'
        '          usermod -s "$(command -v zsh)" agent && \\\n'
        '          su - agent -c "REPO_ROOT=/opt/geek-env /opt/geek-env/scripts/setup-nvim.sh" && \\\n'
        '          su - agent -c "REPO_ROOT=/opt/geek-env SKIP_PACKAGE_INSTALL=1 /opt/geek-env/scripts/setup-tmux.sh" && \\\n'
    )


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in text.splitlines())


@dataclass
class SecretEnvVar:
    name: str
    value: str


@dataclass
class PlainEnvVar:
    name: str
    value: str


@dataclass
class AgentConfig:
    project_name: str
    host_path: str
    mount_path: str
    runtime_class: str
    base_image: str
    cpu: str
    memory: str
    storage: str
    agent: str
    agent_cmd: str
    permissive_mode: str
    agent_args: str
    all_packages: str
    install_rustup: bool = False
    plain_env_vars: list[PlainEnvVar] = field(default_factory=list)
    secret_env_vars: list[SecretEnvVar] = field(default_factory=list)
    expose_service: bool = False
    container_port: str = ""
    node_port: str = ""
    agent_secret_name: str = ""
    agent_secret_key: str = ""
    agent_secret_mount_path: str = ""
    agent_secret_content: str = ""

    @property
    def yaml_path(self) -> Path:
        return OUTPUT_DIR / f"{self.project_name}.yaml"

    @property
    def env_path(self) -> Path:
        return OUTPUT_DIR / f"{self.project_name}.env"

    @property
    def agent_state_host_path(self) -> str:
        return f"{self.host_path.rstrip('/')}/.agent-state"

    @property
    def claude_state_host_path(self) -> str:
        return f"{self.agent_state_host_path}/claude"

    @property
    def codex_state_host_path(self) -> str:
        return f"{self.agent_state_host_path}/codex"

    def env_text(self) -> str:
        lines = [
            f"# {self.project_name}.env — project config",
            f"PROJECT={self.project_name}",
            f"HOST_PATH={self.host_path}",
            f"MOUNT_PATH={self.mount_path}",
            f"AGENT_STATE_HOST_PATH={self.agent_state_host_path}",
            f"CLAUDE_STATE_HOST_PATH={self.claude_state_host_path}",
            f"CODEX_STATE_HOST_PATH={self.codex_state_host_path}",
            f"RUNTIME_CLASS={self.runtime_class}",
            f"BASE_IMAGE={self.base_image}",
            f"CPU={self.cpu}",
            f"MEMORY={self.memory}",
            f"STORAGE={self.storage}",
            f"AGENT={self.agent}",
            f"AGENT_CMD={self.agent_cmd}",
            f"PERMISSIVE_MODE={self.permissive_mode}",
            f"AGENT_ARGS={self.agent_args}",
            f"ALL_PACKAGES={self.all_packages}",
            f"INSTALL_RUSTUP={'true' if self.install_rustup else 'false'}",
        ]
        return "\n".join(lines) + "\n"

    def build_container_bootstrap_lines(self) -> str:
        rustup_line = ""
        if self.install_rustup:
            rustup_line = "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | su agent -c 'sh -s -- -y' && \\\n          "
        agent_pkg = agent_package_for_cmd(self.agent_cmd)
        agent_install_line = build_agent_install_line(agent_pkg)
        agent_wrapper_line = build_agent_wrapper_line(self.agent_cmd, self.agent_args)
        return (
            "          if ! id agent >/dev/null 2>&1; then useradd -m -s /bin/bash agent; fi && \\\n"
            "          mkdir -p /home/agent /home/agent/.claude /home/agent/.codex && \\\n"
            "          chown agent:agent /home/agent /home/agent/.claude /home/agent/.codex && \\\n"
            "          apt-get update && apt-get install -y \\\n"
            f"            {self.all_packages} && \\\n"
            "          mkdir -p /etc/sudoers.d && \\\n"
            '          echo "agent ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/agent && \\\n'
            "          chmod 440 /etc/sudoers.d/agent && \\\n"
            f"          {build_user_setup_line()}{rustup_line}{agent_install_line}{agent_wrapper_line}"
            "touch /tmp/.ready && sleep infinity"
        )

    def yaml_text(self) -> str:
        docs: list[str] = [
            "\n".join(
                [
                    f"# Agent deployment: {self.project_name}",
                    f"# Generated by agentctl.py on {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "apiVersion: v1",
                    "kind: Namespace",
                    "metadata:",
                    f"  name: {self.project_name}",
                ]
            )
        ]

        if self.secret_env_vars:
            secret_lines = [
                "apiVersion: v1",
                "kind: Secret",
                "metadata:",
                f"  name: {self.project_name}-secrets",
                f"  namespace: {self.project_name}",
                "type: Opaque",
                "stringData:",
            ]
            for item in self.secret_env_vars:
                secret_lines.append(f'  {item.name}: "{item.value}"')
            docs.append("\n".join(secret_lines))

        if self.agent_secret_content:
            docs.append(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Secret",
                        "metadata:",
                        f"  name: {self.agent_secret_name}",
                        f"  namespace: {self.project_name}",
                        "type: Opaque",
                        "stringData:",
                        f"  {self.agent_secret_key}: |",
                        indent_block(self.agent_secret_content, 4),
                    ]
                )
            )

        deployment_lines = [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            f"  name: {self.project_name}",
            f"  namespace: {self.project_name}",
            "spec:",
            "  progressDeadlineSeconds: 900",
            "  replicas: 1",
            "  selector:",
            "    matchLabels:",
            f"      app: {self.project_name}",
            "  template:",
            "    metadata:",
            "      labels:",
            f"        app: {self.project_name}",
            "    spec:",
            f"      runtimeClassName: {self.runtime_class}",
            "      containers:",
            "      - name: agent",
            f"        image: {self.base_image}",
            '        command: ["/bin/sh", "-c"]',
            "        args:",
            "        - |",
            self.build_container_bootstrap_lines(),
            "        readinessProbe:",
            "          exec:",
            '            command: ["test", "-f", "/tmp/.ready"]',
            "          initialDelaySeconds: 5",
            "          periodSeconds: 5",
            "          failureThreshold: 60",
            "        resources:",
            "          limits:",
            f'            memory: "{self.memory}"',
            f'            cpu: "{self.cpu}"',
            f'            ephemeral-storage: "{self.storage}"',
            "        volumeMounts:",
            "        - name: project",
            f"          mountPath: {self.mount_path}",
            "        - name: claude-home",
            "          mountPath: /home/agent/.claude",
            "        - name: codex-home",
            "          mountPath: /home/agent/.codex",
            "        - name: geek-env",
            "          mountPath: /opt/geek-env",
            "          readOnly: true",
        ]
        if self.agent_secret_content:
            deployment_lines.extend(
                [
                    "        - name: agent-auth",
                    f"          mountPath: {self.agent_secret_mount_path}",
                    f"          subPath: {self.agent_secret_key}",
                    "          readOnly: true",
                ]
            )
        if self.plain_env_vars or self.secret_env_vars:
            deployment_lines.append("        env:")
            for item in self.plain_env_vars:
                deployment_lines.extend(
                    [
                        f"        - name: {item.name}",
                        f'          value: "{item.value}"',
                    ]
                )
            for item in self.secret_env_vars:
                deployment_lines.extend(
                    [
                        f"        - name: {item.name}",
                        "          valueFrom:",
                        "            secretKeyRef:",
                        f"              name: {self.project_name}-secrets",
                        f"              key: {item.name}",
                    ]
                )
        deployment_lines.extend(
            [
                "      volumes:",
                "      - name: project",
                "        hostPath:",
                f"          path: {self.host_path}",
                "          type: Directory",
                "      - name: claude-home",
                "        hostPath:",
                f"          path: {self.claude_state_host_path}",
                "          type: DirectoryOrCreate",
                "      - name: codex-home",
                "        hostPath:",
                f"          path: {self.codex_state_host_path}",
                "          type: DirectoryOrCreate",
                "      - name: geek-env",
                "        hostPath:",
                f"          path: {REPO_ROOT}",
                "          type: Directory",
            ]
        )
        if self.agent_secret_content:
            deployment_lines.extend(
                [
                    "      - name: agent-auth",
                    "        secret:",
                    f"          secretName: {self.agent_secret_name}",
                ]
            )
        docs.append("\n".join(deployment_lines))

        if self.expose_service:
            docs.append(
                "\n".join(
                    [
                        "apiVersion: v1",
                        "kind: Service",
                        "metadata:",
                        f"  name: {self.project_name}",
                        f"  namespace: {self.project_name}",
                        "spec:",
                        "  type: NodePort",
                        "  selector:",
                        f"    app: {self.project_name}",
                        "  ports:",
                        f"  - port: {self.container_port}",
                        f"    targetPort: {self.container_port}",
                        f"    nodePort: {self.node_port}",
                    ]
                )
            )

        return "\n---\n".join(docs) + "\n"


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def rewrite_project_resource_files(project_name: str, memory: str = "", storage: str = "") -> None:
    env_file = OUTPUT_DIR / f"{project_name}.env"
    manifest = OUTPUT_DIR / f"{project_name}.yaml"
    if env_file.exists():
        lines = env_file.read_text().splitlines()
        rewritten: list[str] = []
        for line in lines:
            if memory and line.startswith("MEMORY="):
                rewritten.append(f"MEMORY={memory}")
            elif storage and line.startswith("STORAGE="):
                rewritten.append(f"STORAGE={storage}")
            else:
                rewritten.append(line)
        env_file.write_text("\n".join(rewritten) + "\n")
    if manifest.exists():
        text = manifest.read_text()
        if memory:
            text = re.sub(r'(^\s+memory:\s+")([^"]+)(")', rf'\1{memory}\3', text, flags=re.MULTILINE)
        if storage:
            text = re.sub(r'(^\s+ephemeral-storage:\s+")([^"]+)(")', rf'\1{storage}\3', text, flags=re.MULTILINE)
        manifest.write_text(text)


def extract_manifest_packages(manifest: Path) -> str:
    lines = manifest.read_text().splitlines()
    for index, line in enumerate(lines):
        if "apt-get update && apt-get install -y" in line and index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            return re.sub(r"\s+&&\s+\\$", "", next_line)
    return ""


def load_project_config(project_name: str) -> dict[str, str]:
    env_data = parse_env_file(OUTPUT_DIR / f"{project_name}.env")
    memory = env_data.get("MEMORY")
    storage = env_data.get("STORAGE")
    if memory:
        memory = normalize_binary_quantity(memory, "Saved memory limit")
    if storage:
        storage = normalize_binary_quantity(storage, "Saved storage limit")
    if memory or storage:
        rewrite_project_resource_files(project_name, memory or "", storage or "")
    return env_data


def render_refreshed_bootstrap(project_name: str, env_data: dict[str, str]) -> str:
    manifest = OUTPUT_DIR / f"{project_name}.yaml"
    all_packages = env_data.get("ALL_PACKAGES") or extract_manifest_packages(manifest)
    if not all_packages or "sudo" not in all_packages:
        warn(f"Falling back to derived package set for {project_name}")
        packages = baseline_packages().split()
        if env_data.get("AGENT_CMD"):
            packages.extend(["nodejs", "npm"])
        if env_data.get("AGENT_CMD") == "codex":
            packages.append("bubblewrap")
        all_packages = sort_unique_words(packages)

    cfg = AgentConfig(
        project_name=project_name,
        host_path=env_data.get("HOST_PATH", ""),
        mount_path=env_data.get("MOUNT_PATH", "/home/agent/work"),
        runtime_class=env_data.get("RUNTIME_CLASS", "kata-qemu"),
        base_image=env_data.get("BASE_IMAGE", "debian:trixie-slim"),
        cpu=env_data.get("CPU", "2"),
        memory=env_data.get("MEMORY", "4Gi"),
        storage=env_data.get("STORAGE", "20Gi"),
        agent=env_data.get("AGENT", ""),
        agent_cmd=env_data.get("AGENT_CMD", ""),
        permissive_mode=env_data.get("PERMISSIVE_MODE", ""),
        agent_args=resolve_agent_args(env_data.get("AGENT_CMD", ""), env_data.get("PERMISSIVE_MODE", "")),
        all_packages=all_packages,
        install_rustup=env_data.get("INSTALL_RUSTUP", "false") == "true" or "sh.rustup.rs" in manifest.read_text(),
    )
    return cfg.build_container_bootstrap_lines()


def refresh_project_manifest(project_name: str, env_data: dict[str, str]) -> None:
    manifest = OUTPUT_DIR / f"{project_name}.yaml"
    if not manifest.exists():
        fail(f"Manifest not found: {manifest}")
    bootstrap = render_refreshed_bootstrap(project_name, env_data).splitlines()
    lines = manifest.read_text().splitlines()
    rewritten: list[str] = []
    in_args = False
    for line in lines:
        if not in_args and line == "        - |":
            rewritten.append(line)
            rewritten.extend(bootstrap)
            in_args = True
            continue
        if in_args:
            if line == "        readinessProbe:":
                rewritten.append(line)
                in_args = False
            continue
        rewritten.append(line)
    manifest.write_text("\n".join(rewritten) + "\n")
    ok(f"Refreshed {manifest} with current generator bootstrap")


def get_project_pod(project_name: str, ready_only: bool = False) -> str:
    result = kubectl(
        [
            "get",
            "pods",
            "--selector",
            f"app={project_name}",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "json",
        ],
        namespace=project_name,
    )
    data = json.loads(result.stdout or "{}")
    pods: list[str] = []
    for item in data.get("items", []):
        if item.get("metadata", {}).get("deletionTimestamp"):
            continue
        if ready_only:
            statuses = item.get("status", {}).get("containerStatuses") or []
            if not statuses or not statuses[0].get("ready"):
                continue
        pods.append(f"pod/{item['metadata']['name']}")
    return pods[-1] if pods else ""


def get_pod_json(project_name: str, pod: str) -> dict:
    result = kubectl(["get", pod, "-o", "json"], namespace=project_name)
    return json.loads(result.stdout)


def latest_pod_warning_event(project_name: str, pod: str) -> tuple[str, str]:
    pod_name = pod.removeprefix("pod/")
    result = kubectl(
        [
            "get",
            "events",
            "--field-selector",
            f"involvedObject.name={pod_name},type=Warning",
            "--sort-by=.lastTimestamp",
            "-o",
            "json",
        ],
        namespace=project_name,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return "", ""
    items = json.loads(result.stdout).get("items", [])
    if not items:
        return "", ""
    event = items[-1]
    return event.get("reason", ""), event.get("message", "")


def print_deploy_diagnostics(project_name: str, pod: str = "") -> None:
    print()
    warn(f"Deployment diagnostics for {project_name}:")
    subprocess.run(["kubectl", "-n", project_name, "get", "deployment", project_name, "-o", "wide"], cwd=str(REPO_ROOT))
    subprocess.run(["kubectl", "-n", project_name, "get", "pods", "-o", "wide"], cwd=str(REPO_ROOT))
    if pod:
        print()
        warn(f"Describing {pod}:")
        subprocess.run(["kubectl", "-n", project_name, "describe", pod], cwd=str(REPO_ROOT))
        print()
        warn(f"Recent logs from {pod}:")
        subprocess.run(["kubectl", "-n", project_name, "logs", pod, "--tail=100"], cwd=str(REPO_ROOT))


def stop_log_stream() -> None:
    global LOG_STREAM_PROCESS
    if LOG_STREAM_PROCESS and LOG_STREAM_PROCESS.poll() is None:
        LOG_STREAM_PROCESS.terminate()
        try:
            LOG_STREAM_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            LOG_STREAM_PROCESS.kill()
            LOG_STREAM_PROCESS.wait(timeout=3)
    LOG_STREAM_PROCESS = None


def maybe_start_log_stream(project_name: str, pod: str) -> None:
    global LOG_STREAM_PROCESS
    if LOG_STREAM_PROCESS and LOG_STREAM_PROCESS.poll() is None:
        return
    try:
        data = get_pod_json(project_name, pod)
    except Exception:
        return
    statuses = data.get("status", {}).get("containerStatuses") or []
    running = statuses and statuses[0].get("state", {}).get("running", {}).get("startedAt")
    if running:
        print()
        hint(f"Streaming logs from {pod} while waiting...")
        LOG_STREAM_PROCESS = subprocess.Popen(
            ["kubectl", "-n", project_name, "logs", "-f", pod, "--tail=20", "--ignore-errors=true"],
            cwd=str(REPO_ROOT),
            text=True,
            stdout=None,
            stderr=subprocess.DEVNULL,
        )


def wait_for_deployment_ready(project_name: str, timeout_seconds: int = 900) -> str:
    deadline = time.time() + timeout_seconds
    last_status = ""
    last_pod = ""
    while time.time() < deadline:
        pod = get_project_pod(project_name)
        if pod:
            if pod != last_pod:
                hint(f"Watching {pod}")
                stop_log_stream()
                last_pod = pod
            maybe_start_log_stream(project_name, pod)
            data = get_pod_json(project_name, pod)
            phase = data.get("status", {}).get("phase", "Unknown")
            statuses = data.get("status", {}).get("containerStatuses") or [{}]
            state = statuses[0].get("state", {})
            ready = statuses[0].get("ready") is True
            waiting_reason = (state.get("waiting") or {}).get("reason", "")
            terminated_reason = (state.get("terminated") or {}).get("reason", "")
            conditions = {item.get("type"): item for item in data.get("status", {}).get("conditions", [])}
            scheduled = conditions.get("PodScheduled", {})
            scheduled_reason = scheduled.get("reason", "")
            scheduled_message = scheduled.get("message", "")
            event_reason, event_message = latest_pod_warning_event(project_name, pod)
            if ready:
                stop_log_stream()
                ok("Pod is ready.")
                return pod
            status_key = terminated_reason or waiting_reason or phase
            if status_key and status_key != last_status:
                if terminated_reason:
                    hint(f"Status: {phase} ({terminated_reason})")
                elif waiting_reason:
                    hint(f"Status: {phase} ({waiting_reason})")
                else:
                    hint(f"Status: {phase}")
                last_status = status_key
            if scheduled_reason == "Unschedulable":
                print_deploy_diagnostics(project_name, pod)
                fail(f"Pod is unschedulable: {scheduled_message or 'scheduler could not place the pod'}")
            if event_reason == "FailedMount":
                print_deploy_diagnostics(project_name, pod)
                fail(f"Pod failed before startup: {event_message or 'volume mount failed'}")
            if waiting_reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"}:
                print_deploy_diagnostics(project_name, pod)
                fail(f"Deployment failed while waiting for {project_name} to become ready")
        time.sleep(5)
    pod = get_project_pod(project_name)
    print_deploy_diagnostics(project_name, pod)
    fail(f"Timed out after {timeout_seconds}s waiting for {project_name} to become ready")


def wait_for_pod_running(project_name: str, timeout_seconds: int = 300) -> str:
    deadline = time.time() + timeout_seconds
    last_status = ""
    while time.time() < deadline:
        pod = get_project_pod(project_name)
        if pod:
            data = get_pod_json(project_name, pod)
            phase = data.get("status", {}).get("phase", "Unknown")
            statuses = data.get("status", {}).get("containerStatuses") or [{}]
            state = statuses[0].get("state", {})
            running = (state.get("running") or {}).get("startedAt", "")
            waiting_reason = (state.get("waiting") or {}).get("reason", "")
            terminated_reason = (state.get("terminated") or {}).get("reason", "")
            conditions = {item.get("type"): item for item in data.get("status", {}).get("conditions", [])}
            scheduled = conditions.get("PodScheduled", {})
            scheduled_reason = scheduled.get("reason", "")
            scheduled_message = scheduled.get("message", "")
            event_reason, event_message = latest_pod_warning_event(project_name, pod)
            if running:
                ok("Container is running.")
                return pod
            status_key = terminated_reason or waiting_reason or phase
            if status_key and status_key != last_status:
                if terminated_reason:
                    hint(f"Status: {phase} ({terminated_reason})")
                elif waiting_reason:
                    hint(f"Status: {phase} ({waiting_reason})")
                else:
                    hint(f"Status: {phase}")
                last_status = status_key
            if scheduled_reason == "Unschedulable":
                print_deploy_diagnostics(project_name, pod)
                fail(f"Pod is unschedulable: {scheduled_message or 'scheduler could not place the pod'}")
            if event_reason == "FailedMount":
                print_deploy_diagnostics(project_name, pod)
                fail(f"Pod failed before startup: {event_message or 'volume mount failed'}")
        time.sleep(2)
    pod = get_project_pod(project_name)
    print_deploy_diagnostics(project_name, pod)
    fail(f"Timed out after {timeout_seconds}s waiting for {project_name} to start running")


def wait_for_agent_user(project_name: str, pod: str, timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = kubectl(["exec", pod, "--", "sh", "-lc", "id agent >/dev/null 2>&1"], namespace=project_name, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    print_deploy_diagnostics(project_name, pod)
    fail(f"The agent user did not become available in {pod} after {timeout_seconds}s")


def wait_for_project_tools(project_name: str, pod: str, agent_cmd: str, timeout_seconds: int = 600) -> None:
    checks = "command -v tmux >/dev/null 2>&1"
    if agent_cmd:
        checks += f" && command -v {shlex.quote(agent_cmd)} >/dev/null 2>&1"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = kubectl(["exec", pod, "--", "sh", "-lc", checks], namespace=project_name, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    print_deploy_diagnostics(project_name, pod)
    if agent_cmd:
        fail(f"tmux and {agent_cmd} did not become available in {pod} after {timeout_seconds}s")
    fail(f"tmux did not become available in {pod} after {timeout_seconds}s")


def attach_to_project_pod(project_name: str, pod: str, work_dir: str, agent_cmd: str, tmux_cmd: str = "tmux new-session -A -s main") -> None:
    ok(f"Attaching to {pod}...")
    maybe_start_log_stream(project_name, pod)
    wait_for_agent_user(project_name, pod)
    if agent_cmd:
        wait_for_project_tools(project_name, pod, agent_cmd)
    stop_log_stream()
    check = kubectl(["exec", pod, "--", "sh", "-lc", "command -v tmux >/dev/null 2>&1"], namespace=project_name, check=False)
    shell_cmd = f"cd {shlex.quote(work_dir)} 2>/dev/null || cd ~; {tmux_cmd}"
    if check.returncode == 0:
        subprocess.run(
            ["kubectl", "-n", project_name, "exec", "-it", pod, "--", "su", "-", "agent", "-c", shell_cmd],
            cwd=str(REPO_ROOT),
            check=False,
        )
        return
    warn(f"tmux is not ready yet. Opening an agent shell in {work_dir}.")
    subprocess.run(
        ["kubectl", "-n", project_name, "exec", "-it", pod, "--", "su", "-", "agent", "-c", f"cd {shlex.quote(work_dir)} 2>/dev/null || cd ~; exec \"${{SHELL:-/bin/sh}}\""],
        cwd=str(REPO_ROOT),
        check=False,
    )


def get_deployment_generation(project_name: str, observed: bool = False) -> str:
    path = "{.status.observedGeneration}" if observed else "{.metadata.generation}"
    result = kubectl(["get", "deployment", project_name, "-o", f"jsonpath={path}"], namespace=project_name, check=False)
    return (result.stdout or "").strip()


def kubectl_json(args: list[str], namespace: str | None = None) -> dict:
    result = kubectl(args + ["-o", "json"], namespace=namespace)
    return json.loads(result.stdout or "{}")


def check_cluster_resource_fit(cpu: str, memory: str, storage: str) -> None:
    if not command_exists("kubectl"):
        return
    cpu_m = cpu_to_millicores(cpu)
    memory_b = quantity_to_bytes(memory)
    storage_b = quantity_to_bytes(storage)
    try:
        node_data = kubectl_json(["get", "nodes"])
        pod_data = kubectl_json(["get", "pods", "-A"])
    except Exception:
        return
    used_cpu: dict[str, int] = {}
    used_mem: dict[str, int] = {}
    used_storage: dict[str, int] = {}
    for item in pod_data.get("items", []):
        spec = item.get("spec", {})
        status = item.get("status", {})
        node_name = spec.get("nodeName")
        if not node_name or item.get("metadata", {}).get("deletionTimestamp"):
            continue
        if status.get("phase") in {"Succeeded", "Failed"}:
            continue
        req_cpu = req_mem = req_storage = 0
        for container in spec.get("containers", []):
            requests = (container.get("resources") or {}).get("requests") or {}
            if requests.get("cpu"):
                req_cpu += cpu_to_millicores(str(requests["cpu"]))
            if requests.get("memory"):
                req_mem += quantity_to_bytes(str(requests["memory"]))
            if requests.get("ephemeral-storage"):
                req_storage += quantity_to_bytes(str(requests["ephemeral-storage"]))
        init_cpu = init_mem = init_store = 0
        for container in spec.get("initContainers") or []:
            requests = (container.get("resources") or {}).get("requests") or {}
            init_cpu = max(init_cpu, cpu_to_millicores(str(requests.get("cpu", "0"))))
            if requests.get("memory"):
                init_mem = max(init_mem, quantity_to_bytes(str(requests["memory"])))
            if requests.get("ephemeral-storage"):
                init_store = max(init_store, quantity_to_bytes(str(requests["ephemeral-storage"])))
        req_cpu = max(req_cpu, init_cpu)
        req_mem = max(req_mem, init_mem)
        req_storage = max(req_storage, init_store)
        used_cpu[node_name] = used_cpu.get(node_name, 0) + req_cpu
        used_mem[node_name] = used_mem.get(node_name, 0) + req_mem
        used_storage[node_name] = used_storage.get(node_name, 0) + req_storage
    best = {"cpu": (0, "n/a"), "memory": (0, "n/a"), "storage": (0, "n/a")}
    for item in node_data.get("items", []):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        status = item.get("status", {})
        name = metadata.get("name", "")
        if spec.get("unschedulable"):
            continue
        conditions = {entry.get("type"): entry.get("status") for entry in status.get("conditions", [])}
        if conditions.get("Ready") != "True":
            continue
        alloc = status.get("allocatable", {})
        free_cpu = max(cpu_to_millicores(str(alloc.get("cpu", "0"))) - used_cpu.get(name, 0), 0)
        free_mem = max(quantity_to_bytes(str(alloc.get("memory", "0"))) - used_mem.get(name, 0), 0)
        free_store = max(quantity_to_bytes(str(alloc.get("ephemeral-storage", "0"))) - used_storage.get(name, 0), 0)
        if free_cpu > best["cpu"][0]:
            best["cpu"] = (free_cpu, name)
        if free_mem > best["memory"][0]:
            best["memory"] = (free_mem, name)
        if free_store > best["storage"][0]:
            best["storage"] = (free_store, name)
        if free_cpu >= cpu_m and free_mem >= memory_b and free_store >= storage_b:
            hint(f"Preflight: {name} has room for {cpu} CPU · {memory} RAM · {storage} storage after current pod requests")
            return
    fail(
        "No ready schedulable node has enough remaining requested capacity for "
        f"{cpu} CPU · {memory} RAM · {storage} storage. Largest free capacity seen after current requests: "
        f"cpu {format_cpu_millicores(best['cpu'][0])} on {best['cpu'][1]}, "
        f"memory {format_binary_bytes(best['memory'][0])} on {best['memory'][1]}, "
        f"storage {format_binary_bytes(best['storage'][0])} on {best['storage'][1]}"
    )


def apply_project_manifest(project_name: str, cpu: str, memory: str, storage: str) -> None:
    manifest = OUTPUT_DIR / f"{project_name}.yaml"
    if not manifest.exists():
        fail(f"Manifest not found: {manifest}")
    check_cluster_resource_fit(cpu, memory, storage)
    ok(f"Applying {manifest}...")
    kubectl(["apply", "-f", str(manifest)], capture=False, namespace=None)


def manage_project(project_name: str) -> None:
    env_data = load_project_config(project_name)
    mount_path = env_data.get("MOUNT_PATH", "/home/agent/work") or "/home/agent/work"
    agent_cmd = env_data.get("AGENT_CMD", "")
    permissive_mode = env_data.get("PERMISSIVE_MODE", "")
    agent_args = resolve_agent_args(agent_cmd, permissive_mode) if agent_cmd and permissive_mode else env_data.get("AGENT_ARGS", "")
    all_packages = env_data.get("ALL_PACKAGES", "")
    cpu = env_data.get("CPU", "2")
    memory = env_data.get("MEMORY", "4Gi")
    storage = env_data.get("STORAGE", "20Gi")

    exists = kubectl(["get", "deployment", project_name], namespace=project_name, check=False)
    if exists.returncode != 0:
        warn(f"No deployment found for '{project_name}'")
        sys.exit(1)

    os.system("clear")
    print(f"{BOLD}{CYAN}")
    print("  ╔═══════════════════════════════════════╗")
    print(f"  ║ {'Manage Agent: ' + project_name:<37} ║")
    print("  ╚═══════════════════════════════════════╝")
    print(f"{RESET}")

    action = choose(
        "Action",
        [
            "exec    — attach tmux session",
            "update  — apply saved manifest; restarts only if pod spec changed",
            "rebuild — regenerate bootstrap and roll a new pod",
            "restart — rolling restart with current manifest",
            "status  — show deployment, pod, and logs",
            "delete  — delete deployment + namespace",
        ],
    )

    if action.startswith("exec"):
        pod = get_project_pod(project_name, ready_only=True) or get_project_pod(project_name)
        if not pod:
            print("No pod running.")
            return
        attach_to_project_pod(project_name, pod, mount_path, agent_cmd)
        return
    if action.startswith("update"):
        generation_before = get_deployment_generation(project_name)
        observed_before = get_deployment_generation(project_name, observed=True)
        apply_project_manifest(project_name, cpu, memory, storage)
        generation_after = get_deployment_generation(project_name)
        observed_after = get_deployment_generation(project_name, observed=True)
        if generation_after and generation_after != generation_before:
            ok("Pod template changed; waiting for rollout to finish...")
            if observed_after != generation_after:
                hint(f"Deployment generation: {generation_before or 'unknown'} -> {generation_after}")
            pod = wait_for_deployment_ready(project_name)
        else:
            ok("No pod-template change detected; reusing the current pod.")
            if observed_after and observed_after != observed_before:
                hint(f"Deployment controller observed generation {observed_after}.")
            pod = get_project_pod(project_name, ready_only=True) or get_project_pod(project_name)
        attach_to_project_pod(project_name, pod, mount_path, agent_cmd)
        return
    if action.startswith("rebuild"):
        refresh_project_manifest(project_name, env_data)
        apply_project_manifest(project_name, cpu, memory, storage)
        ok("Waiting for rebuilt pod to become ready...")
        pod = wait_for_deployment_ready(project_name)
        attach_to_project_pod(project_name, pod, mount_path, agent_cmd)
        return
    if action.startswith("restart"):
        ok(f"Restarting deployment/{project_name}...")
        kubectl(["rollout", "restart", f"deployment/{project_name}"], namespace=project_name, capture=False)
        ok("Waiting for restarted pod to become ready...")
        pod = wait_for_deployment_ready(project_name)
        attach_to_project_pod(project_name, pod, mount_path, agent_cmd)
        return
    if action.startswith("status"):
        pod = get_project_pod(project_name)
        print_deploy_diagnostics(project_name, pod)
        return
    if action.startswith("delete"):
        warn(f"This will delete the namespace '{project_name}' and all its resources.")
        if not confirm("Are you sure?"):
            return
        kubectl(["delete", "namespace", project_name], capture=False)
        ok(f"Deleted namespace {project_name}")


def find_first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def gather_agent_auth(agent_cmd: str, project_name: str) -> tuple[str, str, str, str]:
    if agent_cmd == "claude":
        path = find_first_existing(
            [
                Path.home() / ".claude" / ".credentials.json",
                Path.home() / ".config" / "claude" / "credentials.json",
            ]
        )
        if not path:
            hint("No existing Claude credentials file found on this host.")
            hint("Running claude auth login so the container can reuse host auth.")
            if command_exists("claude"):
                subprocess.run(["claude", "auth", "login"], cwd=str(REPO_ROOT), check=False)
            path = find_first_existing(
                [
                    Path.home() / ".claude" / ".credentials.json",
                    Path.home() / ".config" / "claude" / "credentials.json",
                ]
            )
        if path:
            ok(f"Read Claude OAuth credentials from {path}")
            return f"{project_name}-claude-credentials", "credentials.json", "/home/agent/.claude/.credentials.json", path.read_text()
        warn("Could not find Claude credentials file — auth may not have completed")
        return "", "", "", ""
    if agent_cmd == "codex":
        auth_path = Path.home() / ".codex" / "auth.json"
        if not auth_path.exists():
            hint("No existing Codex auth file found on this host.")
            hint("Running codex auth login so the container can reuse host auth.")
            if command_exists("codex"):
                subprocess.run(["codex", "auth", "login"], cwd=str(REPO_ROOT), check=False)
        if auth_path.exists():
            data = json.loads(auth_path.read_text())
            if data.get("auth_mode") == "chatgpt":
                ok(f"Read Codex OAuth credentials from {auth_path}")
                return f"{project_name}-codex-auth", "auth.json", "/home/agent/.codex/auth.json", auth_path.read_text()
        warn("Could not auto-read Codex OAuth credentials from host")
    return "", "", "", ""


def build_config_interactively() -> AgentConfig:
    steps = 8
    step = 0

    def next_step(title: str) -> None:
        nonlocal step
        step += 1
        header(f"[{step}/{steps}] {title}")

    os.system("clear")
    print(f"{BOLD}{CYAN}")
    print("  ╔═══════════════════════════════════════╗")
    print("  ║   k3s + Kata Agent Config Generator   ║")
    print("  ╚═══════════════════════════════════════╝")
    print(f"{RESET}")
    print("  Deploys a Kata-isolated coding agent on k3s.\n")

    next_step("Project")
    project_name = prompt("Project name (used as namespace + deployment name)")
    while not project_name or not re.fullmatch(r"[a-z0-9-]+", project_name):
        warn("Name must be lowercase letters, numbers, hyphens only")
        project_name = prompt("Project name")

    default_host_path = f"/home/{os.environ.get('SUDO_USER') or os.environ.get('USER')}/Projects/{project_name}"
    host_path = prompt_path("Host path to mount", default_host_path)
    if not Path(host_path).exists():
        warn(f"Directory does not exist: {host_path}")
        if confirm("Create it?"):
            Path(host_path).mkdir(parents=True, exist_ok=True)
            ok(f"Created {host_path}")
    mount_path = prompt_path("Mount path inside container", "/home/agent/work")

    next_step("Runtime")
    runtime_class = choose(
        "Kata runtime flavour",
        [
            "kata-qemu (full VMX isolation)",
            "kata-clh (Cloud Hypervisor, faster start)",
            "kata-qemu-tdx (TDX confidential computing)",
        ],
        default_idx=1,
    )
    if runtime_class.startswith("kata-qemu-tdx"):
        runtime_class = "kata-qemu-tdx"
    elif runtime_class.startswith("kata-clh"):
        runtime_class = "kata-clh"
    else:
        runtime_class = "kata-qemu"

    next_step("Base image")
    base_image = choose(
        "Base container image",
        [
            "debian:trixie-slim",
            "ubuntu:24.04",
            "python:3.12-slim",
            "node:22-slim",
            "custom",
        ],
        default_idx=1,
    )
    if base_image == "custom":
        base_image = prompt("Enter custom image (e.g. myrepo/myimage:tag)")

    next_step("Toolchain packages")
    hint("Always installed: python3 python3-pip git curl wget jq ripgrep fd-find bat")
    toolchains = multichoose(
        "Additional toolchains",
        ["nodejs npm", "golang", "rustup", "build-essential"],
    )
    extra_packages = prompt("Any additional apt packages (space-separated, or leave blank)")

    next_step("Resource limits")
    hint("These are hard limits for the Kata VM. OOM = VM dies, not your host.")
    hint("Memory and storage values use Kubernetes binary units. Bare numbers default to Gi.")
    cpu_preset = choose("CPU limit", ["1 (light scripting)", "2", "4 (compilation / ML)", "8 (heavy parallel builds)", "custom"], default_idx=2)
    cpu = {"1 (light scripting)": "1", "2": "2", "4 (compilation / ML)": "4", "8 (heavy parallel builds)": "8"}.get(cpu_preset, "")
    if not cpu:
        cpu = prompt("CPU limit", "2")
    mem_preset = choose("Memory limit", ["1Gi (minimal)", "2Gi", "4Gi", "8Gi (ML / large builds)", "16Gi", "custom"], default_idx=3)
    memory = {"1Gi (minimal)": "1Gi", "2Gi": "2Gi", "4Gi": "4Gi", "8Gi (ML / large builds)": "8Gi", "16Gi": "16Gi"}.get(mem_preset, "")
    if not memory:
        memory = prompt("Memory limit (e.g. 6Gi)", "4Gi")
    memory = normalize_binary_quantity(memory, "Memory limit")
    storage_preset = choose("Ephemeral storage limit", ["10Gi", "20Gi", "50Gi", "100Gi", "custom"], default_idx=2)
    storage = {"10Gi": "10Gi", "20Gi": "20Gi", "50Gi": "50Gi", "100Gi": "100Gi"}.get(storage_preset, "")
    if not storage:
        storage = prompt("Storage limit (e.g. 30Gi)", "20Gi")
    storage = normalize_binary_quantity(storage, "Ephemeral storage limit")

    next_step("AI Agent")
    agent_selection = choose("AI coding agent to install in the container", ["Claude Code (Anthropic)", "OpenAI Codex", "None"], default_idx=2)
    agent_pkg = ""
    agent_cmd = ""
    agent = agent_selection
    if agent_selection.startswith("Claude Code"):
        agent_pkg = "@anthropic-ai/claude-code"
        agent_cmd = "claude"
    elif agent_selection.startswith("OpenAI Codex"):
        agent_pkg = "@openai/codex"
        agent_cmd = "codex"
    permissive_mode = ""
    agent_args = ""
    secret_env_vars: list[SecretEnvVar] = []
    if agent_cmd:
        permissive_mode = "true" if confirm_yes("Enable permissive mode for the agent container?") else "false"
        agent_args = resolve_agent_args(agent_cmd, permissive_mode)
    agent_secret_name = ""
    agent_secret_key = ""
    agent_secret_mount_path = ""
    agent_secret_content = ""
    if agent_cmd:
        agent_secret_name, agent_secret_key, agent_secret_mount_path, agent_secret_content = gather_agent_auth(agent_cmd, project_name)
        if agent_cmd == "codex":
            auth_path = Path.home() / ".codex" / "auth.json"
            if auth_path.exists():
                try:
                    auth = json.loads(auth_path.read_text())
                    derived_key = auth.get("OPENAI_API_KEY") or ""
                except json.JSONDecodeError:
                    derived_key = ""
                if derived_key:
                    ok("Derived OPENAI_API_KEY from host auth")
                    secret_env_vars.append(SecretEnvVar("OPENAI_API_KEY", derived_key))
                elif not agent_secret_content:
                    warn("Could not auto-read credential from host")
                    manual = prompt("OPENAI_API_KEY (paste manually, or leave blank to skip)")
                    if manual:
                        secret_env_vars.append(SecretEnvVar("OPENAI_API_KEY", manual))

    next_step("Environment variables")
    hint("Plain env vars (stored in the Deployment, not encrypted).")
    plain_env_vars: list[PlainEnvVar] = []
    while confirm("Add a plain env var?"):
        plain_env_vars.append(PlainEnvVar(prompt("Variable name (e.g. GOPATH)"), prompt("Value")))

    hint("Secret env vars (stored as a Kubernetes Secret, injected as env vars).")
    while confirm("Add a secret env var?"):
        secret_env_vars.append(SecretEnvVar(prompt("Variable name"), prompt("Value")))

    next_step("Network")
    expose_service = False
    container_port = ""
    node_port = ""
    if confirm("Expose a port via NodePort service?"):
        container_port = prompt("Container port", "8080")
        node_port = prompt("NodePort (30000-32767)", "30800")
        expose_service = True

    toolchain_words = []
    for item in toolchains:
        toolchain_words.extend(item.split())
    extra_words = extra_packages.split()
    if agent_pkg and "nodejs" not in toolchain_words:
        toolchain_words.extend(["nodejs", "npm"])
    if agent_cmd == "codex" and "bubblewrap" not in extra_words:
        extra_words.append("bubblewrap")
    install_rustup = "rustup" in toolchain_words
    if install_rustup:
        toolchain_words = [word for word in toolchain_words if word != "rustup"]
    all_packages = sort_unique_words((baseline_packages() + " " + " ".join(toolchain_words + extra_words)).split())

    cfg = AgentConfig(
        project_name=project_name,
        host_path=host_path,
        mount_path=mount_path,
        runtime_class=runtime_class,
        base_image=base_image,
        cpu=cpu,
        memory=memory,
        storage=storage,
        agent=agent,
        agent_cmd=agent_cmd,
        permissive_mode=permissive_mode,
        agent_args=agent_args,
        all_packages=all_packages,
        install_rustup=install_rustup,
        plain_env_vars=plain_env_vars,
        secret_env_vars=secret_env_vars,
        expose_service=expose_service,
        container_port=container_port,
        node_port=node_port,
        agent_secret_name=agent_secret_name,
        agent_secret_key=agent_secret_key,
        agent_secret_mount_path=agent_secret_mount_path,
        agent_secret_content=agent_secret_content,
    )
    return cfg


def write_project_files(cfg: AgentConfig) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.yaml_path.write_text(cfg.yaml_text())
    cfg.env_path.write_text(cfg.env_text())
    ok(f"Generated {cfg.yaml_path}")


def print_summary(cfg: AgentConfig) -> None:
    print()
    print(f"{BOLD}  Summary{RESET}")
    print(f"  {DIM}───────────────────────────────────────{RESET}")
    print(f"  Project   {BOLD}{cfg.project_name}{RESET}")
    print(f"  Runtime   {BOLD}{cfg.runtime_class}{RESET}")
    print(f"  Image     {BOLD}{cfg.base_image}{RESET}")
    print(f"  Resources {BOLD}{cfg.cpu} CPU · {cfg.memory} RAM · {cfg.storage} storage{RESET}")
    print(f"  Mount     {BOLD}{cfg.host_path}{RESET} → {cfg.mount_path}")
    if cfg.agent_cmd:
        print(f"  Agent     {BOLD}{cfg.agent_cmd} {cfg.agent_args}{RESET}")
        print(f"  Permissive {BOLD}{cfg.permissive_mode or 'false'}{RESET}")
        print(f"  Command   {BOLD}{cfg.agent_cmd}{RESET}")
    print(f"  {DIM}───────────────────────────────────────{RESET}")
    print()


def deploy_new_project(cfg: AgentConfig) -> None:
    if not command_exists("kubectl"):
        warn("kubectl not found — skipping deploy. Apply manually:")
        print(f"  kubectl apply -f {cfg.yaml_path}")
        return
    exists = kubectl(["get", "deployment", cfg.project_name], namespace=cfg.project_name, check=False)
    if exists.returncode == 0:
        warn(f"Deployment '{cfg.project_name}' already exists and will be restarted.")
        if not confirm("Continue?"):
            return
    ok("Applying manifests...")
    check_cluster_resource_fit(cfg.cpu, cfg.memory, cfg.storage)
    kubectl(["apply", "-f", str(cfg.yaml_path)], capture=False)
    ok("Waiting for pod to start...")
    pod = wait_for_pod_running(cfg.project_name)
    attach_to_project_pod(cfg.project_name, pod, cfg.mount_path, cfg.agent_cmd)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate and manage k3s Kata agent deployments.")
    parser.add_argument("project", nargs="?", help="Manage an existing project")
    args = parser.parse_args(argv)

    try:
        if args.project:
            manage_project(args.project)
        else:
            cfg = build_config_interactively()
            write_project_files(cfg)
            print_summary(cfg)
            if confirm_yes("Deploy now?"):
                deploy_new_project(cfg)
        return 0
    except AgentError as exc:
        print(f"{YELLOW}✖{RESET}  {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        print(f"{YELLOW}✖{RESET}  Command failed: {detail}", file=sys.stderr)
        return exc.returncode or 1
    finally:
        stop_log_stream()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
