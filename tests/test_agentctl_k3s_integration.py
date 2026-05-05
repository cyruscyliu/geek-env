#!/usr/bin/env python3

import contextlib
import io
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from scripts import agentctl
from scripts.agentctl import AgentConfig, AgentError, PlainEnvVar, load_project_config


def kubectl_available() -> bool:
    return shutil.which("kubectl") is not None


def kata_runtime_available() -> bool:
    if not kubectl_available():
        return False
    result = agentctl.kubectl(["get", "runtimeclass", "kata-qemu"], check=False)
    return result.returncode == 0


@unittest.skipUnless(kubectl_available(), "kubectl is required for live k3s integration tests")
@unittest.skipUnless(kata_runtime_available(), "kata-qemu runtimeclass is required for live k3s integration tests")
class AgentCtlK3sIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="agentctl-k3s-")
        self.addCleanup(self.tempdir.cleanup)

        self.workspace = Path(self.tempdir.name) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.original_output_dir = agentctl.OUTPUT_DIR
        self.output_dir = Path(self.tempdir.name) / "agents"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        agentctl.OUTPUT_DIR = self.output_dir

        self.project_name = f"itest-{time.time_ns()}"

    def tearDown(self) -> None:
        try:
            agentctl.kubectl(["delete", "namespace", self.project_name, "--ignore-not-found=true", "--wait=false"], check=False)
        finally:
            agentctl.OUTPUT_DIR = self.original_output_dir

    def write_and_load_config(self, cfg: AgentConfig) -> AgentConfig:
        agentctl.write_project_files(cfg)
        self.assertTrue(cfg.config_path.exists())
        self.assertTrue(cfg.yaml_path.exists())
        return load_project_config(self.project_name)

    def wait_until_ready(self, cfg: AgentConfig, timeout_seconds: int = 180) -> str:
        agentctl.apply_project_manifest(cfg)
        agentctl.wait_for_pod_running(self.project_name, timeout_seconds=timeout_seconds)
        return agentctl.wait_for_deployment_ready(self.project_name, timeout_seconds=timeout_seconds)

    def make_config(self, **overrides: object) -> AgentConfig:
        defaults: dict[str, object] = {
            "project_name": self.project_name,
            "host_path": str(self.workspace),
            "mount_path": "/workspace",
            "runtime_class": "kata-qemu",
            "base_image": "debian:trixie-slim",
            "cpu": "1",
            "memory": "2Gi",
            "storage": "10Gi",
            "agent": "None",
            "agent_cmd": "",
            "permissive_mode": "",
            "agent_args": "",
            "all_packages": "",
            "persist_state": False,
            "bootstrap_profile": "minimal",
            "plain_env_vars": [PlainEnvVar("SMOKE_FLAG", "1")],
        }
        defaults.update(overrides)
        return AgentConfig(**defaults)

    def wait_for_namespace_gone(self, timeout_seconds: int = 60) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            result = agentctl.kubectl(["get", "namespace", self.project_name], check=False)
            if result.returncode != 0:
                return
            time.sleep(1)
        self.fail(f"Namespace {self.project_name} still exists after {timeout_seconds}s")

    def test_graph_none_saved_starting_ready_delete_none(self) -> None:
        cfg = self.make_config()

        loaded = self.write_and_load_config(cfg)
        self.assertEqual(loaded.project_name, cfg.project_name)
        self.assertEqual(loaded.bootstrap_profile, "minimal")
        self.assertFalse(loaded.persist_state)

        ready_pod = self.wait_until_ready(cfg)
        self.assertTrue(ready_pod.startswith("pod/"))

        result = agentctl.kubectl(
            ["get", "deployment", self.project_name, "-o", "jsonpath={.status.readyReplicas}"],
            namespace=self.project_name,
        )
        self.assertEqual((result.stdout or "").strip(), "1")

        delete = agentctl.kubectl(["delete", "namespace", self.project_name, "--wait=false"], check=False)
        self.assertEqual(delete.returncode, 0)
        self.wait_for_namespace_gone()

    def test_graph_ready_config_saved_apply_starting_ready(self) -> None:
        cfg = self.make_config()
        self.write_and_load_config(cfg)
        self.wait_until_ready(cfg)

        updated = self.make_config(plain_env_vars=[PlainEnvVar("SMOKE_FLAG", "2")])
        loaded = self.write_and_load_config(updated)
        self.assertEqual(loaded.plain_env_vars[0].value, "2")

        self.wait_until_ready(updated)

        result = agentctl.kubectl(
            ["get", "deployment", self.project_name, "-o", "jsonpath={.spec.template.spec.containers[0].env[0].value}"],
            namespace=self.project_name,
        )
        self.assertEqual((result.stdout or "").strip(), "2")

    def test_graph_starting_failed_delete_none(self) -> None:
        cfg = self.make_config(cpu="999")
        self.write_and_load_config(cfg)

        render_only = io.StringIO()
        with contextlib.redirect_stdout(render_only):
            agentctl.render_project_manifest(cfg)

        apply = agentctl.kubectl(["apply", "-f", str(cfg.yaml_path)], check=False)
        self.assertEqual(apply.returncode, 0, apply.stderr)

        with self.assertRaises(AgentError):
            quiet = io.StringIO()
            with contextlib.redirect_stdout(quiet):
                agentctl.wait_for_deployment_ready(self.project_name, timeout_seconds=20)

        pod_listing = agentctl.kubectl(["get", "pods", "-o", "jsonpath={.items[0].status.phase}"], namespace=self.project_name, check=False)
        self.assertIn((pod_listing.stdout or "").strip(), {"Pending", ""})

        delete = agentctl.kubectl(["delete", "namespace", self.project_name, "--wait=false"], check=False)
        self.assertEqual(delete.returncode, 0)
        self.wait_for_namespace_gone()


if __name__ == "__main__":
    unittest.main()
