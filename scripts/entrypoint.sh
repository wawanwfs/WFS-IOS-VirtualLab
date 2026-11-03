#!/usr/bin/env bash
set -euo pipefail
mkdir -p /workspace/logs
# Container restarts preserve /tmp, but not the X server process.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb :99 -screen 0 1125x2500x24 -ac -nolisten tcp > /workspace/logs/xvfb.log 2>&1 &
for attempt in {1..100}; do
  if xdpyinfo -display :99 >/dev/null 2>&1; then break; fi
  sleep 0.1
done
xdpyinfo -display :99 >/dev/null 2>&1 || { echo 'Xvfb failed to start'; exit 1; }
# VNC is only used on the container's loopback interface; noVNC proxies it.
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -wait 100 -defer 20 > /workspace/logs/x11vnc.log 2>&1 &
websockify --web /usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 > /workspace/logs/novnc.log 2>&1 &
exec /opt/wfs/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
