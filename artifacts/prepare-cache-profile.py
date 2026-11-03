"""Prepare a separate APFS image with uncompressed dyld cache for a TCG test.

Uses only the existing local image; no source image is modified. Metadata and
symlink targets are passed to the same APFS writer through its manifest format.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

sys.path.insert(0, '/workspace/hackios/tools/apfs')
import apfs

diagnostics = Path('/var/lib/wfs/diagnostics')
root = diagnostics / 'system-unpacked'
if root.exists():
    raise SystemExit(f'Refusing to overwrite existing export: {root}')
root.mkdir()
container = apfs.Container('/var/lib/wfs/hakios/userland/system.apfs')
volume = apfs.pick_volume(container, None)
count = total = 0
digest = hashlib.sha256()
manifest_path = diagnostics / 'system-unpacked.manifest'
with manifest_path.open('wb') as manifest:
    for path, _, file_id, _ in apfs.walk(volume, apfs.ROOT_DIR_INO_NUM):
        relative = PurePosixPath(path.lstrip('/'))
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit(f'Unsafe image path: {path}')
        inode = volume.inode(file_id)
        if inode is None:
            raise SystemExit(f'No inode for {path}')
        target = root / str(relative)
        line = f'{inode.mode:o}\t{inode.owner}\t{inode.group}\t{relative}'.encode()
        if inode.is_dir:
            target.mkdir(exist_ok=True)
        elif inode.is_link:
            # Manifest creates the symlink after source traversal; no host link
            # can redirect file writes while exporting the image.
            line += b'\t' + inode.symlink_target_bytes()
        elif inode.is_reg:
            data = inode.contents()
            if len(data) != inode.size:
                raise SystemExit(f'Short read for {path}')
            target.write_bytes(data)
            digest.update(str(relative).encode() + b'\0' + hashlib.sha256(data).digest())
            total += len(data)
        else:
            raise SystemExit(f'Unexpected file type for {path}: {inode.mode:o}')
        manifest.write(line + b'\n')
        count += 1
        if count % 2500 == 0:
            print(f'Exported {count} entries, {total} bytes', flush=True)
if container.blocks.cksum_bad:
    raise SystemExit('APFS metadata checksum errors')
summary = {'entries': count, 'bytes': total, 'content_digest': digest.hexdigest(),
           'metadata_checksums_verified': container.blocks.cksum_checked,
           'metadata_checksum_errors': container.blocks.cksum_bad}
container.close()
(diagnostics / 'system-export.json').write_text(json.dumps(summary, indent=2))
print(json.dumps(summary), flush=True)
subprocess.run([
    'python3', '/workspace/hackios/tools/apfs/mkapfs.py', '-z',
    '--plain', 'System/Cryptexes/OS/System/Library/Caches/com.apple.dyld',
    '-o', str(diagnostics / 'system-cache-plain.apfs'),
    f'System={root},manifest={manifest_path}',
], check=True)
