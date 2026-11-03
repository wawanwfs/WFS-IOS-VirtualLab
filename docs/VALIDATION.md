# Validation — 31 October 2026 (Asia/Jakarta)

The dashboard and session manager run locally through Docker Compose. Full iOS interface validation is recorded below separately from service readiness.

## Environment

- Windows host, Docker Desktop Linux containers, approximately 9.7 GiB assigned to Docker.
- Ubuntu 24.04 container; QEMU 8.2.2; Python 3.12.3.
- FastAPI 0.162.0, Uvicorn 0.54.0, Pydantic 2.14.2.
- Installed HakiOS source: `88513176b1e96ecf0b764cd62c6f4e6ac71345e3`.
- Existing local APFS images were used. No replacement IPSW was downloaded.
- Kernel and loader match the SHA-256 values in the installed `prebuilt/SHA256SUMS`.

## Changes

- Use the installed `qemu/run-ios.sh` launcher and its positional duration argument.
- Configure Ubuntu AAVMF firmware paths and install QEMU GTK and ROM dependencies.
- Reject missing/empty prerequisite files before starting a session.
- Clear stale X11 locks on container startup and wait for Xvfb before starting x11vnc.
- Use a portrait X11 desktop to contain the 1125 × 2436 guest display.
- Stage runtime files and guest RAM on the persistent Linux Docker volume.
- Buffer serial output before writing to the Windows log directory.
- Keep GNU timeout in the managed process group and kill remaining descendants on Stop.
- Stop the managed session on API shutdown, and enforce duration plus 40 seconds of wall time.
- Add a healthcheck covering the API, VNC and noVNC listener.

## Verified

- `docker compose up -d --build`: successful.
- Container healthcheck: healthy.
- Container restart: Xvfb and VNC return successfully despite existing X11 lock files.
- Nine regression tests pass, including a subprocess that ignores SIGTERM, failed guest exit reporting, duplicate starts, duration validation, launcher failures, API shutdown, detecting a guest kernel panic while its emulator process remains alive, and staging an alternate image without replacing the original.
- Browser test with Microsoft Edge/Playwright: no JavaScript page errors; RUNNING status; Start disabled; Stop enabled; embedded noVNC connected.
- Live API: invalid durations return HTTP 422; a duplicate start returns HTTP 409.
- Real guest reaches Darwin/XNU, mounts APFS, completes 36 init checks with zero failures, and launches SpringBoard and backboardd.
- Apple boot logo is visibly rendered through the embedded noVNC display; screenshot: `artifacts/dashboard-apple-logo.png`.
- Guest backboardd logs incoming touch events. This establishes the input path, separately from completing an interactive home-screen test.

## Guest interface and lifecycle

The live automatic-stop test passes: an isolated real API process accepted a 60-second session, stopped it in 100.41 seconds (the 100-second wall limit plus polling overhead), and terminated its SIGTERM-ignoring child. Result: `workspace/logs/timeout-validation.json`. The primary guest continued booting during this isolated test.

The real 1200-second guest session also reached its automatic stop, returned STOPPED, and left no QEMU process behind. Result: `artifacts/real-session-timeout.json`. That one-CPU boot rendered the Apple logo but did not reach the home screen before its session limit.

A four-CPU boot and a second four-CPU boot using 25 upstream default jobs both failed with a kernel panic. Both panic reports identify the same ticket spinlock, at `_pset0 + 0x100`, while scheduling a thread. The first panicked in `geod`; the reduced-job run panicked in `fseventsd`. Reducing background services therefore did not fix this failure. The original boot image has been restored from its backup.

After those panics, Compose was temporarily returned to one emulated CPU (`QEMU_SMP=1`, `CMDLINE=cpus=1`) for the successful Home Screen boot. The current local eight-CPU profile is described below. The 3600-second session default remains. The manager now reports `guest_status=failed` and the panic message independently of whether QEMU is still running; the browser displays FAILED in that case. A Playwright fixture verifies that Start remains disabled and Stop remains enabled while a failed guest's emulator process is alive.

The four-CPU guest confirms all four CPUs active, repeats all 36 init checks without failure, reports `svc_test: 0 failed`, and passes all 80 `surf_test` checks (including cross-process surface access).

The one-CPU uncompressed-cache boot reached the real SpringBoard Home Screen at approximately 05:10 Jakarta, about 38 minutes after Start. Settings was opened through QMP touch input and fully rendered by approximately 05:15. Screenshots: `artifacts/dashboard-home.png` and `artifacts/dashboard-settings.png`. Application startup took several minutes. The white widgets and slow input are remaining limitations; rendering these screens does not establish compatibility with every app.

The embedded noVNC URL now explicitly enables input (`view_only=false`), enables its fallback dot cursor, and reconnects automatically. A CSS crosshair keeps the workstation pointer visible even when QEMU hides the tablet cursor. Browser validation confirms computed cursor `crosshair`, dot cursor enabled and view-only disabled (`artifacts/cursor-validation.json`). X11 and QEMU pointer buttons were released and the display services reconnected without restarting the guest. Browser clicks reach VNC, but end-to-end input response remains under examination: backboardd logged input timestamps several minutes behind processing time.

The packaged noVNC input path is adapted by `scripts/configure-novnc.py`: hover moves stay local, drag updates are throttled to 100 ms, and blur/visibility changes release a held pointer at its last coordinates. The build fails if the expected upstream hooks change. The live browser test forwards events to the actual VNC server and verifies zero hover packets, a down packet, release on blur, final button mask zero, and crosshair cursor (`artifacts/pointer-release-validation.json`).

## Eight-CPU performance profile

The Windows host has an Intel Core i5-8250U (4 cores, 8 logical processors) and approximately 19.9 GiB physical RAM. Docker exposes all 8 logical processors, with no container CPU quota or cpuset restriction. Allocating more virtual RAM does not increase Docker's approximately 9.7 GiB physical memory budget.

An isolated eight-CPU preflight used the same uncompressed-cache image, 10 GiB virtual RAM and `cpus=8 tlto_us=30000000 slto_us=30000000`. XNU's [machine_routines.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-8796.121.2/osfmk/arm64/machine_routines.c) defines these boot arguments in microseconds; both timeouts were set to 30 seconds. This extends the watchdog thresholds rather than disabling lock checking. All eight CPUs registered, 36 init checks passed, `svc_test: 0 failed`, and `surf_test: 80 checks, 0 failed`. No kernel panic was recorded over approximately 14 minutes before container replacement ended this preflight. This is a preflight, not proof of an interactive eight-CPU Home Screen. Evidence: `artifacts/smp8-preflight.log` and the persistent `/var/lib/wfs/diagnostics/smp8-timeout/console.log`.

The one-CPU display session stopped automatically at approximately 05:33 Jakarta. The local `.env` now selects eight CPUs and the timeout arguments above. The container was rebuilt with the cursor/input fixes and a new primary eight-CPU session was started for full interface validation.

## Image checks

The installed system image was read in full with the repository's independent Python APFS reader: 62,261 entries, 5,644,490,423 logical file bytes, 12,429 metadata checksums verified, zero checksum failures. A separate diagnostic image with an uncompressed dyld cache was generated and then compared in full through the kernel's APFS reader. Both images contain 62,261 entries and produce the same sorted census digest (`d5d99ce98f91690cb4bbeee40b803c4defd5d1c5a9648a2e38b1a11050decb29`), covering file content, paths, types, modes, owners, groups and logical sizes. See `artifacts/cache-profile-validation.json`.

The local `.env` selects `/var/lib/wfs/images/system-cache-plain.apfs` from the persistent Docker volume and `QEMU_RAM_GB=10`, since the uncompressed-cache image is approximately 4.21 GB. The original `workspace/hackios/userland/system.apfs` is preserved. This profile reached Home Screen and Settings with one CPU as described above.

The kernel's APFS reader was also compiled as a Linux tool and used to compare SpringBoard's executable, Info.plist and Assets.car, plus backboardd and lsd, with their existing extraction inputs. All five byte-for-byte comparisons passed (`artifacts/critical-files-validation.json`).

## Notification test repair

The original prebuilt service test failed its notification-delivery check during the busy one-CPU boot. Its source checked delivery only once, after a fixed 100 ms sleep. Preferences, logging and all 80 surface checks passed in that same boot.

The notification check now polls for the actual delivery with a 10-second monotonic deadline. It was rebuilt from source using clang/lld 18.1.3 and the Theos iPhoneOS 16.5 SDK checkout `0222fd5413cf4b9af096f37b4621afa2688572f7`. No mock notification service was used: a separate headless one-CPU guest ran the rebuilt program twice against iOS notifyd, cfprefsd and logd. Both runs reported zero failures; delivery waits were 0.062 and 0.095 seconds. The isolated guest's 36 init checks also passed and its process group was terminated afterward. See `artifacts/notification-validation.json` and `artifacts/guest-test-build.json`.

The fixed binary is installed in local `prebuilt/userland/svc_test`, and its checksum manifest is updated. `userland/root.apfs` was rebuilt for subsequent sessions, with QUIET=1 to reduce launchd console noise. The root image's test executable matches the verified binary byte for byte. The build now also omits the var-store job when its executable is absent in the supplied prebuilts. The existing running display guest retains the boot image it loaded before this repair.

## Evidence

- `artifacts/unit-tests.txt`
- `artifacts/browser-result.json`
- `artifacts/live-api.json`
- `artifacts/dashboard-running.png`
- `artifacts/latest-boot.log`
- `workspace/logs/session.log`

## Reproduce

```sh
docker compose up -d --build
# Dashboard: http://localhost:8000
# Display: http://localhost:6080/vnc.html
```

The first start stages roughly 2.4 GB into the Linux runtime volume and can take several minutes on this host. Subsequent starts reuse the cache. Source files and original images remain in `workspace/hackios`; the runtime volume contains working copies.
