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
runtime = Path('/var/lib/wfs/diagnostics/minimal-ui-1cpu')
runtime.mkdir(exist_ok=False)
root = runtime / 'root'
shutil.copytree(source / 'userland/root', root, symlinks=True)
labels = set('''com.apple.notifyd com.apple.cfprefsd.xpc.daemon
com.apple.cfprefsd.xpc.daemon.system com.apple.logd com.apple.syslogd
com.apple.distnoted.xpc.daemon com.apple.diagnosticd com.apple.fseventsd
com.apple.containermanagerd com.apple.containermanagerd.system
com.apple.runningboardd com.apple.backboardd com.apple.mobile.usermanagerd
com.apple.mobilegestalt.xpc com.apple.lsd com.apple.powerd com.apple.analyticsd
com.apple.logd_helper com.apple.iconservices.iconservicesagent
com.apple.pluginkit.pkd com.apple.SpringBoard com.apple.wifid
com.hakios.demo com.hakios.wifi'''.split())
found = set()
for path in (root / 'LaunchDaemons').glob('*.plist'):
    job = plistlib.loads(path.read_bytes())
    if job['Label'] not in labels:
        path.unlink()
    else:
        found.add(job['Label'])
        if job['Label'] == 'com.apple.lsd':
            job.setdefault('EnvironmentVariables', {})['OS_ACTIVITY_DT_MODE'] = 'YES'
            path.write_bytes(plistlib.dumps(job))
if found != labels:
    raise SystemExit(f'Missing default services: {labels - found}')
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
shutil.copy2(log, '/workspace/logs/minimal-ui-1cpu.log')
print(json.dumps({'exit_code': process.returncode, 'log': str(log)}), flush=True)
