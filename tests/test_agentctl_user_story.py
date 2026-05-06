#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.agentctl import (
    AgentConfig,
    AgentAuthFile,
    InvalidTransitionError,
    PlainEnvVar,
    agent_label_for_cmd,
    build_paseo_bootstrap_line,
    gather_agent_auth_files,
    is_valid_project_name,
    kubectl_exec_args_for_terminal,
    sanitize_codex_config_toml,
    restore_files,
    snapshot_files,
    transition_public_state,
)


class UserStoryGraphTest(unittest.TestCase):
    PROJECT = "fight-cuttlefish-x64"
    WORKSPACE = f"/home/debian/Projects/{PROJECT}"
    MOUNT_PATH = f"/home/{PROJECT}"

    def make_config(self, **overrides: Any) -> AgentConfig:
        defaults: dict[str, Any] = {
            "project_name": self.PROJECT,
            "host_path": self.WORKSPACE,
            "mount_path": self.MOUNT_PATH,
            "runtime_class": "kata-qemu",
            "base_image": "debian:trixie-slim",
            "cpu": "2",
            "memory": "4Gi",
            "storage": "20Gi",
            "agent": "None",
            "agent_cmd": "",
            "agent_args": "",
            "persist_state": False,
            "all_packages": "",
            "bootstrap_profile": "full",
            "install_rustup": False,
            "plain_env_vars": [],
            "auth_files": [],
            "expose_service": False,
            "container_port": "",
            "node_port": "",
        }
        defaults.update(overrides)
        return AgentConfig(**defaults)

    def make_agent_config(self, **overrides: Any) -> AgentConfig:
        return self.make_config(
            agent=agent_label_for_cmd("multi"),
            agent_cmd="multi",
            **overrides,
        )

    def test_config_edges(self) -> None:
        for state in ("none", "saved", "ready", "failed"):
            with self.subTest(state=state):
                self.assertEqual(transition_public_state(state, "config"), "saved")

    def test_apply_edges(self) -> None:
        for state in ("saved", "ready", "failed"):
            with self.subTest(state=state):
                self.assertEqual(transition_public_state(state, "apply"), "starting")

    def test_system_edges(self) -> None:
        self.assertEqual(transition_public_state("starting", event="pod_ready"), "ready")
        self.assertEqual(transition_public_state("starting", event="failure"), "failed")

    def test_exec_edge(self) -> None:
        self.assertEqual(transition_public_state("ready", "exec"), "ready")

    def test_status_edges(self) -> None:
        for state in ("none", "saved", "starting", "ready", "failed"):
            with self.subTest(state=state):
                self.assertEqual(transition_public_state(state, "status"), state)

    def test_delete_edges(self) -> None:
        for state in ("saved", "starting", "ready", "failed"):
            with self.subTest(state=state):
                self.assertEqual(transition_public_state(state, "delete"), "none")

    def test_rejects_invalid_user_edges(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("none", "apply")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("saved", "exec")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("starting", "exec")

    def test_rejects_invalid_system_edges(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("ready", event="pod_ready")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("failed", event="failure")

    def test_requires_exactly_one_transition_input(self) -> None:
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("saved")
        with self.assertRaises(InvalidTransitionError):
            transition_public_state("starting", "status", event="failure")

    def test_file_snapshot_restore_rolls_back_new_and_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir) / "existing.txt"
            new_file = Path(tmpdir) / "new.yaml"
            existing.write_text("before\n")

            snapshots = snapshot_files([existing, new_file])

            existing.write_text("after\n")
            new_file.write_text("created\n")

            restore_files(snapshots)

            self.assertEqual(existing.read_text(), "before\n")
            self.assertFalse(new_file.exists())

    def test_project_name_validation_matches_user_group_constraints(self) -> None:
        valid = ("morpheus", "morpheus2", "morpheus-dev", "a", "a1")
        invalid = ("", "2morpheus", "-morpheus", "morpheus-", "Morph", "morpheus_dev", "m" * 33)
        for name in valid:
            with self.subTest(name=name):
                self.assertTrue(is_valid_project_name(name))
        for name in invalid:
            with self.subTest(name=name):
                self.assertFalse(is_valid_project_name(name))

    def test_sanitize_codex_config_removes_trusted_projects(self) -> None:
        source = """model_provider = "openai"
[projects."/home/debian/Projects/foo"]
trust_level = "trusted"

[projects."/tmp"]
trust_level = "trusted"

[tui.model_availability_nux]
"gpt-5.5" = 4
"""
        rendered = sanitize_codex_config_toml(source)
        self.assertIn('model_provider = "openai"', rendered)
        self.assertIn("[tui.model_availability_nux]", rendered)
        self.assertNotIn('[projects."/home/debian/Projects/foo"]', rendered)
        self.assertNotIn('trust_level = "trusted"', rendered)

    def test_agent_config_round_trip(self) -> None:
        cfg = self.make_agent_config(
            cpu="12",
            memory="12Gi",
            storage="80Gi",
            persist_state=True,
            all_packages="bat bubblewrap curl git nodejs npm python3 ripgrep sudo wget",
            plain_env_vars=[PlainEnvVar("FOO", "bar")],
            auth_files=[
                AgentAuthFile(
                    key="codex-auth.json",
                    mount_path=f"/home/{self.PROJECT}/.codex/auth.json",
                    content='{"auth_mode":"chatgpt"}',
                )
            ],
            expose_service=True,
            container_port="8080",
            node_port="30800",
        )

        loaded = AgentConfig.from_config_dict(cfg.to_config_dict())

        for field_name in (
            "project_name",
            "host_path",
            "mount_path",
            "runtime_class",
            "base_image",
            "cpu",
            "memory",
            "storage",
            "agent_cmd",
            "agent_args",
            "persist_state",
            "bootstrap_profile",
            "all_packages",
            "container_port",
            "node_port",
        ):
            with self.subTest(field=field_name):
                self.assertEqual(getattr(loaded, field_name), getattr(cfg, field_name))
        self.assertEqual(loaded.plain_env_vars[0].name, "FOO")
        self.assertEqual(loaded.auth_files[0].key, "codex-auth.json")
        self.assertTrue(loaded.expose_service)

    def test_auth_files_are_copied_in_bootstrap_not_k8s_secret(self) -> None:
        cfg = self.make_agent_config(
            auth_files=[
                AgentAuthFile(
                    key="codex-auth.json",
                    mount_path=f"/home/{self.PROJECT}/.codex/auth.json",
                    content='{"auth_mode":"chatgpt"}',
                ),
                AgentAuthFile(
                    key="claude-settings.json",
                    mount_path=f"/home/{self.PROJECT}/.claude/settings.json",
                    content='{"token":"abc"}',
                ),
            ]
        )

        rendered = cfg.yaml_text()

        self.assertNotIn("kind: Secret", rendered)
        self.assertNotIn("secretName:", rendered)
        self.assertNotIn("name: agent-auth", rendered)
        self.assertIn("path.write_bytes(base64.b64decode", rendered)
        self.assertIn(f"/home/{self.PROJECT}/.codex/auth.json", rendered)
        self.assertIn(f"/home/{self.PROJECT}/.claude/settings.json", rendered)

    def test_persisted_codex_state_uses_project_pvc_not_host_home(self) -> None:
        cfg = self.make_agent_config(persist_state=True)

        rendered = cfg.yaml_text()

        self.assertIn(f"mountPath: /home/{self.PROJECT}/.paseo", rendered)
        self.assertIn(f"claimName: {cfg.project_pvc_name}", rendered)
        self.assertIn("subPath: .paseo", rendered)
        self.assertNotIn("hostPath:", rendered)

    def test_persisted_codex_state_mounts_project_subpath_when_workspace_differs(self) -> None:
        cfg = self.make_agent_config(
            persist_state=True,
            mount_path="/workspace",
        )

        rendered = cfg.yaml_text()

        self.assertIn("        - name: codex-home", rendered)
        self.assertIn(f"mountPath: /home/{self.PROJECT}/.codex", rendered)
        self.assertIn("subPath: .codex", rendered)
        self.assertIn(f"claimName: {cfg.project_pvc_name}", rendered)

    def test_paseo_home_is_rendered_as_env_not_volume_mount(self) -> None:
        cfg = self.make_agent_config(
            plain_env_vars=[PlainEnvVar("FOO", "bar")],
        )

        rendered = cfg.yaml_text()
        volume_mounts_section = rendered.split("        volumeMounts:\n", 1)[1].split("        env:\n", 1)[0]

        self.assertIn("        env:\n", rendered)
        self.assertIn('        - name: PASEO_HOME\n          value: "/home/fight-cuttlefish-x64/.paseo"', rendered)
        self.assertNotIn("PASEO_HOME", volume_mounts_section)

    def test_claude_config_is_loaded(self) -> None:
        loaded = AgentConfig.from_config_dict(
            {
                "project": self.PROJECT,
                "workspace": {
                    "host_path": self.WORKSPACE,
                    "mount_path": self.MOUNT_PATH,
                },
                "runtime": {
                    "class": "kata-qemu",
                    "base_image": "debian:trixie-slim",
                },
                "resources": {
                    "cpu": "2",
                    "memory": "4Gi",
                    "ephemeral_storage": "20Gi",
                },
                "agent": {
                    "kind": "multi",
                    "label": "Codex + Claude Code",
                    "permissive": False,
                    "args": [],
                    "persist_state": True,
                },
                "tooling": {
                    "bootstrap_profile": "full",
                    "apt_packages": [],
                    "install_rustup": False,
                },
                "auth": {
                    "files": [
                        {
                            "key": "claude-settings.json",
                            "mount_path": f"/home/{self.PROJECT}/.claude/settings.json",
                            "content": "{}",
                        }
                    ]
                },
            }
        )

        self.assertEqual(loaded.agent_cmd, "multi")
        self.assertEqual(loaded.agent, "Codex + Claude Code")
        self.assertEqual(loaded.auth_files[0].key, "claude-settings.json")

    def test_gather_agent_auth_files_reads_repo_local_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets_dir = Path(tmpdir) / "agentctl"
            (secrets_dir / "codex").mkdir(parents=True)
            (secrets_dir / "claude").mkdir(parents=True)
            (secrets_dir / "codex" / "auth.json").write_text('{"auth_mode":"chatgpt"}')
            (secrets_dir / "codex" / "config.toml").write_text(
                'model_provider = "openai"\n'
                '[projects."/tmp/foo"]\n'
                'trust_level = "trusted"\n'
            )
            (secrets_dir / "claude" / "settings.json").write_text('{"token":"abc"}')

            with patch("scripts.agentctl.SECRETS_DIR", secrets_dir):
                auth_files = gather_agent_auth_files(self.PROJECT)

        self.assertEqual([item.key for item in auth_files], ["codex-auth.json", "codex-config.toml", "claude-settings.json"])
        self.assertEqual(auth_files[0].mount_path, f"/home/{self.PROJECT}/.codex/auth.json")
        self.assertNotIn('trust_level = "trusted"', auth_files[1].content)

    def test_minimal_bootstrap_keeps_sudo_passwordless(self) -> None:
        cfg = self.make_config(
            host_path="/tmp/sudo-passwordless",
            bootstrap_profile="minimal",
        )

        rendered = cfg.build_container_bootstrap_lines()
        self.assertIn("NOPASSWD: ALL", rendered)

    def test_paseo_bootstrap_is_enabled_for_agents(self) -> None:
        rendered = build_paseo_bootstrap_line("multi", self.PROJECT, f"/home/{self.PROJECT}")
        self.assertIn("paseo daemon start", rendered)
        self.assertIn("paseo daemon pair --json", rendered)

    def test_container_identity_uses_project_name(self) -> None:
        cfg = self.make_agent_config()
        rendered = cfg.build_container_bootstrap_lines()
        self.assertEqual(cfg.container_user, self.PROJECT)
        self.assertEqual(cfg.container_home, f"/home/{self.PROJECT}")
        self.assertIn(f"useradd -m -s /bin/bash {self.PROJECT}", rendered)
        self.assertIn(f"{self.PROJECT} ALL=(ALL) NOPASSWD: ALL", rendered)

    def test_full_bootstrap_does_not_include_shell_editor_mux_setup(self) -> None:
        cfg = self.make_agent_config(
            host_path="/tmp/sudo-passwordless",
            cpu="1",
            memory="2Gi",
            storage="10Gi",
            all_packages="python3",
        )

        rendered = cfg.build_container_bootstrap_lines()
        for legacy_marker in ("setup-zsh.sh", "setup-nvim.sh", "setup-tmux.sh", "usermod -s"):
            with self.subTest(marker=legacy_marker):
                self.assertNotIn(legacy_marker, rendered)

    def test_kubectl_exec_uses_tty_only_when_terminal_is_available(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            self.assertEqual(kubectl_exec_args_for_terminal(), ["-it"])

        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=False):
            self.assertEqual(kubectl_exec_args_for_terminal(), ["-i"])

        with patch("sys.stdin.isatty", return_value=False), patch("sys.stdout.isatty", return_value=False):
            self.assertEqual(kubectl_exec_args_for_terminal(), [])


if __name__ == "__main__":
    unittest.main()
