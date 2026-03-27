#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path

from scripts.agentctl import (
    AgentConfig,
    FileSnapshot,
    InvalidTransitionError,
    PlainEnvVar,
    SecretEnvVar,
    restore_files,
    snapshot_files,
    transition_public_state,
)


class UserStoryGraphTest(unittest.TestCase):
    def test_config_edges(self) -> None:
        self.assertEqual(transition_public_state("none", "config"), "saved")
        self.assertEqual(transition_public_state("saved", "config"), "saved")
        self.assertEqual(transition_public_state("ready", "config"), "saved")
        self.assertEqual(transition_public_state("failed", "config"), "saved")

    def test_apply_edges(self) -> None:
        self.assertEqual(transition_public_state("saved", "apply"), "starting")
        self.assertEqual(transition_public_state("ready", "apply"), "starting")
        self.assertEqual(transition_public_state("failed", "apply"), "starting")

    def test_system_edges(self) -> None:
        self.assertEqual(transition_public_state("starting", event="pod_ready"), "ready")
        self.assertEqual(transition_public_state("starting", event="failure"), "failed")

    def test_exec_edge(self) -> None:
        self.assertEqual(transition_public_state("ready", "exec"), "ready")

    def test_status_edges(self) -> None:
        self.assertEqual(transition_public_state("none", "status"), "none")
        self.assertEqual(transition_public_state("saved", "status"), "saved")
        self.assertEqual(transition_public_state("starting", "status"), "starting")
        self.assertEqual(transition_public_state("ready", "status"), "ready")
        self.assertEqual(transition_public_state("failed", "status"), "failed")

    def test_delete_edges(self) -> None:
        self.assertEqual(transition_public_state("saved", "delete"), "none")
        self.assertEqual(transition_public_state("starting", "delete"), "none")
        self.assertEqual(transition_public_state("ready", "delete"), "none")
        self.assertEqual(transition_public_state("failed", "delete"), "none")

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

    def test_agent_config_round_trip(self) -> None:
        cfg = AgentConfig(
            project_name="fight-cuttlefish-x64",
            host_path="/home/debian/Projects/fight-cuttlefish-x64",
            mount_path="/home/agent/work",
            runtime_class="kata-qemu",
            base_image="debian:trixie-slim",
            cpu="12",
            memory="12Gi",
            storage="80Gi",
            agent="OpenAI Codex",
            agent_cmd="codex",
            permissive_mode="true",
            agent_args="--dangerously-bypass-approvals-and-sandbox",
            persist_state=True,
            all_packages="bat bubblewrap curl git nodejs npm python3 ripgrep sudo tmux wget",
            bootstrap_profile="full",
            install_rustup=False,
            plain_env_vars=[PlainEnvVar("FOO", "bar")],
            secret_env_vars=[SecretEnvVar("OPENAI_API_KEY", "secret")],
            expose_service=True,
            container_port="8080",
            node_port="30800",
            agent_secret_name="fight-cuttlefish-x64-codex-auth",
            agent_secret_key="auth.json",
            agent_secret_mount_path="/home/agent/.codex/auth.json",
            agent_secret_content='{"auth_mode":"chatgpt"}',
        )

        loaded = AgentConfig.from_config_dict(cfg.to_config_dict())

        self.assertEqual(loaded.project_name, cfg.project_name)
        self.assertEqual(loaded.host_path, cfg.host_path)
        self.assertEqual(loaded.mount_path, cfg.mount_path)
        self.assertEqual(loaded.runtime_class, cfg.runtime_class)
        self.assertEqual(loaded.base_image, cfg.base_image)
        self.assertEqual(loaded.cpu, cfg.cpu)
        self.assertEqual(loaded.memory, cfg.memory)
        self.assertEqual(loaded.storage, cfg.storage)
        self.assertEqual(loaded.agent_cmd, cfg.agent_cmd)
        self.assertEqual(loaded.agent_args, cfg.agent_args)
        self.assertEqual(loaded.persist_state, cfg.persist_state)
        self.assertEqual(loaded.bootstrap_profile, cfg.bootstrap_profile)
        self.assertEqual(loaded.all_packages, cfg.all_packages)
        self.assertEqual(loaded.plain_env_vars[0].name, "FOO")
        self.assertEqual(loaded.secret_env_vars[0].name, "OPENAI_API_KEY")
        self.assertTrue(loaded.expose_service)
        self.assertEqual(loaded.container_port, "8080")
        self.assertEqual(loaded.node_port, "30800")

    def test_persisted_codex_state_uses_shared_home_directory(self) -> None:
        cfg = AgentConfig(
            project_name="fight-cuttlefish-x64",
            host_path="/home/debian/Projects/fight-cuttlefish-x64",
            mount_path="/home/agent/work",
            runtime_class="kata-qemu",
            base_image="debian:trixie-slim",
            cpu="2",
            memory="4Gi",
            storage="20Gi",
            agent="OpenAI Codex",
            agent_cmd="codex",
            permissive_mode="true",
            agent_args="",
            persist_state=True,
            all_packages="",
        )

        rendered = cfg.yaml_text()

        self.assertIn(f"          path: {Path.home() / '.codex'}", rendered)
        self.assertNotIn("/home/agent/.claude", rendered)

    def test_legacy_claude_config_is_loaded_as_none(self) -> None:
        loaded = AgentConfig.from_config_dict(
            {
                "project": "fight-cuttlefish-x64",
                "workspace": {
                    "host_path": "/home/debian/Projects/fight-cuttlefish-x64",
                    "mount_path": "/home/agent/work",
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
                    "kind": "claude",
                    "label": "Claude Code (Anthropic)",
                    "permissive": True,
                    "args": ["--dangerously-skip-permissions"],
                    "persist_state": True,
                },
                "tooling": {
                    "bootstrap_profile": "full",
                    "apt_packages": [],
                    "install_rustup": False,
                },
            }
        )

        self.assertEqual(loaded.agent_cmd, "")
        self.assertEqual(loaded.agent, "None")


if __name__ == "__main__":
    unittest.main()
