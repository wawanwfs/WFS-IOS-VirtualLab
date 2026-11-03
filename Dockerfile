FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 DISPLAY=:99
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libc6-dev \
    linux-libc-dev \
    python3 python3-pip python3-venv git curl ca-certificates  qemu-system-arm qemu-efi-aarch64 qemu-utils xvfb x11vnc novnc websockify \
    7zip lz4 liblz4-dev gcc make xauth x11-utils procps && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    qemu-system-gui seabios ipxe-qemu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
# Isolate Python dependencies from Ubuntu's externally-managed system Python.
RUN python3 -m venv /opt/wfs/.venv \
    && /opt/wfs/.venv/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/wfs/.venv/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /opt/wfs
COPY app /opt/wfs/app
RUN cat /opt/wfs/app/static/vnc-cursor.css >> /usr/share/novnc/app/styles/base.css
COPY scripts /opt/wfs/scripts
RUN sed -i 's/\r$//' /opt/wfs/scripts/*.sh && chmod +x /opt/wfs/scripts/*.sh && mkdir -p /workspace \
    && python3 /opt/wfs/scripts/configure-novnc.py
EXPOSE 8000 6080
CMD ["/opt/wfs/scripts/entrypoint.sh"]
