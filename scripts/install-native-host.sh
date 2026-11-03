#!/usr/bin/env bash
# Install the native-host dependencies for WFS iOS Virtual Lab on Ubuntu 24.04
# (QEMU + AAVMF firmware + SeaBIOS/ramfb + Xvfb/x11vnc/noVNC), and start the
# X/VNC display stack the dashboard expects (Xvfb :99, VNC 5900, noVNC 6080).
#
# Usage: bash scripts/install-native-host.sh   (run from the repo root)
#
# Notes:
# - Requires root (apt + /var/lib/wfs). Packages installed with apt do NOT
#   survive a VM/runtime replacement; re-run this script after one.
# - This only installs and starts the display stack. It does not clone HakiOS,
#   fetch an IPSW, build images, or start the dashboard or a guest session.
# - Idempotent: already-running Xvfb/x11vnc/websockify processes are left alone.
set -euo pipefail
cd "$(dirname "$0")/.."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    qemu-system-arm qemu-efi-aarch64 qemu-utils xvfb x11vnc novnc websockify \
    qemu-system-gui seabios ipxe-qemu
mkdir -p /var/lib/wfs/hakios logs
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
if ! pgrep -f "Xvfb :99" >/dev/null; then
    setsid nohup Xvfb :99 -screen 0 1125x2500x24 -ac -nolisten tcp \
        > logs/xvfb.log 2>&1 < /dev/null &
    sleep 2
fi
if ! pgrep -f "x11vnc -display :99" >/dev/null; then
    setsid nohup x11vnc -display :99 -forever -shared -nopw -localhost \
        -rfbport 5900 -wait 100 -defer 20 > logs/x11vnc.log 2>&1 < /dev/null &
fi
if ! pgrep -f "websockify.*6080" >/dev/null; then
    setsid nohup websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 \
        > logs/novnc.log 2>&1 < /dev/null &
fi
sleep 1
qemu-system-aarch64 --version | head -1
ls -l /usr/share/AAVMF/AAVMF_CODE.fd /usr/share/AAVMF/AAVMF_VARS.fd \
    /usr/share/seabios/vgabios-ramfb.bin
echo "Native host install done. Start the dashboard, then check /api/status (ready:true)."
