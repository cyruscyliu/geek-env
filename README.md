# Agent Vault

Agent Vault is an AI-native environment for isolated coding agents. It runs
agent workloads in VM-backed sandboxes, with
[Headlamp](https://headlamp.dev/) managing k3s pods and
[Paseo](https://github.com/getpaseo/paseo) managing the agent runtime inside
each guest.

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
pyhton3 -m pip install -r requirements.txt
python3 scripts/agentctl.py
```

Apply the generated manifest when ready:

```bash
kubectl apply -f agents/<project>.yaml
```

For tool-specific usage details, see:

- [`README.k3s-kata.md`](README.k3s-kata.md)

If you want to extend the underlying k3s/Kata setup to more hosts, see
[`scripts/setup-k3s-kata-worker.sh`](scripts/setup-k3s-kata-worker.sh).

## Contribute

- update docs when behavior changes
- validate with:

```bash
python3 -m py_compile scripts/agentctl.py
bash -n scripts/setup-k3s-kata.sh
python3 -m unittest tests/test_agentctl_user_story.py
python3 -m unittest tests/test_agentctl_k3s_integration.py
./tests/smoke-agentctl-paseo.sh
```

If you change command flow or generated manifests, update the relevant usage
docs under the README files in the repo root.

## License

MIT. See [`LICENSE`](LICENSE).
