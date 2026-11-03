"""Make a separate diagnostic boot image using upstream's default job list.

Run inside the Linux container. The source images and running VM are untouched.
"""
from pathlib import Path
import plistlib
import shutil
import subprocess

source = Path('/workspace/hackios')
target = Path('/var/lib/wfs/diagnostics/minimal-root')
if target.exists():
    raise SystemExit(f'Diagnostic directory already exists: {target}')
shutil.copytree(source / 'userland/root', target, symlinks=True)
labels = set('''com.apple.notifyd com.apple.cfprefsd.xpc.daemon
com.apple.cfprefsd.xpc.daemon.system com.apple.logd com.apple.syslogd
com.apple.distnoted.xpc.daemon com.apple.diagnosticd com.apple.fseventsd
com.apple.containermanagerd com.apple.containermanagerd.system
com.apple.runningboardd com.apple.backboardd com.apple.mobile.usermanagerd
com.apple.mobilegestalt.xpc com.apple.lsd com.apple.powerd com.apple.analyticsd
com.apple.logd_helper com.apple.iconservices.iconservicesagent
com.apple.pluginkit.pkd com.apple.SpringBoard com.apple.wifid'''.split())
found = set()
removed = 0
for path in (target / 'LaunchDaemons').glob('*.plist'):
    label = plistlib.loads(path.read_bytes())['Label']
    if label in labels or label.startswith('com.hakios.'):
        found.add(label)
    else:
        path.unlink()
        removed += 1
missing = labels - found
if missing:
    raise SystemExit(f'Missing essential jobs: {sorted(missing)}')
print(f'Kept {len(found)} jobs; removed {removed} optional jobs', flush=True)
image = target.with_suffix('.apfs')
subprocess.run(['python3', str(source / 'tools/apfs/mkapfs.py'), '-z',
                '--plain', 'fw', '-o', str(image), f'redwood={target}'], check=True)
shutil.copy2(image, '/workspace/logs/minimal-root.apfs')
print(image, flush=True)
