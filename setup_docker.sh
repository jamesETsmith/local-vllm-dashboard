#!/usr/bin/env bash
set -euo pipefail

if [[ ! -r /etc/os-release ]]; then
  printf 'Cannot identify this operating system.\n' >&2
  exit 1
fi

. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  printf 'This installer supports Ubuntu only, found %s.\n' "${ID:-unknown}" >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  printf 'sudo is required to install system packages.\n' >&2
  exit 1
fi

sudo apt update
sudo apt install -y docker.io docker-compose-v2

if ! getent group docker >/dev/null; then
  sudo groupadd docker
fi

if ! id -nG "$USER" | tr ' ' '\n' | grep -qx docker; then
  sudo usermod -aG docker "$USER"
fi

printf '\nDocker packages are installed. Log out and back in, then run:\n'
printf '  docker version\n'
printf '  docker compose version\n'
printf '  docker run --rm hello-world\n'
