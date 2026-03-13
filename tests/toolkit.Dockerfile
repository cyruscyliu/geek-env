FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
  bash \
  ca-certificates \
  curl \
  git \
  gnupg \
  sudo \
  unzip \
  xz-utils \
  && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash geek \
  && echo 'geek ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/geek \
  && chmod 0440 /etc/sudoers.d/geek

USER geek
WORKDIR /workspace

ENV HOME=/home/geek
