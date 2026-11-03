"""Read-only lookup of diagnostic stack addresses in the existing iOS cache."""
import subprocess
import sys

for raw in sys.argv[1:]:
    result = subprocess.run([
        '/tmp/wfs-symbols/ipsw', 'dyld', 'a2s',
        '/tmp/wfs-symbols/cache-debug/dyld_shared_cache_arm64',
        hex(int(raw, 16) - 0x746c000),
        '--cache', '/tmp/wfs-symbols/cache.a2s',
    ], text=True, capture_output=True)
    print(raw, result.stdout.strip(), result.stderr.strip(), flush=True)
