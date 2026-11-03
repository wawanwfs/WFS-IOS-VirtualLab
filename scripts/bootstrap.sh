#!/usr/bin/env bash
set -euo pipefail
cd "${WFS_WORKSPACE:-/workspace}"
if [ ! -d hackios/.git ]; then
  git clone --no-checkout https://github.com/oosexgang/hakios-xnu-kernel.git hackios
  git -C hackios checkout --detach "${WFS_HAKIOS_REV:-88513176b1e96ecf0b764cd62c6f4e6ac71345e3}"
fi
cd hackios
test -f qemu/run-ios.sh || { echo 'Unsupported HakiOS layout: qemu/run-ios.sh missing'; exit 1; }
printf '\nHakiOS sources ready. Next (manual, check rights and disk space):\n'
printf '  docker compose exec wfs-ios-lab bash -lc "cd /workspace/hackios && bash sysimage/fetch.sh"\n'
printf '  docker compose exec wfs-ios-lab bash -lc "cd /workspace/hackios && REST=1 bash userland/build.sh"\n'
