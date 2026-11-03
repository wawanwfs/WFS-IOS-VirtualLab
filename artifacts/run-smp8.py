"""Compare the upstream default service set in a separate one-CPU guest."""
from pathlib import Path
import json
import os
import plistlib
import shutil
import signal
import subprocess
import time

source = Path('/workspace/hackios')
runtime = Path('/var/lib/wfs/diagnostics/smp8-timeout')
runtime.mkdir(exist_ok=False)
root_image = source / 'userland/root.apfs'
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
environment = {**os.environ, 'QEMU_SMP': '8', 'CMDLINE': 'cpus=8 tlto_us=30000000 slto_us=30000000',
               'QEMU_RAM_GB': '10', 'QEMU_INSTANCE': '1',
               'ROOT': str(root_image), 'IMG': str(image),
               'QEMU_EFI': '/usr/share/AAVMF/AAVMF_CODE.fd',
               'QEMU_VARS': '/usr/share/AAVMF/AAVMF_VARS.fd'}
log = runtime / 'console.log'
with log.open('wb') as output:
    process = subprocess.Popen(['bash', str(runtime / 'qemu/run-ios.sh'), '1200',
                                '-display', 'none', '-vnc', '127.0.0.1:1', '-nic', 'none'],
                               env=environment, stdout=output, stderr=subprocess.STDOUT,
                               start_new_session=True)
    (runtime / 'process.json').write_text(json.dumps({'pid': process.pid, 'started': time.time()}))
    try:
        process.wait(timeout=1245)
    except subprocess.TimeoutExpired:
        pass
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
shutil.copy2(log, '/workspace/logs/smp8-timeout.log')
print(json.dumps({'exit_code': process.returncode, 'log': str(log)}), flush=True)
