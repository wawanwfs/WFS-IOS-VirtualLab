"""Compare critical files read by the kernel's APFS reader with local inputs."""
import hashlib
import json
from pathlib import Path
import subprocess

base = Path('/workspace/hackios')
image = '/var/lib/wfs/hakios/userland/system.apfs'
paths = [
    '/System/Library/CoreServices/SpringBoard.app/SpringBoard',
    '/System/Library/CoreServices/SpringBoard.app/Info.plist',
    '/System/Library/CoreServices/SpringBoard.app/Assets.car',
    '/usr/libexec/backboardd',
    '/usr/libexec/lsd',
]
results = []
for path in paths:
    original = base / 'sysimage/rootfs' / path.lstrip('/')
    if not original.is_file():
        raise SystemExit(f'Missing comparison input: {original}')
    read = subprocess.run(['/tmp/wfs-symbols/apfs-tool', 'cat', image, path],
                          check=True, capture_output=True).stdout
    expected = original.read_bytes()
    result = {'path': path, 'bytes': len(read),
              'sha256': hashlib.sha256(read).hexdigest(), 'matches': read == expected}
    results.append(result)
    if not result['matches']:
        raise SystemExit(f'APFS read mismatch: {result}')
output = json.dumps(results, indent=2)
Path('/workspace/logs/critical-files-validation.json').write_text(output)
print(output)
