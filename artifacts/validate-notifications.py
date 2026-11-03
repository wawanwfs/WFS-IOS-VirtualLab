"""Run the rebuilt service test in an isolated, headless, one-CPU guest.

Its private RAM mapping shares the existing immutable backing file with the
main guest. Firmware variables, payload, root image and monitor ports are separate.
"""
from pathlib import Path
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import time

source = Path('/workspace/hackios')
runtime = Path('/var/lib/wfs/diagnostics/notify-run')
runtime.mkdir(exist_ok=False)
root = runtime / 'root'
shutil.copytree(source / 'userland/root', root, symlinks=True)
shutil.copy2('/var/lib/wfs/toolchain/svc_test', root / 'bin/svc_test')
keep = {'com.apple.notifyd', 'com.apple.cfprefsd.xpc.daemon',
        'com.apple.cfprefsd.xpc.daemon.system', 'com.apple.logd',
        'com.apple.logd_helper', 'com.apple.syslogd', 'com.hakios.demo'}
found = set()
for path in (root / 'LaunchDaemons').glob('*.plist'):
    label = plistlib.loads(path.read_bytes())['Label']
    if label in keep:
        found.add(label)
    else:
        path.unlink()
if found != keep:
    raise SystemExit(f'Missing test services: {keep - found}')
(root / 'etc/rc.jobs').write_text('/redwood/bin/svc_test\nsleep 2\n/redwood/bin/svc_test\n')
(root / 'etc/quiet').touch()
root_image = runtime / 'root.apfs'
subprocess.run(['python3', str(source / 'tools/apfs/mkapfs.py'), '-z', '-o',
                str(root_image), f'redwood={root}'], check=True)
for name in ['qemu/run-ios.sh', 'qemu/run.sh', 'xnuloader/mkpayload.py',
             'prebuilt/mach.development.bcm2837', 'prebuilt/loader.efi']:
    target = runtime / name
    target.parent.mkdir(exist_ok=True, parents=True)
    shutil.copy2(Path('/var/lib/wfs/hakios') / name, target)
ram = Path('/var/lib/wfs/hakios/qemu/ram.img')
image = Path('/var/lib/wfs/images/system-cache-plain.apfs')
if image.stat().st_mtime_ns > ram.stat().st_mtime_ns:
    raise SystemExit('RAM backing file would be rebuilt; refusing shared test')
os.symlink(ram, runtime / 'qemu/ram.img')
environment = {**os.environ, 'QEMU_SMP': '1', 'CMDLINE': 'cpus=1',
               'QEMU_RAM_GB': '10', 'QEMU_INSTANCE': '1',
               'ROOT': str(root_image), 'IMG': str(image),
               'QEMU_EFI': '/usr/share/AAVMF/AAVMF_CODE.fd',
               'QEMU_VARS': '/usr/share/AAVMF/AAVMF_VARS.fd'}
log = runtime / 'console.log'
started = time.monotonic()
with log.open('wb') as output:
    process = subprocess.Popen(['bash', str(runtime / 'qemu/run-ios.sh'), '600',
                                '-display', 'none', '-nic', 'none'], env=environment,
                               stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        while time.monotonic() - started < 620 and process.poll() is None:
            text = log.read_text(errors='replace')
            before_replay = text.split('== KERNEL LOG ==')[0]
            if before_replay.count('svc_test: 0 failed') >= 2 or 'panic(cpu ' in text:
                break
            time.sleep(2)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
text = log.read_text(errors='replace').split('== KERNEL LOG ==')[0]
result = {'passed': text.count('svc_test: 0 failed') >= 2 and '[FAIL]' not in text,
          'service_test_pids': re.findall(r'svc_test: pid (\d+)', text),
          'delivery_waits_seconds': re.findall(r'notification delivery wait: ([\d.]+)', text),
          'init_checks_passed': '=== 36 checks, 0 failed ===' in text,
          'elapsed_seconds': round(time.monotonic() - started, 2),
          'log': str(log)}
Path('/workspace/logs/notification-validation.json').write_text(json.dumps(result, indent=2))
shutil.copy2(log, '/workspace/logs/notification-validation.log')
print(json.dumps(result), flush=True)
if not result['passed']:
    raise SystemExit(1)
