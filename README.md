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
![UI](https://img.shields.io/badge/ui-Headlamp-2563eb)
![Manager](https://img.shields.io/badge/manager-Paseo-15803d)
![License](https://img.shields.io/badge/license-MIT-black)

## Quick Start

```bash
grep -c vmx /proc/cpuinfo
sudo bash scripts/setup-k3s-kata.sh
pyhton3 -m pip install -r requirements.txt
python3 scripts/agentctl.py
```

For tool-specific usage details, see:

- [`README.k3s-kata.md`](README.k3s-kata.md)

If you want to extend the underlying k3s/Kata setup to more hosts, see
[`scripts/setup-k3s-kata-worker.sh`](scripts/setup-k3s-kata-worker.sh).

## TODO

- add a custom base image workflow for agent pods so system packages and other
  image-level changes persist across pod restarts instead of being reinstalled
  at bootstrap time

## Pitfalls

- do not rely on ad hoc `apt-get install` inside a running agent container for
  persistent tooling; only the project home on the PVC persists, while `/usr`,
  `/etc`, and the package database are recreated from the base image on restart
- do not build with `make -j$(nproc)` inside Kata guests for heavy workloads
  such as Buildroot; `$(nproc)` reflects visible CPUs, but max parallelism can
  overdrive the guest VM and trigger Kata agent timeouts or sandbox restarts.
  Prefer a conservative value such as `-j2` or `-j4` unless you have verified
  the workload is stable with more parallelism

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

[`MIT LICENSE`](LICENSE).
