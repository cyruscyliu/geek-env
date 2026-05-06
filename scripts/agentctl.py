#!/usr/bin/env python3
"""
Interactive generator and manager for k3s + Kata Containers agent deployments.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.formatted_text import ANSI
import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
OUTPUT_DIR = REPO_ROOT / "agents"
SECRETS_DIR = REPO_ROOT / "secrets" / "agentctl"

BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

LOG_STREAM_PROCESS: subprocess.Popen[str] | None = None

class AgentError(RuntimeError):
    pass


class BackSignal(Exception):
    pass


@dataclass
class FileSnapshot:
    path: Path
    existed: bool
    content: str = ""


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


def is_back_token(raw: str) -> bool:
    return raw.strip().lower() in {"<", "back"}


def prompt(question: str, default: str = "") -> str:
    if default:
        raw = input(f"{BOLD}{question}{RESET} {DIM}[{default}]{RESET}: ")
        if is_back_token(raw):
            raise BackSignal()
        return raw.strip() or default
    raw = input(f"{BOLD}{question}{RESET}: ").strip()
    if is_back_token(raw):
        raise BackSignal()
    return raw


def prompt_path(question: str, default: str = "") -> str:
    completer = PathCompleter(expanduser=True)
    suffix = f" {DIM}[{default}]{RESET}" if default else ""
    raw = pt_prompt(
        ANSI(f"{BOLD}{question}{RESET}{suffix}: "),
        default=default,
        completer=completer,
        complete_while_typing=True,
    )
    if is_back_token(raw):
        raise BackSignal()
    return raw.strip() or default


def choose(question: str, options: list[str], default_idx: int = 0) -> str:
    print(f"{BOLD}{question}{RESET}")
    hint("Type '<' or 'back' to return to the previous section.")
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
        if is_back_token(raw):
            raise BackSignal()
        if raw.isdigit():
            pick = int(raw)
            if 1 <= pick <= len(options):
                return options[pick - 1]
        warn(f"Enter a number between 1 and {len(options)}")


def multichoose(question: str, options: list[str], defaults: list[int] | None = None) -> list[str]:
    defaults = defaults or []
    print(f"{BOLD}{question}{RESET}")
    hint("Enter numbers to select (e.g: 1 3 4), 0 for none. Press Enter to keep defaults (*).")
    hint("Type '<' or 'back' to return to the previous section.")
    for index, option in enumerate(options, start=1):
        marker = f"{GREEN}*{RESET} " if index in defaults else "  "
        print(f"  {marker}{DIM}{index}{RESET}) {option}")
    raw = input("Choices: ").strip()
    if is_back_token(raw):
        raise BackSignal()
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
    raw = input(f"{BOLD}{question}{RESET} {DIM}[y/N]{RESET}: ").strip().lower()
    if is_back_token(raw):
        raise BackSignal()
    return raw == "y"


def confirm_yes(question: str) -> bool:
    raw = input(f"{BOLD}{question}{RESET} {DIM}[Y/n]{RESET}: ").strip().lower()
    if is_back_token(raw):
        raise BackSignal()
    return raw not in {"n", "no"}


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


def is_valid_project_name(value: str) -> bool:
    return re.fullmatch(r"[a-z](?:[a-z0-9-]{0,30}[a-z0-9])?", value) is not None


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


def host_cpu_count() -> str:
    count = os.cpu_count()
    return str(count) if count else "unknown"


def host_available_disk(path: str) -> str:
    try:
        usage = shutil.disk_usage(path or ".")
    except OSError:
        return "unknown"
    return format_binary_bytes(usage.free)


def host_total_memory() -> str:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return "unknown"
    if not isinstance(page_size, int) or not isinstance(phys_pages, int):
        return "unknown"
    return format_binary_bytes(page_size * phys_pages)


def baseline_packages() -> str:
    return "sudo ca-certificates curl wget git jq python3 python3-pip ripgrep fd-find bat build-essential nodejs npm bubblewrap"


def agent_label_for_cmd(cmd: str) -> str:
    return {
        "codex": "OpenAI Codex",
        "claude": "Claude Code",
        "multi": "Codex + Claude Code",
        "": "None",
        "none": "None",
    }.get(cmd, cmd)


def agent_package_for_cmd(cmd: str) -> str:
    return {
        "codex": "@openai/codex",
        "claude": "@anthropic-ai/claude-code",
    }.get(cmd, "")

def build_agent_install_line(agent_pkg: str) -> str:
    if not agent_pkg:
        return ""
    return (
        f"          echo 'installing {agent_pkg}' && \\\n"
        f"          mkdir -p /opt/agent-cli && npm install -g --prefix /opt/agent-cli {agent_pkg} && \\\n"
    )


def build_paseo_install_line(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "          echo 'installing @getpaseo/cli' && \\\n"
        "          mkdir -p /opt/agent-cli && npm install -g --prefix /opt/agent-cli @getpaseo/cli && \\\n"
    )


def build_paseo_wrapper_line(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        "          printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail' "
        "'exec /opt/agent-cli/bin/paseo \"$@\"' > /usr/local/bin/paseo "
        "&& chmod 755 /usr/local/bin/paseo && \\\n"
    )


def build_agent_wrapper_line(agent_cmd: str, agent_args: str) -> str:
    if not agent_cmd:
        return ""
    args = f" {agent_args}" if agent_args else ""
    return (
        "          printf '%s\\n' '#!/usr/bin/env bash' 'set -euo pipefail' "
        f"'exec /opt/agent-cli/bin/{agent_cmd}{args} \"$@\"' > /usr/local/bin/{agent_cmd} "
        f"&& chmod 755 /usr/local/bin/{agent_cmd} && \\\n"
    )


def build_agent_dirs_line(container_user: str, container_home: str) -> str:
    return (
        f"          mkdir -p {container_home} {container_home}/.codex {container_home}/.claude {container_home}/.paseo && \\\n"
        f"          chown {container_user}:{container_user} {container_home} {container_home}/.codex {container_home}/.claude {container_home}/.paseo && \\\n"
    )


def build_sudoers_line(container_user: str) -> str:
    return (
        "          mkdir -p /etc/sudoers.d && \\\n"
        f'          echo "{container_user} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/{container_user} && \\\n'
        f"          chmod 440 /etc/sudoers.d/{container_user} && \\\n"
    )


def build_paseo_bootstrap_line(agent_cmd: str, container_user: str, container_home: str) -> str:
    if not agent_cmd:
        return ""
    if container_user == "root":
        return (
            "          echo 'starting paseo daemon' && \\\n"
            f"          PASEO_HOME={container_home}/.paseo /opt/agent-cli/bin/paseo daemon start && \\\n"
            "          echo 'pairing paseo daemon' && \\\n"
            f"          paired=0; for i in $(seq 1 30); do PASEO_HOME={container_home}/.paseo /opt/agent-cli/bin/paseo daemon pair --json > {container_home}/.paseo/pairing.json.tmp 2>/dev/null && mv {container_home}/.paseo/pairing.json.tmp {container_home}/.paseo/pairing.json && paired=1 && break; sleep 2; done; test \"$paired\" = 1 && \\\n"
        )
    return (
        "          echo 'starting paseo daemon' && \\\n"
        f'          su - {container_user} -c "PASEO_HOME={container_home}/.paseo /opt/agent-cli/bin/paseo daemon start" && \\\n'
        "          echo 'pairing paseo daemon' && \\\n"
        f'          su - {container_user} -c "for i in \\$(seq 1 30); do PASEO_HOME={container_home}/.paseo /opt/agent-cli/bin/paseo daemon pair --json > {container_home}/.paseo/pairing.json.tmp 2>/dev/null && mv {container_home}/.paseo/pairing.json.tmp {container_home}/.paseo/pairing.json && exit 0; sleep 2; done; exit 1" && \\\n'
    )


def build_auth_copy_lines(container_user: str, auth_files: list["AgentAuthFile"]) -> str:
    if not auth_files:
        return ""
    lines: list[str] = []
    for item in auth_files:
        encoded = base64.b64encode(item.content.encode("utf-8")).decode("ascii")
        parent = str(Path(item.mount_path).parent)
        path_quoted = shlex.quote(item.mount_path)
        parent_quoted = shlex.quote(parent)
        encoded_quoted = shlex.quote(encoded)
        lines.append(
            "          python3 -c "
            + shlex.quote(
                "import base64, pathlib; "
                f"path = pathlib.Path({item.mount_path!r}); "
                f"path.parent.mkdir(parents=True, exist_ok=True); "
                f"path.write_bytes(base64.b64decode({encoded!r}));"
            )
            + f" && chown {container_user}:{container_user} {parent_quoted} {path_quoted} && chmod 600 {path_quoted} && \\\n"
        )
    return "".join(lines)


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else prefix.rstrip() for line in text.splitlines())


def sanitize_codex_config_toml(text: str) -> str:
    lines = text.splitlines()
    sanitized: list[str] = []
    skip_projects_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[projects."):
            skip_projects_block = True
            continue
        if skip_projects_block and stripped.startswith("[") and stripped.endswith("]"):
            skip_projects_block = False
        if skip_projects_block:
            continue
        sanitized.append(line)
    result = "\n".join(sanitized).strip()
    return f"{result}\n" if result else ""


@dataclass
class PlainEnvVar:
    name: str
    value: str


@dataclass
class AgentAuthFile:
    key: str
    mount_path: str
    content: str


@dataclass
class AgentConfig:
    project_name: str
    runtime_class: str
    base_image: str
    cpu: str
    memory: str
    storage: str
    agent: str
    agent_cmd: str
    agent_args: str
    all_packages: str
    runtime_user: str = ""
    persist_state: bool = True
    bootstrap_profile: str = "full"
    install_rustup: bool = False
    plain_env_vars: list[PlainEnvVar] = field(default_factory=list)
    auth_files: list[AgentAuthFile] = field(default_factory=list)
    expose_service: bool = False
    container_port: str = ""
    node_port: str = ""

    @property
    def config_path(self) -> Path:
        return OUTPUT_DIR / f"{self.project_name}.agent.yaml"

    @property
    def yaml_path(self) -> Path:
        return OUTPUT_DIR / f"{self.project_name}.yaml"

    @property
    def project_pvc_name(self) -> str:
        return f"{self.project_name}-project"

    @property
    def container_user(self) -> str:
        return self.runtime_user or self.project_name

    @property
    def container_home(self) -> str:
        return "/root" if self.container_user == "root" else f"/home/{self.container_user}"

    def to_config_dict(self) -> dict:
        return {
            "project": self.project_name,
            "runtime": {
                "class": self.runtime_class,
                "base_image": self.base_image,
                "user": self.container_user,
            },
            "resources": {
                "cpu": self.cpu,
                "memory": self.memory,
                "ephemeral_storage": self.storage,
            },
            "agent": {
                "kind": self.agent_cmd or "none",
                "label": self.agent,
                "args": self.agent_args.split() if self.agent_args else [],
                "persist_state": self.persist_state,
            },
            "tooling": {
                "bootstrap_profile": self.bootstrap_profile,
                "apt_packages": self.all_packages.split(),
                "install_rustup": self.install_rustup,
            },
            "auth": {
                "files": [
                    {
                        "key": item.key,
                        "mount_path": item.mount_path,
                        "content": item.content,
                    }
                    for item in self.auth_files
                ],
            },
            "env": {
                "plain": {item.name: item.value for item in self.plain_env_vars},
            },
            "service": {
                "enabled": self.expose_service,
                "container_port": self.container_port or None,
                "node_port": self.node_port or None,
            },
        }

    def config_text(self) -> str:
        return yaml.safe_dump(self.to_config_dict(), sort_keys=False)

    @classmethod
    def from_config_dict(cls, data: dict) -> "AgentConfig":
        runtime = data.get("runtime", {}) or {}
        resources = data.get("resources", {}) or {}
        agent = data.get("agent", {}) or {}
        tooling = data.get("tooling", {}) or {}
        auth = data.get("auth", {}) or {}
        env = data.get("env", {}) or {}
        service = data.get("service", {}) or {}
        plain = env.get("plain", {}) or {}
        saved_kind = agent.get("kind") or ""
        kind = saved_kind if saved_kind in {"", "none", "codex", "claude", "multi"} else "none"
        label = (
            agent.get("label")
            if saved_kind in {"", "none", "codex", "claude", "multi"}
            else {
                "none": "None",
                "": "None",
            }.get(kind, kind)
        ) or agent_label_for_cmd(kind)
        args = agent.get("args", []) or []
        auth_files_data = auth.get("files", []) or []
        if not auth_files_data:
            legacy_mount_path = auth.get("mount_path") or ""
            legacy_key = auth.get("secret_key") or ""
            legacy_content = auth.get("content") or ""
            if legacy_mount_path and legacy_key and legacy_content:
                auth_files_data = [
                    {
                        "key": legacy_key,
                        "mount_path": legacy_mount_path,
                        "content": legacy_content,
                    }
                ]
        return cls(
            project_name=data["project"],
            runtime_class=runtime.get("class", "kata-qemu"),
            base_image=runtime.get("base_image", "debian:trixie-slim"),
            runtime_user=str(runtime.get("user") or ""),
            cpu=str(resources.get("cpu", "2")),
            memory=normalize_binary_quantity(str(resources.get("memory", "4Gi")), "Saved memory limit"),
            storage=normalize_binary_quantity(str(resources.get("ephemeral_storage", "20Gi")), "Saved storage limit"),
            agent=label,
            agent_cmd="" if kind == "none" else kind,
            agent_args=" ".join(args),
            persist_state=bool(agent.get("persist_state", True)),
            bootstrap_profile=tooling.get("bootstrap_profile", "full"),
            all_packages=" ".join(tooling.get("apt_packages", []) or []),
            install_rustup=bool(tooling.get("install_rustup", False)),
            plain_env_vars=[PlainEnvVar(name, value) for name, value in plain.items()],
            auth_files=[
                AgentAuthFile(
                    key=item.get("key", ""),
                    mount_path=item.get("mount_path", ""),
                    content=item.get("content", ""),
                )
                for item in auth_files_data
                if item.get("key") and item.get("mount_path") and item.get("content")
            ],
            expose_service=bool(service.get("enabled", False)),
            container_port=str(service.get("container_port") or ""),
            node_port=str(service.get("node_port") or ""),
        )

    def build_container_bootstrap_lines(self) -> str:
        user = self.container_user
        home = self.container_home
        user_setup_line = ""
        sudoers_line = ""
        rustup_line = "          curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \\\n"
        if user != "root":
            user_setup_line = f"          if ! id {user} >/dev/null 2>&1; then useradd -m -s /bin/bash {user}; fi && \\\n"
            sudoers_line = build_sudoers_line(user)
            rustup_line = f"          curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | su {user} -c 'sh -s -- -y' && \\\n"
        if self.bootstrap_profile == "minimal":
            return (
                "          set -eux && \\\n"
                f"{user_setup_line}{build_agent_dirs_line(user, home)}{sudoers_line}"
                "          touch /tmp/.ready && sleep infinity"
            )
        agent_install_line = (
            build_agent_install_line(agent_package_for_cmd("codex"))
            + build_agent_install_line(agent_package_for_cmd("claude"))
        )
        paseo_install_line = build_paseo_install_line(True)
        paseo_wrapper_line = build_paseo_wrapper_line(True)
        agent_wrapper_line = (
            build_agent_wrapper_line("codex", "")
            + build_agent_wrapper_line("claude", "")
        )
        auth_copy_lines = build_auth_copy_lines(user, self.auth_files)
        paseo_bootstrap_line = build_paseo_bootstrap_line("multi", user, home)
        return (
            "          set -eux && \\\n"
            f"{user_setup_line}{build_agent_dirs_line(user, home)}"
            "          apt-get update && apt-get install -y \\\n"
            f"            {self.all_packages} && \\\n"
            f"{sudoers_line}{rustup_line}{agent_install_line}{paseo_install_line}{paseo_wrapper_line}{agent_wrapper_line}{auth_copy_lines}{paseo_bootstrap_line}"
            "          touch /tmp/.ready && sleep infinity"
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

        docs.append(
            "\n".join(
                [
                    "apiVersion: v1",
                    "kind: PersistentVolumeClaim",
                    "metadata:",
                    f"  name: {self.project_pvc_name}",
                    f"  namespace: {self.project_name}",
                    "spec:",
                    "  accessModes:",
                    "  - ReadWriteOnce",
                    "  resources:",
                    "    requests:",
                    f'      storage: "{self.storage}"',
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
            "  strategy:",
            "    type: Recreate",
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
            f"          mountPath: {self.container_home}",
        ]
        if self.agent_cmd:
            deployment_lines.extend(
                [
                    "        - name: project",
                    f"          mountPath: {self.container_home}/.paseo",
                    "          subPath: .paseo",
                ]
            )
        env_items: list[str] = []
        for item in self.plain_env_vars:
            env_items.extend(
                [
                    f"        - name: {item.name}",
                    f'          value: "{item.value}"',
                ]
            )
        if self.agent_cmd:
            env_items.extend(
                [
                    "        - name: PASEO_HOME",
                    f'          value: "{self.container_home}/.paseo"',
                ]
            )
        if env_items:
            deployment_lines.append("        env:")
            deployment_lines.extend(env_items)
        deployment_lines.extend(
            [
                "      volumes:",
                "      - name: project",
                "        persistentVolumeClaim:",
                f"          claimName: {self.project_pvc_name}",
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


def snapshot_files(paths: Iterable[Path]) -> list[FileSnapshot]:
    snapshots: list[FileSnapshot] = []
    for path in paths:
        if path.exists():
            snapshots.append(FileSnapshot(path=path, existed=True, content=path.read_text()))
        else:
            snapshots.append(FileSnapshot(path=path, existed=False))
    return snapshots


def restore_files(snapshots: Iterable[FileSnapshot]) -> None:
    for snapshot in snapshots:
        if snapshot.existed:
            snapshot.path.parent.mkdir(parents=True, exist_ok=True)
            snapshot.path.write_text(snapshot.content)
        elif snapshot.path.exists():
            snapshot.path.unlink()


def rollback_created_project(cfg: AgentConfig, snapshots: Iterable[FileSnapshot]) -> None:
    warn(f"Rolling back failed creation for {cfg.project_name}...")
    if command_exists("kubectl"):
        subprocess.run(
            ["kubectl", "delete", "namespace", cfg.project_name, "--ignore-not-found=true", "--wait=false"],
            cwd=str(REPO_ROOT),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    restore_files(snapshots)


def load_project_config(project_name: str) -> AgentConfig:
    config_path = OUTPUT_DIR / f"{project_name}.agent.yaml"
    if not config_path.exists():
        fail(f"Config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text()) or {}
    cfg = AgentConfig.from_config_dict(data)
    fresh_auth_files = gather_agent_auth_files(project_name, cfg.container_home)
    if fresh_auth_files:
        cfg.auth_files = fresh_auth_files
    return cfg


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
                if "unbound immediate PersistentVolumeClaims" in (scheduled_message or ""):
                    time.sleep(2)
                    continue
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
                if "unbound immediate PersistentVolumeClaims" in (scheduled_message or ""):
                    time.sleep(2)
                    continue
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
        result = kubectl(["exec", pod, "--", "sh", "-lc", f"id {shlex.quote(project_name)} >/dev/null 2>&1"], namespace=project_name, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    print_deploy_diagnostics(project_name, pod)
    fail(f"The agent user did not become available in {pod} after {timeout_seconds}s")


def wait_for_project_tools(project_name: str, pod: str, agent_cmd: str, timeout_seconds: int = 600) -> None:
    checks = "true"
    if agent_cmd:
        checks = "command -v codex >/dev/null 2>&1 && command -v claude >/dev/null 2>&1 && command -v paseo >/dev/null 2>&1"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = kubectl(["exec", pod, "--", "sh", "-lc", checks], namespace=project_name, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    print_deploy_diagnostics(project_name, pod)
    if agent_cmd:
        fail(f"codex, claude, and paseo did not become available in {pod} after {timeout_seconds}s")
    fail(f"Project tools did not become available in {pod} after {timeout_seconds}s")


def read_paseo_pairing_info(project_name: str, pod: str, timeout_seconds: int = 120) -> dict:
    deadline = time.time() + timeout_seconds
    cfg = load_project_config(project_name)
    container_home = cfg.container_home
    cmd = (
        f"if [ -s {container_home}/.paseo/pairing.json ]; then "
        f"cat {container_home}/.paseo/pairing.json; "
        "else "
        f"PASEO_HOME={container_home}/.paseo /opt/agent-cli/bin/paseo daemon pair --json; "
        "fi"
    )
    while time.time() < deadline:
        exec_args = ["exec", pod, "--", "sh", "-lc", cmd] if cfg.container_user == "root" else ["exec", pod, "--", "su", "-", cfg.container_user, "-c", cmd]
        result = kubectl(exec_args, namespace=project_name, check=False)
        output = (result.stdout or "").strip()
        if result.returncode == 0 and output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                pass
        time.sleep(2)
    return {}


def print_paseo_pairing_info(project_name: str, pod: str) -> None:
    info = read_paseo_pairing_info(project_name, pod)
    if not info:
        warn("Paseo pairing information is not available yet.")
        return
    print()
    ok("Paseo pairing info:")
    url = info.get("url")
    qr = info.get("qr")
    if url:
        print(f"  URL  {url}")
    if qr:
        print("  QR")
        print(indent_block(str(qr), 4))


def kubectl_exec_args_for_terminal() -> list[str]:
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ["-it"]
    if sys.stdin.isatty():
        return ["-i"]
    return []


def attach_to_project_pod(project_name: str, pod: str, work_dir: str, agent_cmd: str) -> None:
    ok(f"Attaching to {pod}...")
    maybe_start_log_stream(project_name, pod)
    stop_log_stream()
    deadline = time.time() + 180
    exec_flags = kubectl_exec_args_for_terminal()
    if "-t" not in "".join(exec_flags):
        hint("No local TTY detected; using a non-interactive exec session.")
    cfg = load_project_config(project_name)
    if cfg.container_user == "root":
        command = [
            "kubectl",
            "-n",
            project_name,
            "exec",
            *exec_flags,
            pod,
            "--",
            "sh",
            "-lc",
            f"cd {shlex.quote(work_dir)} 2>/dev/null || cd {shlex.quote(cfg.container_home)}; exec \"${{SHELL:-/bin/sh}}\"",
        ]
    else:
        command = [
            "kubectl",
            "-n",
            project_name,
            "exec",
            *exec_flags,
            pod,
            "--",
            "su",
            "-",
            cfg.container_user,
            "-c",
            f"cd {shlex.quote(work_dir)} 2>/dev/null || cd ~; exec \"${{SHELL:-/bin/sh}}\"",
        ]
    while True:
        data = get_pod_json(project_name, pod)
        statuses = data.get("status", {}).get("containerStatuses") or []
        if statuses:
            state = statuses[0].get("state", {})
            waiting = state.get("waiting", {})
            if waiting.get("reason") == "CrashLoopBackOff":
                print_deploy_diagnostics(project_name, pod)
                fail(f"{pod} is in CrashLoopBackOff: {waiting.get('message', 'container is not available for exec')}")
        result = subprocess.run(command, cwd=str(REPO_ROOT), check=False)
        if result.returncode == 0:
            return
        data = get_pod_json(project_name, pod)
        statuses = data.get("status", {}).get("containerStatuses") or []
        if statuses:
            state = statuses[0].get("state", {})
            if not state.get("waiting"):
                return
        if time.time() >= deadline:
            fail(f"Could not attach to {pod} after waiting for an exec-ready container")
        time.sleep(2)


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


def render_project_manifest(cfg: AgentConfig) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.yaml_path.write_text(cfg.yaml_text())


def apply_project_manifest(cfg: AgentConfig) -> None:
    render_project_manifest(cfg)
    check_cluster_resource_fit(cfg.cpu, cfg.memory, cfg.storage)
    ok(f"Applying {cfg.yaml_path}...")
    kubectl(["apply", "-f", str(cfg.yaml_path)], capture=False, namespace=None)


def find_first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def gather_agent_auth_files(project_name: str, container_home: str | None = None) -> list[AgentAuthFile]:
    container_home = container_home or f"/home/{project_name}"
    auth_files: list[AgentAuthFile] = []

    codex_auth_path = SECRETS_DIR / "codex" / "auth.json"
    if codex_auth_path.exists():
        ok(f"Read Codex auth file from {codex_auth_path}")
        auth_files.append(
            AgentAuthFile(
                key="codex-auth.json",
                mount_path=f"{container_home}/.codex/auth.json",
                content=codex_auth_path.read_text(),
            )
        )
    else:
        hint(f"No Codex auth file found in {SECRETS_DIR / 'codex'}.")

    codex_config_path = SECRETS_DIR / "codex" / "config.toml"
    if codex_config_path.exists():
        ok(f"Read Codex config file from {codex_config_path}")
        auth_files.append(
            AgentAuthFile(
                key="codex-config.toml",
                mount_path=f"{container_home}/.codex/config.toml",
                content=sanitize_codex_config_toml(codex_config_path.read_text()),
            )
        )
    else:
        hint(f"No Codex config file found in {SECRETS_DIR / 'codex'}.")

    claude_auth_path = find_first_existing(
        [
            SECRETS_DIR / "claude" / "settings.json",
        ]
    )
    if claude_auth_path is not None:
        ok(f"Read Claude Code credentials from {claude_auth_path}")
        auth_files.append(
            AgentAuthFile(
                key="claude-settings.json",
                mount_path=f"{container_home}/.claude/settings.json",
                content=claude_auth_path.read_text(),
            )
        )
    else:
        hint(f"No Claude settings file found in {SECRETS_DIR / 'claude'}.")

    return auth_files


def derive_extra_package_defaults(cfg: AgentConfig | None) -> str:
    if cfg is None:
        return ""
    baseline = set(baseline_packages().split())
    installed = set(cfg.all_packages.split())
    extras = installed - baseline
    if cfg.agent_cmd == "codex":
        extras.discard("bubblewrap")
    return " ".join(sorted(extras))


def build_config_interactively(initial: AgentConfig | None = None) -> AgentConfig:
    extra_defaults = derive_extra_package_defaults(initial)
    state: dict[str, object] = {
        "project_name": initial.project_name if initial else "",
        "runtime_class": initial.runtime_class if initial else "kata-qemu",
        "base_image": initial.base_image if initial else "debian:trixie-slim",
        "runtime_user": initial.runtime_user if initial else "",
        "extra_packages": extra_defaults,
        "cpu": initial.cpu if initial else "2",
        "memory": initial.memory if initial else "4Gi",
        "storage": initial.storage if initial else "20Gi",
        "agent": initial.agent if initial else "Codex + Claude Code",
        "agent_cmd": initial.agent_cmd if initial else "multi",
        "agent_args": initial.agent_args if initial else "",
        "plain_env_vars": [PlainEnvVar(item.name, item.value) for item in (initial.plain_env_vars if initial else [])],
        "auth_files": [AgentAuthFile(item.key, item.mount_path, item.content) for item in (initial.auth_files if initial else [])],
        "expose_service": initial.expose_service if initial else False,
        "container_port": initial.container_port if initial else "",
        "node_port": initial.node_port if initial else "",
    }

    def render_header(step: int, title: str) -> None:
        os.system("clear")
        print(f"{BOLD}{CYAN}")
        print("  ╔═══════════════════════════════════════╗")
        print("  ║   k3s + Kata Agent Config Generator   ║")
        print("  ╚═══════════════════════════════════════╝")
        print(f"{RESET}")
        print("  Deploys a Kata-isolated coding agent on k3s.\n")
        header(f"[{step}/6] {title}")

    def step_project() -> None:
        project_name = prompt("Project name (used as namespace + deployment name)", str(state["project_name"]))
        while not project_name or not is_valid_project_name(project_name):
            warn("Name must start with a lowercase letter, use only lowercase letters, numbers, or hyphens, end with a letter or number, and stay within 32 characters for user/group compatibility")
            project_name = prompt("Project name", project_name)
        state["project_name"] = project_name

    def step_runtime() -> None:
        runtime_options = [
            "kata-qemu (full VMX isolation)",
            "kata-clh (Cloud Hypervisor, faster start)",
            "kata-qemu-tdx (TDX confidential computing)",
        ]
        default_idx = {"kata-qemu": 1, "kata-clh": 2, "kata-qemu-tdx": 3}.get(str(state["runtime_class"]), 1)
        runtime_class = choose("Kata runtime flavour", runtime_options, default_idx=default_idx)
        if runtime_class.startswith("kata-qemu-tdx"):
            state["runtime_class"] = "kata-qemu-tdx"
        elif runtime_class.startswith("kata-clh"):
            state["runtime_class"] = "kata-clh"
        else:
            state["runtime_class"] = "kata-qemu"

    def step_base_image() -> None:
        base_options = ["debian:trixie-slim", "ubuntu:24.04", "python:3.12-slim", "node:22-slim", "custom"]
        current = str(state["base_image"])
        default_idx = base_options.index(current) + 1 if current in base_options[:-1] else 5
        picked = choose("Base container image", base_options, default_idx=default_idx)
        state["base_image"] = prompt("Enter custom image (e.g. myrepo/myimage:tag)", current) if picked == "custom" else picked

    def step_packages() -> None:
        hint("Always installed: python3 python3-pip git curl wget jq ripgrep fd-find bat build-essential nodejs npm rustup")
        state["extra_packages"] = prompt("Any additional apt packages (space-separated, or leave blank)", str(state["extra_packages"]))

    def step_resources() -> None:
        hint("These are hard limits for the Kata VM. OOM = VM dies, not your host.")
        hint("Memory and storage values use Kubernetes binary units. Bare numbers default to Gi.")
        hint(f"Host reference: {host_cpu_count()} CPU(s) visible")
        hint(f"Host reference: {host_total_memory()} RAM visible")
        resource_step = 0
        while resource_step < 3:
            if resource_step == 0:
                cpu_defaults = {"1": 1, "2": 2, "4": 3, "8": 4}
                try:
                    cpu_preset = choose("CPU limit", ["1 (light scripting)", "2", "4 (compilation / ML)", "8 (heavy parallel builds)", "custom"], default_idx=cpu_defaults.get(str(state["cpu"]), 5))
                except BackSignal:
                    raise
                cpu = {"1 (light scripting)": "1", "2": "2", "4 (compilation / ML)": "4", "8 (heavy parallel builds)": "8"}.get(cpu_preset, "")
                if not cpu:
                    try:
                        cpu = prompt("CPU limit", str(state["cpu"]))
                    except BackSignal:
                        continue
                state["cpu"] = cpu
                resource_step += 1
                continue

            if resource_step == 1:
                mem_defaults = {"1Gi": 1, "2Gi": 2, "4Gi": 3, "8Gi": 4, "16Gi": 5}
                try:
                    mem_preset = choose("Memory limit", ["1Gi (minimal)", "2Gi", "4Gi", "8Gi (ML / large builds)", "16Gi", "custom"], default_idx=mem_defaults.get(str(state["memory"]), 6))
                except BackSignal:
                    resource_step = 0
                    continue
                memory = {"1Gi (minimal)": "1Gi", "2Gi": "2Gi", "4Gi": "4Gi", "8Gi (ML / large builds)": "8Gi", "16Gi": "16Gi"}.get(mem_preset, "")
                if not memory:
                    try:
                        memory = prompt("Memory limit (e.g. 6Gi)", str(state["memory"]))
                    except BackSignal:
                        continue
                state["memory"] = normalize_binary_quantity(memory, "Memory limit")
                resource_step += 1
                continue

            storage_defaults = {"10Gi": 1, "20Gi": 2, "50Gi": 3, "100Gi": 4}
            try:
                storage_preset = choose("Ephemeral storage limit", ["10Gi", "20Gi", "50Gi", "100Gi", "custom"], default_idx=storage_defaults.get(str(state["storage"]), 5))
            except BackSignal:
                resource_step = 1
                continue
            storage = {"10Gi": "10Gi", "20Gi": "20Gi", "50Gi": "50Gi", "100Gi": "100Gi"}.get(storage_preset, "")
            if not storage:
                try:
                    storage = prompt("Storage limit (e.g. 30Gi)", str(state["storage"]))
                except BackSignal:
                    continue
            state["storage"] = normalize_binary_quantity(storage, "Ephemeral storage limit")
            resource_step += 1

    def step_environment() -> None:
        while True:
            plain_items = ", ".join(f"{item.name}={item.value}" for item in list(state["plain_env_vars"])) or "none"
            hint(f"Plain env vars: {plain_items}")
            action = choose(
                "Environment variables",
                [
                    "done",
                    "add plain env var",
                    "remove plain env var",
                    "clear all env vars",
                ],
                default_idx=1,
            )
            plain_env_vars = list(state["plain_env_vars"])
            if action == "done":
                return
            if action == "add plain env var":
                plain_env_vars.append(PlainEnvVar(prompt("Variable name (e.g. GOPATH)"), prompt("Value")))
            elif action == "remove plain env var":
                if not plain_env_vars:
                    warn("No plain env vars to remove")
                    continue
                picked = choose("Remove which plain env var?", [f"{item.name}={item.value}" for item in plain_env_vars])
                plain_env_vars.pop([f"{item.name}={item.value}" for item in plain_env_vars].index(picked))
            elif action == "clear all env vars":
                plain_env_vars = []
            state["plain_env_vars"] = plain_env_vars

    def step_network() -> None:
        default_expose = bool(state["expose_service"])
        expose_service = confirm_yes("Expose a port via NodePort service?") if default_expose else confirm("Expose a port via NodePort service?")
        state["expose_service"] = expose_service
        if expose_service:
            state["container_port"] = prompt("Container port", str(state["container_port"] or "8080"))
            state["node_port"] = prompt("NodePort (30000-32767)", str(state["node_port"] or "30800"))
        else:
            state["container_port"] = ""
            state["node_port"] = ""

    steps: list[tuple[str, callable]] = [
        ("Project", step_project),
        ("Runtime", step_runtime),
        ("Base image", step_base_image),
        ("Extra packages", step_packages),
        ("Resource limits", step_resources),
        ("Environment variables", step_environment),
        ("Network", step_network),
    ]

    index = 0
    while index < len(steps):
        title, handler = steps[index]
        render_header(index + 1, title)
        try:
            handler()
            index += 1
        except BackSignal:
            if index == 0:
                warn("Already at the first section")
                time.sleep(1)
            else:
                index -= 1

    extra_words = str(state["extra_packages"]).split()
    runtime_user = str(state["runtime_user"])
    container_home = "/root" if runtime_user == "root" else f"/home/{runtime_user or state['project_name']}"
    state["auth_files"] = gather_agent_auth_files(str(state["project_name"]), container_home)
    all_packages = sort_unique_words((baseline_packages() + " " + " ".join(extra_words)).split())

    return AgentConfig(
        project_name=str(state["project_name"]),
        runtime_class=str(state["runtime_class"]),
        base_image=str(state["base_image"]),
        runtime_user=str(state["runtime_user"]),
        cpu=str(state["cpu"]),
        memory=str(state["memory"]),
        storage=str(state["storage"]),
        agent=str(state["agent"]),
        agent_cmd=str(state["agent_cmd"]),
        agent_args=str(state["agent_args"]),
        all_packages=all_packages,
        install_rustup=True,
        plain_env_vars=list(state["plain_env_vars"]),
        auth_files=list(state["auth_files"]),
        expose_service=bool(state["expose_service"]),
        container_port=str(state["container_port"]),
        node_port=str(state["node_port"]),
    )


def write_project_files(cfg: AgentConfig) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.config_path.write_text(cfg.config_text())
    cfg.yaml_path.write_text(cfg.yaml_text())
    ok(f"Generated {cfg.config_path}")
    ok(f"Generated {cfg.yaml_path}")


def print_summary(cfg: AgentConfig) -> None:
    print()
    print(f"{BOLD}  Summary{RESET}")
    print(f"  {DIM}───────────────────────────────────────{RESET}")
    print(f"  Project   {BOLD}{cfg.project_name}{RESET}")
    print(f"  Runtime   {BOLD}{cfg.runtime_class}{RESET}")
    print(f"  Image     {BOLD}{cfg.base_image}{RESET}")
    print(f"  Resources {BOLD}{cfg.cpu} CPU · {cfg.memory} RAM · {cfg.storage} storage{RESET}")
    if cfg.agent_cmd:
        print(f"  Agent     {BOLD}codex, claude{RESET}")
        print(f"  Daemon    {BOLD}paseo{RESET}")
        print(f"  Auth      {BOLD}{len(cfg.auth_files)} file(s) copied{RESET}")
    print(f"  {DIM}───────────────────────────────────────{RESET}")
    print()


def apply_saved_project(project_name: str) -> None:
    cfg = load_project_config(project_name)
    write_project_files(cfg)
    generation_before = get_deployment_generation(project_name)
    observed_before = get_deployment_generation(project_name, observed=True)
    apply_project_manifest(cfg)
    generation_after = get_deployment_generation(project_name)
    observed_after = get_deployment_generation(project_name, observed=True)
    if generation_after and generation_after != generation_before:
        ok("Pod template changed; waiting for rollout to finish...")
        if observed_after != generation_after:
            hint(f"Deployment generation: {generation_before or 'unknown'} -> {generation_after}")
        pod = wait_for_deployment_ready(project_name)
        ok(f"{pod} is ready.")
        return
    ok("No pod-template change detected; apply completed.")
    if observed_after and observed_after != observed_before:
        hint(f"Deployment controller observed generation {observed_after}.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate k3s Kata agent project config and manifests.")
    parser.add_argument("project", nargs="?", help="Apply a saved project config")
    args = parser.parse_args(argv)

    try:
        if args.project:
            apply_saved_project(args.project)
        else:
            cfg = build_config_interactively()
            write_project_files(cfg)
            print_summary(cfg)
            print("Apply manually when ready:")
            print(f"  kubectl apply -f {cfg.yaml_path}")
        return 0
    except AgentError as exc:
        print(f"{YELLOW}✖{RESET}  {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        stop_log_stream()
        print(f"\n{YELLOW}✖{RESET}  Configuration cancelled.", file=sys.stderr)
        return 130
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
