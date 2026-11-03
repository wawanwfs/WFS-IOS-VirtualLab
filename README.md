# WFS iOS Virtual Lab — Phase 1 (experimental)

A locally hosted dashboard and containerized research harness for the HakiOS QEMU target. It does NOT contain iOS, Apple's proprietary firmware, an IPSW, or an iPhone simulator compatible with all apps.

## Architecture

Browser → localhost:8000 FastAPI manager → subprocess (HakiOS qemu/run-ios.sh 1200 -display gtk) → QEMU ARM64 → virtual X11 display (:99)
Browser → localhost:6080 noVNC → websockify → x11vnc → virtual X11 display (:99)
Persistent host `workspace/` → cloned source, APFS system images, logs.
Docker volume `qemu-runtime` → Linux runtime copies and sparse guest RAM. The first session stages the required files; later sessions reuse unchanged copies. Guest RAM stays on the Linux filesystem rather than the Windows bind mount.

An optional local `.env` can set `WFS_SYSTEM_IMAGE` to an alternate image path inside the container and `QEMU_RAM_GB` to the guest RAM size. The default image remains `workspace/hackios/userland/system.apfs`; `.env.example` shows the defaults. An alternate image is checked before starting and staged into the Linux runtime without replacing the original image.

**Security model:** local trusted single-user workstation. Local-only bound TCP ports; VNC within container is unauthenticated. Do not publish ports over the internet, and do not use the lab with sensitive accounts/data. Do not mount Docker socket or run privileged. This design is not hardened for multi-user hosting.

## Requirements

- Linux x86_64 with Docker Engine + Docker Compose v2, or Windows 11 with WSL2 and Docker Desktop Linux containers.
- Recommended >= 16 GB RAM and >= 30 GB free disk; HakiOS upstream minimum is lower.
- Internet for initial source and IPSW retrieval, with any appropriate rights and license review.
- Host CPU x86_64 works by **emulation** rather than ARM KVM acceleration; boot can be slow.

## Run Phase 1

```bash
docker compose up -d --build
# Dashboard http://localhost:8000
# QEMU display: http://localhost:6080/vnc.html
```

The initial dashboard works without an iOS image, and clearly reports missing dependencies.
The generic Compose profile assigns one emulated CPU and defaults to a 3600-second session. `WFS_QEMU_CPUS` and `WFS_QEMU_BOOT_ARGS` can override the guest CPU count and additional kernel arguments. On this 4-core/8-thread workstation, the local `.env` selects 8 guest CPUs and `tlto_us=30000000 slto_us=30000000`: XNU's ticket/spinlock timeouts are extended to 30 seconds to accommodate software emulation. The unmodified four-CPU profile previously panicked. The eight-CPU preflight passed init, service and surface checks; full interface validation is recorded in `docs/VALIDATION.md`. CPU emulation remains slow; use the duration control to choose 60 to 3600 seconds.

The display shows a crosshair cursor. Click to touch; drag up from the bottom edge for Home, and use L to lock/wake. Hover movements stay local, drag updates are limited to 10 per second, and leaving the browser releases a held pointer button. Reload the dashboard with Ctrl+F5 after updating the display code.

## Prepare HakiOS

Bootstrap pins new installations to source commit `88513176b1e96ecf0b764cd62c6f4e6ac71345e3`, matching the launcher layout used here. Existing checkouts are preserved. `WFS_HAKIOS_REV` can override the revision for a new installation after compatibility review.

```bash
docker compose exec wfs-ios-lab bash /opt/wfs/scripts/bootstrap.sh
# inspect HakiOS source and legal terms before fetching an IPSW
docker compose exec wfs-ios-lab bash -lc 'cd /workspace/hackios && bash sysimage/fetch.sh'
docker compose exec wfs-ios-lab bash -lc 'cd /workspace/hackios && REST=1 bash userland/build.sh'
```

Then open the dashboard, set session duration, and click **Start session**. Standard HakiOS command documented upstream:

```bash
cd /workspace/hackios
bash qemu/run-ios.sh 1200 -display gtk
```

The manager supports the installed HakiOS `qemu/run-ios.sh` layout and Ubuntu AAVMF firmware paths. It passes the duration as a positional argument and enables GTK on DISPLAY=:99. The API enforces a wall-clock limit of the requested duration plus 40 seconds for loader shutdown.

## API

- `GET /api/status` — VM status / installation checks
- `POST /api/start` — `{"seconds":1200}` (single instance)
- `POST /api/stop` — stop spawned process group
- `GET /api/logs` — tail of the latest session log

## Limitations, safety and scope

- This workstation has reached the real SpringBoard Home Screen and opened Settings with the uncompressed-cache image. The one-CPU boot took about 38 minutes, and input/app startup remain very slow. See `docs/VALIDATION.md` for measured results.
- No Apple Account, App Store downloads, cellular or general IPA support promised.
- Do not distribute Apple IPSW extracts, userland images, or files without appropriate rights. Read Apple's terms.
- VNC server has no auth and is only accessed via localhost-published web UI. If others share your machine, use OS security isolation.
- No automatically downloaded iOS system image; user explicitly controls downloading/processing.
- The `seconds` input is passed to the launcher as a positional argument (60 to 3600 seconds).
- Runtime state lives in the API process; it does not reattach to already-running QEMU processes after service restarts.

## Phase 2 planning

1. Pin and verify upstream commits/checksums; verify command compatibility with integration tests.
2. Split API, VM worker, and WebSocket proxy; add process supervision and persistent state.
3. Move from Xvfb desktop capture to QEMU native VNC or SPICE, implement deterministic input and screenshot APIs.
4. Add per-VM writable overlays, snapshots, quota and bounded resource allocations.
5. Add authentication, RBAC, auditing, and remote access only through an authenticated TLS gateway.
6. Validate iOS app compatibility and publish an honest per-app compatibility matrix.

## Sources

- https://github.com/oosexgang/hakios-xnu-kernel
- https://packages.ubuntu.com/noble/all/seabios/filelist


## Fix: `exec: uvicorn: not found`

The project now installs FastAPI and Uvicorn in `/opt/wfs/.venv` and invokes it through that environment's Python. Rebuild after replacing the project files:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose logs -f --tail=80 wfs-ios-lab
```

Check `http://localhost:8000/api/status`. Running Docker does not establish that HakiOS boots successfully; HakiOS prerequisites remain separate.

## Regression tests

Run in Linux with the development dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests use a temporary workspace and fake launcher. Real boot results are recorded separately in `docs/VALIDATION.md`.
