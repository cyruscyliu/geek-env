# Agent Vault

Agent Vault is an AI-native environment for isolated coding agents. It runs
agent workloads in VM-backed sandboxes, with
[Paseo](https://github.com/getpaseo/paseo) managing the runtime inside each
guest.

![Platform](https://img.shields.io/badge/platform-k3s-blue)
![Isolation](https://img.shields.io/badge/isolation-Kata%20Containers-6f42c1)
![Agent](https://img.shields.io/badge/agent-Codex-0a7ea4)
![Agent](https://img.shields.io/badge/agent-Claude%20Code-d97706)
![Manager](https://img.shields.io/badge/manager-Paseo-15803d)
![License](https://img.shields.io/badge/license-MIT-black)

## Quick Start

```bash
grep -c vmx /proc/cpuinfo
sudo bash scripts/setup-k3s-kata.sh
python3 scripts/agentctl.py
```

To re-enter or manage a vault later:

```bash
python3 scripts/agentctl.py <project>
```

For tool-specific usage details, see:

- [`README.k3s-kata.md`](README.k3s-kata.md)

If you want to extend the underlying k3s/Kata setup to more hosts, see
[`scripts/setup-k3s-kata-worker.sh`](scripts/setup-k3s-kata-worker.sh).

## Notes

- `scripts/agentctl.py` stores each vault as a canonical
  `agents/<project>.agent.yaml` config and renders `agents/<project>.yaml`
  from it when applying or rebuilding.
- Agent vaults can now bootstrap either `codex` or `claude`, copy host auth
  into the Kata guest, auto-start a `paseo` daemon, and print pairing info
  during attach.
- Memory and storage limits use Kubernetes-style binary units such as `Gi` or
  `Mi`. Bare values entered in the wizard are normalized to `Gi`.

## Contribute

- update docs when behavior changes
- validate with:

```bash
python3 -m py_compile scripts/agentctl.py
bash -n scripts/setup-k3s-kata.sh
python3 -m unittest tests/test_agentctl_user_story.py
python3 -m unittest tests/test_agentctl_k3s_integration.py
./tests/smoke-agentctl.sh
./tests/smoke-agentctl-paseo.sh
./tests/smoke-test.sh
```

If you change command flow or generated manifests, update the relevant usage
docs under the README files in the repo root.

## License

MIT. See [`LICENSE`](LICENSE).
