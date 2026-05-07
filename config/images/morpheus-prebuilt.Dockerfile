FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/opt/agent-cli/bin:/root/.cargo/bin:${PATH}

ARG PASEO_VERSION=0.1.70-beta.1
ARG PASEO_DEB_URL=https://github.com/getpaseo/paseo/releases/download/v0.1.70-beta.1/Paseo-0.1.70-beta.1-amd64.deb

RUN apt-get update && apt-get install -y \
  openssh-client \
  bash \
  bat \
  bubblewrap \
  build-essential \
  ca-certificates \
  curl \
  fd-find \
  git \
  jq \
  libasound2t64 \
  nodejs \
  npm \
  python3 \
  python3-pip \
  ripgrep \
  sudo \
  wget \
  xdg-utils \
  && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

RUN curl -fsSL "${PASEO_DEB_URL}" -o /tmp/paseo.deb \
  && apt-get update \
  && apt-get install -y /tmp/paseo.deb \
  && rm -f /tmp/paseo.deb \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/agent-cli \
  && npm install -g --prefix /opt/agent-cli \
    @openai/codex \
    @anthropic-ai/claude-code \
    pnpm

RUN ln -sf /opt/Paseo/resources/bin/paseo /usr/local/bin/paseo \
  && printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'exec /opt/agent-cli/bin/codex "$@"' > /usr/local/bin/codex \
  && chmod 755 /usr/local/bin/codex \
  && printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' 'exec /opt/agent-cli/bin/claude "$@"' > /usr/local/bin/claude \
  && chmod 755 /usr/local/bin/claude
