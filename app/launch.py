"""Stage QEMU's working files on a Linux volume, then exec the upstream launcher.

Windows bind mounts are suitable for source and logs, but guest RAM mappings
need Linux filesystem semantics and fast page faults.
"""
import os
from pathlib import Path
import shutil
import sys


def main():
    source = Path(os.environ.get('WFS_WORKSPACE', '/workspace')) / 'hackios'
    runtime = Path(os.environ.get('WFS_RUNTIME', '/var/lib/wfs/hakios')).resolve()
    files = (
        'qemu/run-ios.sh', 'qemu/run.sh', 'xnuloader/mkpayload.py',
        'prebuilt/mach.development.bcm2837', 'prebuilt/loader.efi',
        'userland/root.apfs', 'userland/system.apfs',
    )
    for name in files:
        src, dst = source / name, runtime / name
        if name == 'userland/system.apfs' and os.environ.get('WFS_SYSTEM_IMAGE'):
            src = Path(os.environ['WFS_SYSTEM_IMAGE'])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (not dst.exists() or src.stat().st_size != dst.stat().st_size
                or src.stat().st_mtime_ns != dst.stat().st_mtime_ns):
            print(f'Preparing Linux runtime: {name}', flush=True)
            temporary = dst.with_suffix(dst.suffix + '.tmp')
            shutil.copy2(src, temporary)
            temporary.replace(dst)
            if name == 'userland/system.apfs':
                # The upstream launcher normally compares mtimes. Explicitly
                # invalidate RAM when an older image was restored from backup.
                (runtime / 'qemu/ram.img').unlink(missing_ok=True)
    # GNU timeout otherwise creates its own process group, escaping the API's
    # session group and leaving QEMU alive when Stop terminates the shell.
    runner = runtime / 'qemu/run.sh'
    text = runner.read_text()
    text = text.replace('timeout "$T" ', 'timeout --foreground "$T" ')
    runner.write_text(text)
    os.chdir(runtime)
    os.execvpe('bash', ['bash', str(runtime / 'qemu/run-ios.sh'), *sys.argv[1:]], os.environ)


if __name__ == '__main__':
    main()
