"""Compare every file and relevant metadata through the kernel's APFS reader."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

images = [
    '/var/lib/wfs/hakios/userland/system.apfs',
    '/var/lib/wfs/diagnostics/system-cache-plain.apfs',
]
results = []
for image in images:
    started = time.monotonic()
    result = subprocess.run(['/tmp/wfs-symbols/apfs-tool', 'census', image],
                            capture_output=True, check=True, timeout=600)
    lines = sorted(result.stdout.splitlines())
    results.append({'image': image, 'entries': len(lines),
                    'content_and_metadata_digest': hashlib.sha256(b'\n'.join(lines)).hexdigest(),
                    'elapsed_seconds': round(time.monotonic() - started, 2),
                    'reader_report': result.stderr.decode(errors='replace')})
    print(json.dumps(results[-1]), flush=True)
matches = results[0]['content_and_metadata_digest'] == results[1]['content_and_metadata_digest']
report = {'matches': matches, 'images': results}
Path('/workspace/logs/cache-profile-validation.json').write_text(json.dumps(report, indent=2))
if not matches:
    raise SystemExit('Repacked image differs in logical contents or metadata')
